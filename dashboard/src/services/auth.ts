/**
 * Authentication service for handling OAuth2 Proxy authentication flow
 */

import { urls, config } from '../config/env';

export interface AuthUser {
  email: string;
  name?: string;
  groups?: string[];
}

class AuthService {
  private static instance: AuthService;
  private readonly OAUTH_PROXY_BASE = urls.oauth.base;

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
      console.log('🔍 Checking auth status...');
      
      // Use a definitely protected endpoint - active sessions requires authentication
      const protectedEndpoint = '/api/v1/history/active-sessions';
      
      const response = await fetch(protectedEndpoint, {
        method: 'GET',
        credentials: 'include', // Important: include cookies for OAuth2 proxy
        headers: {
          'Accept': 'application/json',
        },
      });

      console.log('🔍 Auth check response:', response.status, response.ok);
      console.log('🔍 Is authenticated:', response.status === 200);
      
      return response.status === 200;
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
      console.log('🔍 Fetching user info from oauth2-proxy...');
      
      // Try the oauth2-proxy userinfo endpoint first
      const userinfoResponse = await fetch('/oauth2/userinfo', {
        method: 'GET', 
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        },
      });

      if (userinfoResponse.ok) {
        const userinfo = await userinfoResponse.json();
        console.log('📋 OAuth2-proxy userinfo response:', userinfo);
        console.log('🔍 Available userinfo fields:', Object.keys(userinfo));
        console.log('🎯 Checking userinfo fields:', {
          user: userinfo.user,
          login: userinfo.login,
          preferred_username: userinfo.preferred_username,
          name: userinfo.name,
          email: userinfo.email
        });
        
        if (userinfo.email) {
          return {
            email: userinfo.email,
            // Priority: username > login > preferred_username > name > email username
            name: userinfo.user || userinfo.login || userinfo.preferred_username || userinfo.name || userinfo.email.split('@')[0],
            groups: [], // Removed groups as per user request
          };
        }
      }

      // Fallback: Try to get user info from headers
      console.log('🔄 Fallback: trying to get user info from headers...');
      const response = await fetch('/api/v1/history/active-sessions', {
        method: 'GET', 
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        },
      });

      if (!response.ok) {
        console.warn('❌ Both userinfo endpoint and headers approach failed');
        return null;
      }

      // Extract user info from response headers  
      const email = response.headers.get('X-Forwarded-Email') ||
                   response.headers.get('X-Forwarded-User') ||
                   response.headers.get('X-User-Email');
      
      const username = response.headers.get('X-Forwarded-Preferred-Username');
      const displayName = response.headers.get('X-User-Name');
      
      // Get all forwarded headers for debugging
      const allHeaders = {
        'X-Forwarded-User': response.headers.get('X-Forwarded-User'),
        'X-Forwarded-Email': response.headers.get('X-Forwarded-Email'),
        'X-Forwarded-Preferred-Username': response.headers.get('X-Forwarded-Preferred-Username'),
        'X-User-Name': response.headers.get('X-User-Name'),
        'X-Forwarded-Groups': response.headers.get('X-Forwarded-Groups')
      };
      
      console.log('🔍 All OAuth2-proxy headers:', allHeaders);
      console.log('🎯 Selected values:', {
        email,
        username,
        displayName,
        finalName: username || displayName || email?.split('@')[0]
      });
      
      if (email) {
        return {
          email,
          // Priority: username > display name > email username
          name: username || displayName || email.split('@')[0],
          groups: response.headers.get('X-Forwarded-Groups')?.split(',').map(g => g.trim()).filter(g => g) || [],
        };
      }

      // If we get here, we're authenticated but no user info is available
      console.warn('⚠️ User is authenticated but no user info available');
      return {
        email: 'unknown@user.com',
        name: 'Authenticated User',
        groups: [],
      };
    } catch (error) {
      console.warn('❌ Failed to get current user:', error);
      return null;
    }
  }

  /**
   * Redirect to OAuth login directly via OAuth2 proxy
   * This bypasses the Vite proxy issue by going directly to the OAuth2 proxy
   */
  redirectToLogin(): void {
    const currentPath = window.location.pathname + window.location.search;
    // In development, use Vite proxy; in production use origin  
    const returnUrl = import.meta.env.DEV 
      ? `${window.location.origin}${currentPath}`
      : `${window.location.origin}${currentPath}`;
    
    const loginUrl = `/oauth2/sign_in?rd=${encodeURIComponent(returnUrl)}`;
    
    console.log('🔐 OAuth Login Debug:');
    console.log('  - Current location:', window.location.href);
    console.log('  - Current path:', currentPath);
    console.log('  - Window origin:', window.location.origin);
    console.log('  - Return URL (unencoded):', returnUrl);
    console.log('  - Return URL (encoded):', encodeURIComponent(returnUrl));
    console.log('  - Full login URL:', loginUrl);
    console.log('  - DEV mode:', import.meta.env.DEV);
    
    window.location.href = loginUrl;
  }

  /**
   * Logout by clearing OAuth session
   */
  logout(): void {
    console.log('🚪 Logging out...');
    
    // In development, use relative URL to go through Vite proxy
    // In production, use the full OAuth2 proxy URL
    const logoutUrl = import.meta.env.DEV 
      ? '/oauth2/sign_out'
      : `${this.OAUTH_PROXY_BASE}/oauth2/sign_out`;
    
    console.log('🚪 Redirecting to logout URL:', logoutUrl);
    console.log('🚪 Environment:', import.meta.env.DEV ? 'development' : 'production');
    window.location.href = logoutUrl;
  }

  /**
   * Handle authentication error (401) by redirecting to login
   */
  handleAuthError(): void {
    // Only prevent redirect if we're actually on an OAuth2 proxy page
    const currentUrl = window.location.href;
    const isOAuthProxyUrl = currentUrl.includes(config.oauthProxyUrl.replace('http://', '').replace('https://', '')) && 
                          (currentUrl.includes('/oauth2/sign_in') || 
                           currentUrl.includes('/oauth2/callback'));
    
    console.log('handleAuthError called:', {
      currentUrl,
      isOAuthProxyUrl,
      pathname: window.location.pathname,
      search: window.location.search
    });

    if (isOAuthProxyUrl) {
      console.warn('Already on OAuth proxy login/callback page, not redirecting to avoid loop');
      return;
    }

    console.log('Authentication required - redirecting to OAuth login');
    this.redirectToLogin();
  }
}

export const authService = AuthService.getInstance();
