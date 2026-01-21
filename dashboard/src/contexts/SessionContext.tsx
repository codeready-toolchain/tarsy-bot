import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import type { ReactNode } from 'react';
import { apiClient, handleAPIError } from '../services/api';
import type { DetailedSession, Session, StageExecution } from '../types';
import { isValidSessionStatus, SESSION_STATUS, type StageStatus } from '../utils/statusConstants';
import {
  createParallelPlaceholders,
  replacePlaceholderWithRealStage
} from '../utils/parallelPlaceholders';

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
  updateStageStatus: (stageId: string, status: StageStatus, errorMessage?: string | null, completedAtUs?: number | null) => void;
  // Placeholder management for parallel stages
  handleParallelStageStarted: (stageExecution: StageExecution) => void;
  handleParallelChildStageStarted: (stageExecution: StageExecution) => void;
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
  const fetchSessionDetail = useCallback(async (sessionId: string, forceRefresh: boolean = false) => {
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
      const normalizedStatus = isValidSessionStatus(sessionData.status)
        ? sessionData.status 
        : SESSION_STATUS.IN_PROGRESS;
      
      const normalizedSession = {
        ...sessionData,
        status: normalizedStatus as Session['status']
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
  }, [cachedSessionId, session, setSession, setLoading, setError, setCachedSessionId]);

  /**
   * Update session state with a function (for WebSocket updates, etc.)
   */
  const updateSession = useCallback((updater: (prev: DetailedSession | null) => DetailedSession | null) => {
    setSession(updater);
  }, [setSession]);

  /**
   * Clear cached session data (useful for navigation cleanup)
   */
  const clearSession = useCallback(() => {
    console.log(`🧹 [SessionContext] Clearing cached session data`);
    setSession(null);
    setCachedSessionId(null);
    setError(null);
    setLoading(false);
  }, [setSession, setCachedSessionId, setError, setLoading]);

  /**
   * Lightweight refresh of session summary statistics only
   */
  const refreshSessionSummary = useCallback(async (sessionId: string) => {
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
  }, [setSession]);

  /**
   * Partial update for session stages (avoids full page refresh)
   */
  const refreshSessionStages = useCallback(async (sessionId: string) => {
    try {
      console.log('🔄 [SessionContext] Refreshing session stages for:', sessionId);
      const sessionData = await apiClient.getSessionDetail(sessionId);
      
      setSession(prevSession => {
        if (!prevSession || prevSession.session_id !== sessionId) return prevSession;
        
        // Only update if stages have actually changed
        const stagesChanged = JSON.stringify(prevSession.stages) !== JSON.stringify(sessionData.stages);
        const analysisChanged = prevSession.final_analysis !== sessionData.final_analysis;
        const summaryChanged = prevSession.final_analysis_summary !== sessionData.final_analysis_summary;
        const statusChanged = prevSession.status !== sessionData.status;
        const pauseMetadataChanged = JSON.stringify(prevSession.pause_metadata) !== JSON.stringify(sessionData.pause_metadata);
        
        if (!stagesChanged && !analysisChanged && !summaryChanged && !statusChanged && !pauseMetadataChanged) {
          console.log('📊 [SessionContext] No stage changes detected, skipping update');
          return prevSession;
        }
        
        console.log('📊 [SessionContext] Updating session stages and analysis:', { 
          stagesChanged, 
          analysisChanged,
          summaryChanged,
          statusChanged,
          pauseMetadataChanged 
        });
        return {
          ...prevSession,
          stages: sessionData.stages,
          final_analysis: sessionData.final_analysis,
          final_analysis_summary: sessionData.final_analysis_summary,
          status: sessionData.status as typeof prevSession.status,
          error_message: sessionData.error_message,
          pause_metadata: sessionData.pause_metadata,
          // Update token usage fields from full session data
          session_input_tokens: sessionData.session_input_tokens ?? prevSession.session_input_tokens,
          session_output_tokens: sessionData.session_output_tokens ?? prevSession.session_output_tokens,
          session_total_tokens: sessionData.session_total_tokens ?? prevSession.session_total_tokens
        };
      });
      
    } catch (error) {
      console.error('❌ [SessionContext] Failed to refresh session stages:', error);
    }
  }, [setSession]);

  /**
   * Direct update of final analysis (no API call needed)
   */
  const updateFinalAnalysis = useCallback((analysis: string) => {
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
  }, [setSession]);

  /**
   * Direct update of session status (no API call needed)
   */
  const updateSessionStatus = useCallback((newStatus: DetailedSession['status'], errorMessage?: string) => {
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
        error_message: errorMessage ?? prevSession.error_message
      };
    });
  }, [setSession]);

  /**
   * Handle parallel parent stage started event - inject placeholders immediately
   */
  const handleParallelStageStarted = useCallback((stageExecution: StageExecution) => {
    console.log('🚀 [SessionContext] Parallel parent stage started, injecting placeholders:', {
      execution_id: stageExecution.execution_id,
      parallel_type: stageExecution.parallel_type,
      expected_count: stageExecution.expected_parallel_count
    });

    setSession(prevSession => {
      if (!prevSession) return prevSession;

      const expectedCount = stageExecution.expected_parallel_count || 0;
      if (expectedCount <= 0) {
        console.warn('🚫 [SessionContext] No expected_parallel_count for parallel stage, skipping placeholders');
        return prevSession;
      }

      // Create placeholders for expected parallel children
      const placeholders = createParallelPlaceholders(stageExecution, expectedCount);
      
      // Insert parent stage and placeholders at the correct position
      const updatedStages = [...(prevSession.stages || [])];
      
      // Find insertion point for parent stage (by stage_index)
      const insertIndex = updatedStages.findIndex(
        s => s.stage_index > stageExecution.stage_index
      );
      
      if (insertIndex === -1) {
        // Add at end
        updatedStages.push(stageExecution, ...placeholders);
      } else {
        // Insert before the next stage
        updatedStages.splice(insertIndex, 0, stageExecution, ...placeholders);
      }

      console.log(`✅ [SessionContext] Injected ${placeholders.length} placeholders for parallel stage`);
      
      return {
        ...prevSession,
        stages: updatedStages
      };
    });
  }, [setSession]);

  /**
   * Handle parallel child stage started event - replace placeholder with real data
   */
  const handleParallelChildStageStarted = useCallback((stageExecution: StageExecution) => {
    console.log('🔄 [SessionContext] Parallel child stage started, replacing placeholder:', {
      execution_id: stageExecution.execution_id,
      parent_id: stageExecution.parent_stage_execution_id,
      parallel_index: stageExecution.parallel_index
    });

    setSession(prevSession => {
      if (!prevSession) return prevSession;

      const updatedStages = replacePlaceholderWithRealStage(
        prevSession.stages || [],
        stageExecution
      );

      return {
        ...prevSession,
        stages: updatedStages
      };
    });
  }, [setSession]);

  /**
   * Update a specific stage's status and error message from WebSocket event
   * This avoids a full API refresh and prevents race conditions
   */
  const updateStageStatus = useCallback((
    stageId: string, 
    status: StageStatus, 
    errorMessage?: string | null,
    completedAtUs?: number | null
  ) => {
    console.log('🔄 [SessionContext] Updating stage status from WebSocket:', {
      stageId,
      status,
      errorMessage,
      completedAtUs
    });

    setSession(prevSession => {
      
      if (!prevSession) return prevSession;
      
      // CRITICAL: If stages array is empty, skip this update and let the API refresh handle it
      // WebSocket events can arrive before initial session data loads, causing updates to stale state
      if (!prevSession.stages || prevSession.stages.length === 0) {
        console.log('⏭️ [SessionContext] Skipping WebSocket stage update - session data not loaded yet');
        return prevSession;
      }

      let stageFound = false;

      // Helper function to update stage recursively (handles nested parallel stages)
      const updateStageRecursive = (stages: StageExecution[]): StageExecution[] => {
        return stages.map(stage => {
          // Check if this is the stage we're looking for
          if (stage.execution_id === stageId) {
            stageFound = true;
            return {
              ...stage,
              status: status,
              error_message: errorMessage ?? stage.error_message,
              completed_at_us: completedAtUs ?? stage.completed_at_us
            };
          }

          // Check nested parallel executions
          if (stage.parallel_executions && stage.parallel_executions.length > 0) {
            return {
              ...stage,
              parallel_executions: updateStageRecursive(stage.parallel_executions)
            };
          }

          return stage;
        });
      };

      const updatedStages = updateStageRecursive(prevSession.stages || []);
      
      // If stage wasn't found, skip this update - let the API refresh handle it
      // This prevents creating inconsistent state when WebSocket arrives before API data
      if (!stageFound) {
        console.log('⏭️ [SessionContext] Skipping WebSocket stage update - stage not found yet (will be handled by API refresh)');
        return prevSession;
      }

      return {
        ...prevSession,
        stages: updatedStages
      };
    });
  }, [setSession]);

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
    updateSessionStatus,
    updateStageStatus,
    // Placeholder management
    handleParallelStageStarted,
    handleParallelChildStageStarted
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
    updateSessionStatus,
    updateStageStatus,
    handleParallelStageStarted,
    handleParallelChildStageStarted
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
    updateSessionStatus,
    updateStageStatus,
    handleParallelStageStarted,
    handleParallelChildStageStarted
  };
}
