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

      // Check for redirects (either via response.redirected or 3xx status codes)
      const isRedirected = response.redirected || (response.status >= 300 && response.status < 400);
      
      // Get and validate Content-Type header
      const contentType = response.headers.get('content-type');
      const isJsonResponse = Boolean(contentType && contentType.includes('application/json'));
      
      // Only consider authenticated if:
      // 1. Response status is 200 (or response.ok)
      // 2. Response was not redirected
      // 3. Content-Type indicates JSON (conservatively treat missing as unauthenticated)
      const isAuthenticated = response.status === 200 && !isRedirected && isJsonResponse;
      
      console.log('🔍 Auth check response:', {
        status: response.status,
        ok: response.ok,
        redirected: response.redirected,
        isRedirected,
        contentType,
        isJsonResponse,
        isAuthenticated
      });
      
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
        if (config.isDevelopment) {
          console.log('📋 OAuth2-proxy userinfo response:', userinfo);
          console.log('🔍 Available userinfo fields:', Object.keys(userinfo));
          console.log('🎯 Checking userinfo fields:', {
            user: userinfo.user,
            login: userinfo.login,
            preferred_username: userinfo.preferred_username,
            name: userinfo.name,
            email: userinfo.email
          });
        }
        
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
      // Only get email from explicit email headers and validate it contains "@"
      const rawEmail = response.headers.get('X-Forwarded-Email') ||
                      response.headers.get('X-User-Email');
      const email = rawEmail && rawEmail.includes('@') ? rawEmail : null;
      
      // Get username from user/username headers (X-Forwarded-User is username, not email)
      const username = response.headers.get('X-Forwarded-User') ||
                      response.headers.get('X-Forwarded-Preferred-Username') ||
                      response.headers.get('X-User-Name');
      const displayName = response.headers.get('X-User-Name');
      
      // Get all forwarded headers for debugging
      const allHeaders = {
        'X-Forwarded-User': response.headers.get('X-Forwarded-User'),
        'X-Forwarded-Email': response.headers.get('X-Forwarded-Email'),
        'X-Forwarded-Preferred-Username': response.headers.get('X-Forwarded-Preferred-Username'),
        'X-User-Name': response.headers.get('X-User-Name'),
        'X-Forwarded-Groups': response.headers.get('X-Forwarded-Groups')
      };
      
      if (config.isDevelopment) {
        console.log('🔍 All OAuth2-proxy headers:', allHeaders);
        console.log('🎯 Selected values:', {
          rawEmail,
          email: email || '(invalid/missing)',
          username,
          displayName,
          finalName: username || displayName || (email ? email.split('@')[0] : undefined)
        });
      }
      
      if (email) {
        return {
          email,
          // Priority: username > displayName > validated email local-part
          name: username || displayName || email.split('@')[0],
          groups: response.headers.get('X-Forwarded-Groups')?.split(',').map(g => g.trim()).filter(g => g) || [],
        };
      }

      // If we have username but no valid email, still return user info
      if (username) {
        return {
          email: 'unknown@user.com', // Fallback email since username exists
          name: username || displayName || 'Authenticated User',
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
    
    if (config.isDevelopment) {
      console.log('🔐 OAuth Login Debug:');
      console.log('  - Current location:', window.location.href);
      console.log('  - Current path:', currentPath);
      console.log('  - Window origin:', window.location.origin);
      console.log('  - Return URL (unencoded):', returnUrl);
      console.log('  - Return URL (encoded):', encodeURIComponent(returnUrl));
      console.log('  - Full login URL:', loginUrl);
      console.log('  - DEV mode:', import.meta.env.DEV);
    }
    
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
    
    if (config.isDevelopment) {
      console.log('🚪 Redirecting to logout URL:', logoutUrl);
      console.log('🚪 Environment:', import.meta.env.DEV ? 'development' : 'production');
    }
    window.location.href = logoutUrl;
  }

  /**
   * Handle authentication error (401) by redirecting to login
   */
  handleAuthError(): void {
    // Only prevent redirect if we're actually on an OAuth2 proxy page
    const currentUrl = new URL(window.location.href);
    
    // Check if we're on OAuth2 proxy paths (pathname-based detection)
    const isOAuthPath = currentUrl.pathname.startsWith('/oauth2/sign_in') || 
                       currentUrl.pathname.startsWith('/oauth2/callback');
    
    // Optional host validation if oauthProxyUrl is configured
    let isCorrectHost = true;
    if (config.oauthProxyUrl) {
      try {
        const proxyUrl = new URL(config.oauthProxyUrl);
        isCorrectHost = proxyUrl.host === currentUrl.host;
      } catch {
        // If oauthProxyUrl is invalid, skip host validation
        isCorrectHost = true;
      }
    }
    
    const isOAuthProxyUrl = isOAuthPath && isCorrectHost;
    
    if (config.isDevelopment) {
      console.log('handleAuthError called:', {
        currentUrl: currentUrl.href,
        pathname: currentUrl.pathname,
        search: currentUrl.search,
        host: currentUrl.host,
        isOAuthPath,
        isCorrectHost,
        isOAuthProxyUrl,
        oauthProxyUrl: config.oauthProxyUrl
      });
    }

    if (isOAuthProxyUrl) {
      console.warn('Already on OAuth proxy login/callback page, not redirecting to avoid loop');
      return;
    }

    console.log('Authentication required - redirecting to OAuth login');
    this.redirectToLogin();
  }
}

export const authService = AuthService.getInstance();
