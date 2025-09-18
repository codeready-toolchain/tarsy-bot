/**
 * Authentication service for handling OAuth2 Proxy authentication flow
 */

import { config } from '../config/env';

export interface AuthUser {
  email: string;
  name?: string;
  groups?: string[];
}

class AuthService {
  private static instance: AuthService;

  public static getInstance(): AuthService {
    if (!AuthService.instance) {
      AuthService.instance = new AuthService();
    }
    return AuthService.instance;
  }

  /**
   * Check if user is authenticated by making a request to a protected endpoint
   */
  async checkAuthStatus(): Promise<boolean> {
    try {
      const response = await fetch('/api/v1/history/active-sessions', {
        method: 'GET',
        credentials: 'include',
        headers: { 'Accept': 'application/json' },
      });

      // Check for redirects (either via response.redirected or 3xx status codes)
      const isRedirected = response.redirected || (response.status >= 300 && response.status < 400);
      
      // Get and validate Content-Type header
      const contentType = response.headers.get('content-type');
      const isJsonResponse = Boolean(contentType && contentType.includes('application/json'));
      
      // Only consider authenticated if:
      // 1. Response status is 200, 2. Response was not redirected, 3. Content-Type indicates JSON
      const isAuthenticated = response.status === 200 && !isRedirected && isJsonResponse;
      
      if (!isAuthenticated && config.isDevelopment) {
        console.log('🔍 Auth check failed:', { status: response.status, redirected: isRedirected, hasJson: isJsonResponse });
      }
      
      return isAuthenticated;
    } catch (error) {
      console.warn('Auth status check failed:', error);
      return false;
    }
  }

  /**
   * Get current user info from OAuth2 proxy userinfo endpoint
   */
  async getCurrentUser(): Promise<AuthUser | null> {
    try {
      // Try the oauth2-proxy userinfo endpoint first
      try {
        const userinfoResponse = await fetch('/oauth2/userinfo', {
          method: 'GET', 
          credentials: 'include',
          headers: { 'Accept': 'application/json' },
        });

        if (userinfoResponse.ok) {
          const userinfo = await userinfoResponse.json();
          if (userinfo.email) {
            return {
              email: userinfo.email,
              name: userinfo.user || userinfo.login || userinfo.preferred_username || userinfo.name || userinfo.email.split('@')[0],
              groups: [],
            };
          }
        }
      } catch (error) {
        if (config.isDevelopment) {
          console.log('OAuth2-proxy userinfo endpoint failed, trying headers fallback');
        }
      }

      // Fallback: Try to get user info from headers
      const response = await fetch('/api/v1/history/active-sessions', {
        method: 'GET', 
        credentials: 'include',
        headers: { 'Accept': 'application/json' },
      });

      if (!response.ok) {
        return null;
      }

      // Extract user info from response headers
      const rawEmail = response.headers.get('X-Forwarded-Email') || response.headers.get('X-User-Email');
      const email = rawEmail && rawEmail.includes('@') ? rawEmail : null;
      const username = response.headers.get('X-Forwarded-User') || 
                      response.headers.get('X-Forwarded-Preferred-Username') ||
                      response.headers.get('X-User-Name');
      const displayName = response.headers.get('X-User-Name');
      
      if (email) {
        return {
          email,
          name: username || displayName || email.split('@')[0],
          groups: response.headers.get('X-Forwarded-Groups')?.split(',').map(g => g.trim()).filter(g => g) || [],
        };
      }

      // If we have username but no valid email, still return user info
      if (username) {
        return {
          email: 'unknown@user.com',
          name: username || displayName || 'Authenticated User',
          groups: response.headers.get('X-Forwarded-Groups')?.split(',').map(g => g.trim()).filter(g => g) || [],
        };
      }

      // No user info available but authenticated
      if (config.isDevelopment) {
        console.warn('User is authenticated but no user info available');
      }
      return {
        email: 'unknown@user.com',
        name: 'Authenticated User',
        groups: [],
      };
    } catch (error) {
      console.warn('Failed to get current user:', error);
      return null;
    }
  }

  /**
   * Redirect to OAuth login via OAuth2 proxy
   */
  redirectToLogin(): void {
    const currentPath = window.location.pathname + window.location.search;
    const returnUrl = `${window.location.origin}${currentPath}`;
    const loginUrl = `/oauth2/sign_in?rd=${encodeURIComponent(returnUrl)}`;
    
    if (config.isDevelopment) {
      console.log('Redirecting to login:', loginUrl);
    }
    
    window.location.href = loginUrl;
  }

  /**
   * Logout by clearing OAuth session
   */
  logout(): void {
    if (config.isDevelopment) {
      console.log('Logging out user');
    }
    window.location.href = '/oauth2/sign_out';
  }

  /**
   * Handle authentication error (401) by redirecting to login
   */
  handleAuthError(): void {
    // Prevent redirect loops if already on OAuth2 proxy pages
    const currentPath = window.location.pathname;
    const isOAuthPath = currentPath.startsWith('/oauth2/sign_in') || currentPath.startsWith('/oauth2/callback');
    
    if (isOAuthPath) {
      console.warn('Already on OAuth login/callback page, avoiding redirect loop');
      return;
    }

    if (config.isDevelopment) {
      console.log('Authentication error, redirecting to login');
    }
    
    this.redirectToLogin();
  }
}

export const authService = AuthService.getInstance();
