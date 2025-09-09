/**
 * Authentication service for handling OAuth2 Proxy authentication flow
 */

export interface AuthUser {
  email: string;
  name?: string;
  groups?: string[];
}

class AuthService {
  private static instance: AuthService;
  private readonly OAUTH_PROXY_BASE = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:4180');

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
   * Get current user info from OAuth2 proxy headers (if available)
   * This would need to be implemented based on your OAuth provider
   */
  async getCurrentUser(): Promise<AuthUser | null> {
    try {
      // OAuth2 proxy typically passes user info via headers
      // Use a protected endpoint to ensure authentication and get user headers
      const response = await fetch('/api/v1/history/active-sessions', {
        method: 'GET', 
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        },
      });

      if (!response.ok) {
        return null;
      }

      // Extract user info from headers if available
      const email = response.headers.get('X-Forwarded-User') || 
                   response.headers.get('X-Forwarded-Email');
      
      if (email) {
        return {
          email,
          name: response.headers.get('X-Forwarded-Preferred-Username') || email,
          groups: response.headers.get('X-Forwarded-Groups')?.split(',') || [],
        };
      }

      return null;
    } catch (error) {
      console.warn('Failed to get current user:', error);
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
    const logoutUrl = `${this.OAUTH_PROXY_BASE}/oauth2/sign_out`;
    window.location.href = logoutUrl;
  }

  /**
   * Handle authentication error (401) by redirecting to login
   */
  handleAuthError(): void {
    // Only prevent redirect if we're actually on an OAuth2 proxy page
    const currentUrl = window.location.href;
    const isOAuthProxyUrl = currentUrl.includes('localhost:4180') && 
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
