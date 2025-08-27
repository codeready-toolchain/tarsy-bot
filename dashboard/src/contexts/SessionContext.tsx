import { createContext, useContext, useState, useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { apiClient, handleAPIError } from '../services/api';
import type { DetailedSession } from '../types';

interface SessionContextData {
  session: DetailedSession | null;
  loading: boolean;
  error: string | null;
  fetchSessionDetail: (sessionId: string, forceRefresh?: boolean) => Promise<void>;
  updateSession: (updater: (prev: DetailedSession | null) => DetailedSession | null) => void;
  clearSession: () => void;
}

const SessionContext = createContext<SessionContextData | null>(null);

interface SessionProviderProps {
  children: ReactNode;
}

/**
 * Session provider that caches and shares session data between reasoning and debug tabs
 * Prevents duplicate API calls when switching between tabs for the same session
 */
export function SessionProvider({ children }: SessionProviderProps) {
  const [session, setSession] = useState<DetailedSession | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [cachedSessionId, setCachedSessionId] = useState<string | null>(null);

  /**
   * Fetch session detail with intelligent caching
   * Only makes API call if:
   * - Session ID is different from cached one
   * - Force refresh is requested
   * - No session data exists
   */
  const fetchSessionDetail = async (sessionId: string, forceRefresh: boolean = false) => {
    // Skip fetch if we already have this session cached and no force refresh
    if (!forceRefresh && cachedSessionId === sessionId && session) {
      console.log(`🎯 [SessionContext] ✅ CACHE HIT - Using cached session data for ${sessionId}, no API call needed!`);
      return;
    }

    const startTime = performance.now();
    
    try {
      setLoading(true);
      setError(null);
      console.log(`🚀 [SessionContext] 📡 API CALL #${Date.now()} - Fetching session detail for ID: ${sessionId}`, {
        forceRefresh,
        currentCachedId: cachedSessionId,
        hasSession: !!session,
        stack: new Error().stack?.split('\n').slice(1, 4).join('\n  ')
      });
      
      const sessionData = await apiClient.getSessionDetail(sessionId);
      
      // Validate and normalize session status
      const normalizedStatus = ['completed', 'failed', 'in_progress', 'pending'].includes(sessionData.status) 
        ? sessionData.status 
        : 'in_progress';
      
      const normalizedSession = {
        ...sessionData,
        status: normalizedStatus as 'completed' | 'failed' | 'in_progress' | 'pending'
      };
      
      setSession(normalizedSession);
      setCachedSessionId(sessionId);
      
      const loadTime = performance.now() - startTime;
      console.log(`✅ [SessionContext] 💾 Session fetched and cached successfully:`, {
        sessionId,
        loadTime: `${loadTime.toFixed(2)}ms`,
        stages: normalizedSession.stages?.length || 0,
        status: normalizedSession.status,
        message: 'Subsequent tab switches will use cache!'
      });
      
    } catch (err) {
      const errorMessage = handleAPIError(err);
      setError(errorMessage);
      console.error(`❌ [SessionContext] Failed to fetch session:`, err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Update session state with a function (for WebSocket updates, etc.)
   */
  const updateSession = (updater: (prev: DetailedSession | null) => DetailedSession | null) => {
    setSession(updater);
  };

  /**
   * Clear cached session data (useful for navigation cleanup)
   */
  const clearSession = () => {
    console.log(`🧹 [SessionContext] Clearing cached session data`);
    setSession(null);
    setCachedSessionId(null);
    setError(null);
    setLoading(false);
  };

  const contextValue: SessionContextData = {
    session,
    loading,
    error,
    fetchSessionDetail,
    updateSession,
    clearSession
  };

  return (
    <SessionContext.Provider value={contextValue}>
      {children}
    </SessionContext.Provider>
  );
}

/**
 * Hook to use the session context
 * Throws error if used outside SessionProvider
 */
export function useSessionContext(): SessionContextData {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSessionContext must be used within a SessionProvider');
  }
  return context;
}

/**
 * Hook for specific session management with automatic cleanup
 * This is the main hook that components should use
 * StrictMode-safe: Prevents duplicate calls during React StrictMode double-invocation
 */
export function useSession(sessionId: string | undefined) {
  const {
    session,
    loading,
    error,
    fetchSessionDetail,
    updateSession,
    clearSession
  } = useSessionContext();

  // Track the last session ID we fetched to prevent StrictMode duplicates
  const lastFetchedRef = useRef<string | null>(null);

  // Fetch session when sessionId changes - StrictMode safe
  useEffect(() => {
    if (sessionId) {
      // Only fetch if we haven't already fetched this session ID
      if (lastFetchedRef.current !== sessionId) {
        console.log(`🎯 [useSession] Initiating fetch for session: ${sessionId}`);
        lastFetchedRef.current = sessionId;
        fetchSessionDetail(sessionId);
      } else {
        console.log(`🛡️ [useSession] StrictMode protection - already fetched session: ${sessionId}`);
      }
    } else {
      // Clear session if no sessionId provided
      clearSession();
      lastFetchedRef.current = null;
    }
  }, [sessionId]);

  // Return session data and utilities
  return {
    session: sessionId && session?.session_id === sessionId ? session : null,
    loading,
    error: sessionId ? error : 'Session ID not provided',
    refetch: () => {
      if (sessionId) {
        lastFetchedRef.current = null; // Reset so refetch will work
        return fetchSessionDetail(sessionId, true);
      }
      return Promise.resolve();
    },
    updateSession
  };
}
