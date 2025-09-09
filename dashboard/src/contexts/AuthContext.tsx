import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';

interface User {
  sub: string;
  username: string;
  email: string;
  avatar_url: string;
  exp: number;
}

interface AuthContextData {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (redirectUrl?: string) => void;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  getTokenForWebSocket: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextData | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Authentication provider that manages cookie-based authentication state
 * 
 * EP-0017 Implementation:
 * - Uses HTTP-only cookies for secure authentication
 * - Automatically checks auth status on app load
 * - Provides token extraction for WebSocket connections
 * - Handles login redirects with state-encoded URLs
 * - No JWT token storage in JavaScript (security by design)
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  /**
   * Check if user is authenticated by trying to get JWT token from cookie
   * Uses direct fetch to avoid 401 redirect loops from axios interceptor
   */
  const checkAuth = async () => {
    try {
      setLoading(true);
      
      // Try to get JWT token from HTTP-only cookie
      // This endpoint will return 401 if not authenticated, but won't trigger redirect
      const tokenResponse = await fetch('/auth/token', {
        credentials: 'include' // Include HTTP-only cookies
      });
      
      if (tokenResponse.ok) {
        const tokenData = await tokenResponse.json();
        const token = tokenData.access_token;
        
        // Decode JWT token to extract user info
        // Using simple base64 decode since we don't need signature verification on frontend
        const payload = JSON.parse(atob(token.split('.')[1]));
        
        const userData: User = {
          sub: payload.sub,
          username: payload.username,
          email: payload.email,
          avatar_url: payload.avatar_url,
          exp: payload.exp
        };
        
        // Check if token is expired
        const isExpired = Date.now() / 1000 > userData.exp;
        if (isExpired) {
          console.log('🔒 JWT token is expired, clearing auth state');
          setUser(null);
        } else {
          console.log('✅ User authenticated:', userData.username);
          setUser(userData);
        }
      } else if (tokenResponse.status === 401) {
        // Not authenticated - this is expected for unauthenticated users
        console.log('🔒 No valid authentication cookie found');
        setUser(null);
      } else {
        // Other error
        console.log('🔒 Auth token check failed with status:', tokenResponse.status);
        setUser(null);
      }
    } catch (error) {
      console.log('🔒 Authentication check failed, user not authenticated:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Initiate login by redirecting to backend OAuth endpoint
   */
  const login = (redirectUrl?: string) => {
    console.log('🔑 AuthContext.login() called with redirectUrl:', redirectUrl);
    
    const currentUrl = window.location.href;
    const targetRedirectUrl = redirectUrl || currentUrl;
    
    console.log('🔑 Current URL:', currentUrl);
    console.log('🔑 Target redirect URL:', targetRedirectUrl);
    
    const loginUrl = `/auth/login?redirect_url=${encodeURIComponent(targetRedirectUrl)}`;
    console.log('🔑 About to redirect to:', loginUrl);
    
    try {
      // Redirect to backend login endpoint with encoded redirect URL
      window.location.href = loginUrl;
      console.log('🔑 Redirect initiated successfully');
    } catch (error) {
      console.error('❌ Error during redirect:', error);
    }
  };

  /**
   * Logout by calling backend logout endpoint and clearing auth state
   */
  const logout = async () => {
    try {
      console.log('🚪 Logging out user:', user?.username);
      
      // Call backend logout endpoint to clear HTTP-only cookie
      await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'include'
      });
      
      // Clear auth state
      setUser(null);
      
      console.log('✅ User logged out successfully');
      
      // Optionally redirect to home page
      window.location.href = '/';
    } catch (error) {
      console.error('❌ Logout failed:', error);
      // Clear local state anyway
      setUser(null);
    }
  };

  /**
   * Get JWT token for programmatic clients (optional fallback)
   * 
   * Note: WebSockets now support HTTP-only cookies directly via handshake headers,
   * so this is mainly for programmatic clients that need Authorization headers.
   */
  const getTokenForWebSocket = async (): Promise<string | null> => {
    try {
      const response = await fetch('/auth/token', {
        credentials: 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        return data.access_token;
      } else {
        console.error('❌ Failed to get token for WebSocket fallback:', response.status);
        return null;
      }
    } catch (error) {
      console.error('❌ Error getting token for WebSocket fallback:', error);
      return null;
    }
  };

  // Check authentication status on app load
  useEffect(() => {
    console.log('🔍 Checking initial authentication status...');
    checkAuth();
  }, []);

  // WebSocket uses HTTP-only cookies automatically - no token provider needed

  const contextValue: AuthContextData = {
    user,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    checkAuth,
    getTokenForWebSocket
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to use the authentication context
 */
export function useAuth(): AuthContextData {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

/**
 * Hook for checking authentication status with automatic redirects
 */
export function useRequireAuth() {
  const { user, loading, login } = useAuth();

  useEffect(() => {
    // Don't redirect if we're already on login or auth pages
    const isOnAuthPage = window.location.pathname === '/login' || window.location.pathname.includes('/auth/');
    
    // If not loading, no user, and not on auth page, redirect to login
    if (!loading && !user && !isOnAuthPage) {
      console.log('🔒 Authentication required, redirecting to login...');
      login();
    }
  }, [user, loading, login]);

  return { user, loading, isAuthenticated: !!user };
}
