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
  // Granular update methods for WebSocket updates
  refreshSessionSummary: (sessionId: string) => Promise<void>;
  refreshSessionStages: (sessionId: string) => Promise<void>;
  updateFinalAnalysis: (analysis: string) => void;
  updateSessionStatus: (newStatus: DetailedSession['status'], errorMessage?: string) => void;
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

  /**
   * Lightweight refresh of session summary statistics only
   */
  const refreshSessionSummary = async (sessionId: string) => {
    try {
      console.log('🔄 [SessionContext] Refreshing session summary statistics for:', sessionId);
      const summaryData = await apiClient.getSessionSummary(sessionId);
      
      setSession(prevSession => {
        if (!prevSession || prevSession.session_id !== sessionId) return prevSession;
        
        console.log('📊 [SessionContext] Updating session summary with fresh data:', summaryData);
        return {
          ...prevSession,
          // Update main session count fields that SessionHeader uses
          llm_interaction_count: summaryData.llm_interactions,
          mcp_communication_count: summaryData.mcp_communications,
          total_interactions: summaryData.total_interactions,
          // Update other relevant fields from summary
          total_stages: summaryData.chain_statistics?.total_stages || prevSession.total_stages,
          completed_stages: summaryData.chain_statistics?.completed_stages || prevSession.completed_stages,
          failed_stages: summaryData.chain_statistics?.failed_stages || prevSession.failed_stages,
          // Update token usage fields
          session_input_tokens: summaryData.session_input_tokens || prevSession.session_input_tokens,
          session_output_tokens: summaryData.session_output_tokens || prevSession.session_output_tokens,
          session_total_tokens: summaryData.session_total_tokens || prevSession.session_total_tokens
        };
      });
      
    } catch (error) {
      console.error('❌ [SessionContext] Failed to refresh session summary:', error);
    }
  };

  /**
   * Partial update for session stages (avoids full page refresh)
   */
  const refreshSessionStages = async (sessionId: string) => {
    try {
      console.log('🔄 [SessionContext] Refreshing session stages for:', sessionId);
      const sessionData = await apiClient.getSessionDetail(sessionId);
      
      setSession(prevSession => {
        if (!prevSession || prevSession.session_id !== sessionId) return prevSession;
        
        // Only update if stages have actually changed
        const stagesChanged = JSON.stringify(prevSession.stages) !== JSON.stringify(sessionData.stages);
        const analysisChanged = prevSession.final_analysis !== sessionData.final_analysis;
        const statusChanged = prevSession.status !== sessionData.status;
        
        if (!stagesChanged && !analysisChanged && !statusChanged) {
          console.log('📊 [SessionContext] No stage changes detected, skipping update');
          return prevSession;
        }
        
        console.log('📊 [SessionContext] Updating session stages and analysis:', { stagesChanged, analysisChanged, statusChanged });
        return {
          ...prevSession,
          stages: sessionData.stages,
          final_analysis: sessionData.final_analysis,
          status: sessionData.status as typeof prevSession.status,
          error_message: sessionData.error_message,
          // Update token usage fields from full session data
          session_input_tokens: sessionData.session_input_tokens ?? prevSession.session_input_tokens,
          session_output_tokens: sessionData.session_output_tokens ?? prevSession.session_output_tokens,
          session_total_tokens: sessionData.session_total_tokens ?? prevSession.session_total_tokens
        };
      });
      
    } catch (error) {
      console.error('❌ [SessionContext] Failed to refresh session stages:', error);
    }
  };

  /**
   * Direct update of final analysis (no API call needed)
   */
  const updateFinalAnalysis = (analysis: string) => {
    console.log('🎯 [SessionContext] Updating final analysis directly');
    setSession(prevSession => {
      if (!prevSession) return prevSession;
      if (prevSession.final_analysis === analysis) {
        console.log('🎯 [SessionContext] Analysis unchanged, skipping update');
        return prevSession;
      }
      return {
        ...prevSession,
        final_analysis: analysis
      };
    });
  };

  /**
   * Direct update of session status (no API call needed)
   */
  const updateSessionStatus = (newStatus: DetailedSession['status'], errorMessage?: string) => {
    console.log('🔄 [SessionContext] Updating session status directly:', newStatus);
    setSession(prevSession => {
      if (!prevSession) return prevSession;
      if (prevSession.status === newStatus && prevSession.error_message === errorMessage) {
        console.log('🔄 [SessionContext] Status unchanged, skipping update');
        return prevSession;
      }
      return {
        ...prevSession,
        status: newStatus,
        error_message: errorMessage || prevSession.error_message
      };
    });
  };

  const contextValue: SessionContextData = {
    session,
    loading,
    error,
    fetchSessionDetail,
    updateSession,
    clearSession,
    // Granular update methods
    refreshSessionSummary,
    refreshSessionStages,
    updateFinalAnalysis,
    updateSessionStatus
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
    clearSession,
    refreshSessionSummary,
    refreshSessionStages,
    updateFinalAnalysis,
    updateSessionStatus
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
    updateSession,
    // Granular update methods
    refreshSessionSummary: (forceSessionId?: string) => {
      const targetId = forceSessionId || sessionId;
      return targetId ? refreshSessionSummary(targetId) : Promise.resolve();
    },
    refreshSessionStages: (forceSessionId?: string) => {
      const targetId = forceSessionId || sessionId;
      return targetId ? refreshSessionStages(targetId) : Promise.resolve();
    },
    updateFinalAnalysis,
    updateSessionStatus
  };
}
