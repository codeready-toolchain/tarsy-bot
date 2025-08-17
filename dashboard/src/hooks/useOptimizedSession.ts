import { useState, useEffect, useMemo } from 'react';
import { apiClient } from '../services/api';
import type { DetailedSession } from '../types';

interface UseOptimizedSessionOptions {
  sessionId: string;
  autoOptimize?: boolean;
  interactionThreshold?: number;
  sizeThreshold?: number; // in bytes
}

interface OptimizedSessionData {
  session: DetailedSession | null;
  loading: boolean;
  error: string | null;
  performanceMetrics: {
    totalInteractions: number;
    stagesCount: number;
    estimatedSize: number;
    largestStage: number;
    loadTime: number | null;
    shouldOptimize: boolean;
    recommendations: string[];
  } | null;
  retry: () => void;
}

/**
 * Custom hook for optimized session data loading with performance metrics
 */
export function useOptimizedSession({
  sessionId,
  interactionThreshold = 50,
  sizeThreshold = 100000 // 100KB
}: Omit<UseOptimizedSessionOptions, 'autoOptimize'>): OptimizedSessionData {
  const [session, setSession] = useState<DetailedSession | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [loadTime, setLoadTime] = useState<number | null>(null);

  // Calculate performance metrics
  const performanceMetrics = useMemo(() => {
    if (!session) return null;

    const totalInteractions = session.stages?.reduce(
      (total, stage) => total + ((stage.llm_interactions?.length || 0) + (stage.mcp_communications?.length || 0)),
      0
    ) || 0;

    const stagesCount = session.stages?.length || 0;

    const largestStage = session.stages?.reduce((max, stage) => {
      const stageInteractions = (stage.llm_interactions?.length || 0) + (stage.mcp_communications?.length || 0);
      return stageInteractions > max ? stageInteractions : max;
    }, 0) || 0;

    // Estimate content size
    let estimatedSize = 0;
    session.stages?.forEach(stage => {
      // Estimate LLM interaction sizes
      stage.llm_interactions?.forEach(interaction => {
        if (interaction.details?.messages) {
          estimatedSize += JSON.stringify(interaction.details.messages).length;
        }
      });
      
      // Estimate MCP interaction sizes
      stage.mcp_communications?.forEach(interaction => {
        if (interaction.details?.result) {
          estimatedSize += JSON.stringify(interaction.details.result).length;
        }
        if (interaction.details?.parameters) {
          estimatedSize += JSON.stringify(interaction.details.parameters).length;
        }
      });
    });

    // Add session metadata size
    estimatedSize += JSON.stringify(session.alert_data || {}).length;
    estimatedSize += (session.final_analysis || '').length;

    const shouldOptimize = totalInteractions > interactionThreshold || estimatedSize > sizeThreshold;

    // Generate recommendations
    const recommendations: string[] = [];
    
    if (totalInteractions > 200) {
      recommendations.push('Use virtualized rendering for interactions');
    }
    if (totalInteractions > 100) {
      recommendations.push('Enable lazy loading for interaction details');
    }
    if (estimatedSize > 500000) { // 500KB
      recommendations.push('Consider content truncation with expand options');
    }
    if (largestStage > 50) {
      recommendations.push('Use progressive disclosure for large stages');
    }
    if (stagesCount > 10) {
      recommendations.push('Consider stage pagination or virtualization');
    }

    return {
      totalInteractions,
      stagesCount,
      estimatedSize,
      largestStage,
      loadTime,
      shouldOptimize,
      recommendations
    };
  }, [session, loadTime, interactionThreshold, sizeThreshold]);

  // Fetch session data with performance tracking
  const fetchSession = async () => {
    const startTime = performance.now();
    
    try {
      setLoading(true);
      setError(null);
      
      console.log(`🚀 [useOptimizedSession] Fetching session ${sessionId}`);
      
      const sessionData = await apiClient.getSessionDetail(sessionId);
      
      // Normalize session status
      const normalizedSession = {
        ...sessionData,
        status: (['completed', 'failed', 'in_progress', 'pending'].includes(sessionData.status) 
          ? sessionData.status 
          : 'in_progress') as 'completed' | 'failed' | 'in_progress' | 'pending'
      };
      
      setSession(normalizedSession);
      
      const endTime = performance.now();
      const duration = endTime - startTime;
      setLoadTime(duration);
      
      console.log(`✅ [useOptimizedSession] Session loaded in ${duration.toFixed(2)}ms`);
      
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to load session';
      setError(errorMessage);
      console.error(`❌ [useOptimizedSession] Failed to fetch session:`, err);
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    if (sessionId) {
      fetchSession();
    } else {
      setError('Session ID not provided');
      setLoading(false);
    }
  }, [sessionId]);

  // Log performance recommendations
  useEffect(() => {
    if (performanceMetrics && performanceMetrics.recommendations.length > 0) {
      console.log(`📊 [useOptimizedSession] Performance recommendations for session ${sessionId}:`);
      performanceMetrics.recommendations.forEach((rec, index) => {
        console.log(`  ${index + 1}. ${rec}`);
      });
    }
  }, [performanceMetrics, sessionId]);

  return {
    session,
    loading,
    error,
    performanceMetrics,
    retry: fetchSession
  };
}

/**
 * Hook for monitoring session performance in development
 */
export function useSessionPerformanceMonitor(sessionId: string) {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return;

    const observer = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      entries.forEach((entry) => {
        if (entry.name.includes('session-detail') || entry.name.includes(sessionId)) {
          console.log(`🔍 [Performance] ${entry.name}: ${entry.duration.toFixed(2)}ms`);
        }
      });
    });

    observer.observe({ entryTypes: ['measure'] });

    return () => {
      observer.disconnect();
    };
  }, [sessionId]);
}

/**
 * Hook for adaptive rendering based on session size
 */
export function useAdaptiveRendering(performanceMetrics: any) {
  const [renderingStrategy, setRenderingStrategy] = useState<'standard' | 'optimized' | 'minimal'>('standard');

  useEffect(() => {
    if (!performanceMetrics) return;

    const { totalInteractions, estimatedSize, largestStage } = performanceMetrics;

    if (totalInteractions > 200 || estimatedSize > 500000) {
      setRenderingStrategy('minimal');
    } else if (totalInteractions > 50 || estimatedSize > 100000 || largestStage > 30) {
      setRenderingStrategy('optimized');
    } else {
      setRenderingStrategy('standard');
    }
  }, [performanceMetrics]);

  return {
    renderingStrategy,
    useVirtualization: renderingStrategy !== 'standard',
    useLazyLoading: renderingStrategy === 'optimized' || renderingStrategy === 'minimal',
    useContentTruncation: renderingStrategy === 'minimal',
    maxPreviewLength: renderingStrategy === 'minimal' ? 500 : renderingStrategy === 'optimized' ? 1000 : 2000
  };
}
