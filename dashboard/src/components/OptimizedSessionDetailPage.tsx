import React, { useState, useEffect, useRef, lazy, Suspense, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Container, 
  AppBar, 
  Toolbar, 
  IconButton, 
  Typography, 
  Box, 
  Paper, 
  Alert, 
  CircularProgress,
  Skeleton,
  Switch,
  FormControlLabel,
  Chip
} from '@mui/material';
import { ArrowBack, Speed } from '@mui/icons-material';
import { apiClient, handleAPIError } from '../services/api';
import { webSocketService } from '../services/websocket';
import type { DetailedSession } from '../types';

// Lazy load heavy components
const SessionHeader = lazy(() => import('./SessionHeader'));
const OriginalAlertCard = lazy(() => import('./OriginalAlertCard'));
const FinalAnalysisCard = lazy(() => import('./FinalAnalysisCard'));
const NestedAccordionTimeline = lazy(() => import('./NestedAccordionTimeline'));
const VirtualizedAccordionTimeline = lazy(() => import('./VirtualizedAccordionTimeline'));

// Performance thresholds
const LARGE_SESSION_THRESHOLD = 50; // interactions
const VERY_LARGE_SESSION_THRESHOLD = 200; // interactions

// Helper function to compute total timeline length across all stages
const totalTimelineLength = (stages?: { llm_interactions?: any[], mcp_communications?: any[] }[]) =>
  stages?.reduce((total, stage) => total + ((stage.llm_interactions?.length || 0) + (stage.mcp_communications?.length || 0)), 0) || 0;

// Loading skeletons for different sections
const HeaderSkeleton = () => (
  <Paper sx={{ p: 3 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <Skeleton variant="circular" width={40} height={40} />
      <Box sx={{ flex: 1 }}>
        <Skeleton variant="text" width="60%" height={32} />
        <Skeleton variant="text" width="40%" height={20} />
      </Box>
      <Skeleton variant="text" width={100} height={24} />
    </Box>
  </Paper>
);

const AlertCardSkeleton = () => (
  <Paper sx={{ p: 3 }}>
    <Skeleton variant="text" width="30%" height={28} sx={{ mb: 2 }} />
    <Box sx={{ display: 'flex', gap: 3 }}>
      <Box sx={{ flex: 1 }}>
        <Skeleton variant="rectangular" height={200} />
      </Box>
      <Box sx={{ flex: 1 }}>
        <Skeleton variant="rectangular" height={200} />
      </Box>
    </Box>
  </Paper>
);

const TimelineSkeleton = () => (
  <Paper sx={{ p: 3 }}>
    <Skeleton variant="text" width="25%" height={28} sx={{ mb: 2 }} />
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {[1, 2, 3].map((i) => (
        <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Skeleton variant="circular" width={32} height={32} />
          <Box sx={{ flex: 1 }}>
            <Skeleton variant="text" width="70%" />
            <Skeleton variant="text" width="40%" />
          </Box>
        </Box>
      ))}
    </Box>
  </Paper>
);

/**
 * OptimizedSessionDetailPage component - Performance Optimized Version
 * Implements lazy loading, virtualization, and progressive disclosure for better performance
 */
function OptimizedSessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  
  // Session detail state
  const [session, setSession] = useState<DetailedSession | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Performance optimization settings
  const [useVirtualization, setUseVirtualization] = useState<boolean | null>(null); // null = auto-detect
  const [showPerformanceMode, setShowPerformanceMode] = useState<boolean>(false);

  // Performance metrics
  const performanceMetrics = useMemo(() => {
    if (!session) return null;

    const totalInteractions = totalTimelineLength(session.stages);
    const stagesCount = session.stages?.length || 0;
    const largestStage = session.stages?.reduce((max, stage) => {
      const stageInteractions = (stage.llm_interactions?.length || 0) + (stage.mcp_communications?.length || 0);
      return stageInteractions > max ? stageInteractions : max;
    }, 0) || 0;

    // Calculate estimated content size
    let estimatedSize = 0;
    session.stages?.forEach(stage => {
      stage.llm_interactions?.forEach(interaction => {
        if (interaction.details?.messages) {
          estimatedSize += JSON.stringify(interaction.details.messages).length;
        }
      });
      stage.mcp_communications?.forEach(interaction => {
        if (interaction.details) {
          estimatedSize += JSON.stringify(interaction.details).length;
        }
      });
    });

    return {
      totalInteractions,
      stagesCount,
      largestStage,
      estimatedSize,
      isLargeSession: totalInteractions > LARGE_SESSION_THRESHOLD,
      isVeryLargeSession: totalInteractions > VERY_LARGE_SESSION_THRESHOLD,
      recommendVirtualization: totalInteractions > LARGE_SESSION_THRESHOLD || estimatedSize > 100000
    };
  }, [session]);

  // Auto-detect performance settings
  useEffect(() => {
    if (performanceMetrics && useVirtualization === null) {
      setUseVirtualization(performanceMetrics.recommendVirtualization);
      setShowPerformanceMode(performanceMetrics.isLargeSession);
    }
  }, [performanceMetrics, useVirtualization]);

  // Ref to hold latest session to avoid stale closures in WebSocket handlers
  const sessionRef = useRef<DetailedSession | null>(null);
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  // Fetch just session summary statistics (lightweight)
  const refreshSessionSummary = async (id: string) => {
    try {
      console.log('🔄 Refreshing session summary statistics for:', id);
      const summaryData = await apiClient.getSessionSummary(id);
      
      setSession(prevSession => {
        if (!prevSession) return prevSession;
        
        console.log('📊 Updating session summary with fresh data:', summaryData);
        return {
          ...prevSession,
          // Update the summary field
          summary: summaryData,
          // Update main session count fields that SessionHeader uses
          llm_interaction_count: summaryData.llm_interactions,
          mcp_communication_count: summaryData.mcp_communications,
          total_interactions: summaryData.total_interactions,
          // Update other relevant fields from summary
          total_stages: summaryData.chain_statistics?.total_stages || prevSession.total_stages,
          completed_stages: summaryData.chain_statistics?.completed_stages || prevSession.completed_stages,
          failed_stages: summaryData.chain_statistics?.failed_stages || prevSession.failed_stages
        };
      });
      
    } catch (error) {
      console.error('Failed to refresh session summary:', error);
    }
  };

  // Fetch session detail data with performance tracking
  const fetchSessionDetail = async (id: string) => {
    const startTime = performance.now();
    
    try {
      setLoading(true);
      setError(null);
      console.log('🚀 Fetching session detail for ID:', id);
      
      const sessionData = await apiClient.getSessionDetail(id);
      
      // Validate and normalize session status
      const normalizedStatus = ['completed', 'failed', 'in_progress', 'pending'].includes(sessionData.status) 
        ? sessionData.status 
        : 'in_progress';
      
      const normalizedSession = {
        ...sessionData,
        status: normalizedStatus as 'completed' | 'failed' | 'in_progress' | 'pending'
      };
      
      setSession(normalizedSession);
      
      const loadTime = performance.now() - startTime;
      const totalInteractions = totalTimelineLength(normalizedSession.stages);
      
      console.log('✅ Session detail loaded:', {
        sessionId: id,
        loadTime: `${loadTime.toFixed(2)}ms`,
        totalInteractions,
        stages: normalizedSession.stages?.length || 0,
        status: normalizedSession.status
      });
      
      // Show performance warning for very large sessions
      if (totalInteractions > VERY_LARGE_SESSION_THRESHOLD) {
        console.warn(`⚠️ Very large session detected: ${totalInteractions} interactions. Consider using optimized rendering.`);
      }
      
    } catch (err) {
      const errorMessage = handleAPIError(err);
      setError(errorMessage);
      console.error('❌ Failed to fetch session detail:', err);
    } finally {
      setLoading(false);
    }
  };

  // WebSocket setup with granular updates to avoid full page refreshes
  useEffect(() => {
    if (!sessionId) return;

    console.log('🔌 Setting up WebSocket subscriptions for session:', sessionId);
    
    webSocketService.connect();
    webSocketService.subscribeToSessionChannel(sessionId);

    // Granular WebSocket handlers - update only relevant parts
    const handleSessionUpdate = (update: any) => {
      // The update data comes directly from WebSocket routing, not wrapped in SessionUpdate
      const updateType = update.type;
      const updateSessionId = update.session_id;
      console.log('📡 Session update received:', { type: updateType, sessionId: updateSessionId, keys: Object.keys(update) });
      
      if (updateSessionId === sessionId) {
        // Handle different update types granularly to avoid full page refreshes
        switch (updateType) {
          case 'llm_interaction':
          case 'mcp_interaction':
          case 'mcp_communication':
          case 'mcp_tool_list':
            // Timeline interaction updates - add to existing session data instead of full refresh
            console.log('📊 Timeline interaction update - adding to existing session data', {
              type: updateType, 
              stage_execution_id: update.stage_execution_id,
              request_id: update.request_id
            });
            setSession(prevSession => {
              if (!prevSession) return prevSession;
              
              // Try to find stage by execution_id first, then fallback to current stage
              let targetStageExecutionId = update.stage_execution_id;
              
              if (!targetStageExecutionId && prevSession.current_stage_index !== null) {
                // Fallback: use current stage if no stage_execution_id provided
                const currentStage = prevSession.stages?.[prevSession.current_stage_index];
                if (currentStage) {
                  targetStageExecutionId = currentStage.execution_id;
                  console.log('📊 No stage_execution_id found, using current stage:', targetStageExecutionId);
                }
              }
              
              if (!targetStageExecutionId || !prevSession.stages) {
                console.log('📊 No stage to update found, skipping granular update');
                return prevSession;
              }
              
              // Find and update the appropriate stage, or skip if not found
              let stageUpdated = false;
              const updatedStages = prevSession.stages.map(stage => {
                if (stage.execution_id === targetStageExecutionId) {
                  const updatedStage = { ...stage };
                  stageUpdated = true;
                  
                  if (updateType === 'llm_interaction') {
                    // Check for duplicates by event_id or request_id
                    const eventId = update.request_id || update.event_id;
                    const exists = stage.llm_interactions?.some(i => 
                      i.event_id === eventId || i.id === eventId
                    );
                    
                    if (!exists && eventId) {
                      // Create properly structured LLM interaction with complete details
                      const newInteraction = {
                        id: eventId,
                        event_id: eventId,
                        type: 'llm' as const,
                        timestamp_us: update.timestamp_us || Date.now() * 1000,
                        step_description: update.step_description || 'New LLM interaction',
                        duration_ms: update.duration_ms,
                        details: {
                          // Core LLM fields
                          model_name: update.model_name,
                          provider: update.provider,
                          token_usage: update.token_usage,
                          success: update.success,
                          error_message: update.error_message,
                          // Use complete conversation object
                          conversation: update.conversation,
                          // Include all other fields from update
                          ...update
                        }
                      };
                      
                      updatedStage.llm_interactions = [...(stage.llm_interactions || []), newInteraction];
                      updatedStage.llm_interaction_count = (updatedStage.llm_interaction_count || 0) + 1;
                      updatedStage.total_interactions = (updatedStage.total_interactions || 0) + 1;
                      console.log('📊 Added LLM interaction:', eventId, 'to stage:', targetStageExecutionId);
                    } else if (exists) {
                      console.log('📊 Duplicate LLM interaction detected, skipping:', eventId);
                      stageUpdated = false; // Don't trigger re-render for duplicates
                    } else {
                      console.log('📊 No eventId found for LLM interaction, skipping update');
                      stageUpdated = false;
                    }
                  } else if (updateType === 'mcp_interaction' || updateType === 'mcp_communication' || updateType === 'mcp_tool_list') {
                    // Check for duplicates by event_id or request_id
                    const eventId = update.request_id || update.event_id;
                    const exists = stage.mcp_communications?.some(i => 
                      i.event_id === eventId || i.id === eventId
                    );
                    
                    if (!exists && eventId) {
                      // Create properly structured MCP interaction with complete details
                      const newInteraction = {
                        id: eventId,
                        event_id: eventId,
                        type: 'mcp' as const,
                        timestamp_us: update.timestamp_us || Date.now() * 1000,
                        step_description: update.step_description || 'New MCP interaction',
                        duration_ms: update.duration_ms,
                        details: {
                          // Core MCP fields
                          server_name: update.server_name,
                          tool_name: update.tool_name,
                          communication_type: update.communication_type,
                          parameters: update.tool_arguments,
                          result: update.tool_result,
                          success: update.success,
                          error_message: update.error_message,
                          // Include all other fields from update
                          ...update
                        }
                      };
                      
                      updatedStage.mcp_communications = [...(stage.mcp_communications || []), newInteraction];
                      updatedStage.mcp_communication_count = (updatedStage.mcp_communication_count || 0) + 1;
                      updatedStage.total_interactions = (updatedStage.total_interactions || 0) + 1;
                      console.log('📊 Added MCP interaction:', eventId, 'to stage:', targetStageExecutionId);
                    } else if (exists) {
                      console.log('📊 Duplicate MCP interaction detected, skipping:', eventId);
                      stageUpdated = false; // Don't trigger re-render for duplicates
                    } else {
                      console.log('📊 No eventId found for MCP interaction, skipping update');
                      stageUpdated = false;
                    }
                  }
                  
                  return updatedStage;
                }
                return stage;
              });
              
              // Return updated session only if something actually changed
              if (!stageUpdated) {
                console.log('📊 No stage found for interaction update, may need stage creation first');
                return prevSession;
              }
              
              return {
                ...prevSession,
                stages: updatedStages
              };
            });
            break;
            
          case 'session_status_change':
            // Status change - update only status-related fields
            console.log('📊 Session status change - updating status fields');
            setSession(prev => {
              if (!prev) return prev;
              
              const updates: any = {
                status: update.status
              };
              
              // Add additional fields if present
              if (update.error_message) {
                updates.error_message = update.error_message;
              }
              if (update.final_analysis) {
                updates.final_analysis = update.final_analysis;
              }
              if (update.completed_at_us) {
                updates.completed_at_us = update.completed_at_us;
              }
              
              return { ...prev, ...updates };
            });
            
            // If session is completed/failed, also refresh summary counts
            if (update.status && ['completed', 'failed'].includes(update.status)) {
              console.log('📊 Session completion via status change - refreshing summary counts');
              // Small delay to ensure backend has processed completion fully
              setTimeout(() => {
                refreshSessionSummary(sessionId);
              }, 500);
            }
            break;
            
          case 'stage_update':
          case 'stage_progress':
            // Stage execution update - update stage status or create new stage
            console.log('📊 Stage update - updating stage status');
            setSession(prevSession => {
              if (!prevSession) return prevSession;
              
              const stageExecutionId = update.stage_execution_id;
              if (!stageExecutionId) return prevSession;
              
              // Check if stage exists
              const existingStageIndex = prevSession.stages?.findIndex(stage => stage.execution_id === stageExecutionId) ?? -1;
              
              if (existingStageIndex >= 0 && prevSession.stages) {
                // Update existing stage
                const updatedStages = [...prevSession.stages];
                updatedStages[existingStageIndex] = {
                  ...updatedStages[existingStageIndex],
                  status: update.status || updatedStages[existingStageIndex].status,
                  completed_at_us: update.completed_at_us || updatedStages[existingStageIndex].completed_at_us,
                  error_message: update.error_message || updatedStages[existingStageIndex].error_message,
                  duration_ms: update.duration_ms || updatedStages[existingStageIndex].duration_ms,
                  started_at_us: update.started_at_us || updatedStages[existingStageIndex].started_at_us
                };
                
                return {
                  ...prevSession,
                  stages: updatedStages,
                  current_stage_index: update.stage_index ?? prevSession.current_stage_index,
                  current_stage_id: update.stage_id || prevSession.current_stage_id
                };
              } else {
                // Create new stage if it doesn't exist
                console.log('📊 Creating new stage:', stageExecutionId);
                const newStage = {
                  execution_id: stageExecutionId,
                  session_id: prevSession.session_id,
                  stage_id: update.stage_id || stageExecutionId,
                  stage_name: update.stage_name || `Stage ${(prevSession.stages?.length ?? 0) + 1}`,
                  stage_index: update.stage_index ?? (prevSession.stages?.length ?? 0),
                  agent: update.agent || 'unknown',
                  status: update.status || 'pending',
                  started_at_us: update.started_at_us,
                  completed_at_us: update.completed_at_us,
                  duration_ms: update.duration_ms,
                  error_message: update.error_message,
                  stage_output: null,
                  llm_interactions: [],
                  mcp_communications: [],
                  llm_interaction_count: 0,
                  mcp_communication_count: 0,
                  total_interactions: 0,
                  iteration_strategy: null,
                  stage_interactions_duration_ms: 0,
                  chronological_interactions: []
                };
                
                const updatedStages = [...(prevSession.stages || []), newStage];
                
                return {
                  ...prevSession,
                  stages: updatedStages,
                  current_stage_index: update.stage_index ?? prevSession.current_stage_index,
                  current_stage_id: update.stage_id || prevSession.current_stage_id
                };
              }
            });
            break;
            
          case 'system_metrics':
            // System metrics updates - ignore for session detail view
            console.log('📊 System metrics update - ignoring for session detail');
            break;
            
          default:
            // Unknown update type or session completion - refresh summary only for completion
            if (update.status && ['completed', 'failed'].includes(update.status)) {
              console.log('🔄 Session completion detected - refreshing summary data only');
              // Small delay to ensure backend has processed completion fully
              setTimeout(() => {
                refreshSessionSummary(sessionId);
              }, 1000);
            } else {
              console.log('📊 Unknown update type - ignoring to avoid unnecessary refresh:', updateType);
            }
            break;
        }
      }
    };

    const unsubscribeUpdate = webSocketService.onSessionSpecificUpdate(`session_${sessionId}`, handleSessionUpdate);
    console.log('🔌 Registered session-specific handler for channel:', `session_${sessionId}`);

    // Cleanup
    return () => {
      console.log('🔌 Cleaning up WebSocket subscriptions');
      unsubscribeUpdate();
      webSocketService.unsubscribeFromSessionChannel(sessionId);
    };
  }, [sessionId]);

  // Initial load
  useEffect(() => {
    if (sessionId) {
      const timeoutId = setTimeout(() => {
        fetchSessionDetail(sessionId);
      }, 100);
      
      return () => clearTimeout(timeoutId);
    } else {
      setError('Session ID not provided');
      setLoading(false);
    }
  }, [sessionId]);

  // Navigation handlers
  const handleBack = () => {
    navigate('/dashboard');
  };

  const handleRetry = () => {
    if (sessionId) {
      fetchSessionDetail(sessionId);
    }
  };

  const handleVirtualizationToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    setUseVirtualization(event.target.checked);
  };

  return (
    <Container maxWidth={false} sx={{ px: 2 }}>
      {/* AppBar with performance indicators */}
      <AppBar position="static" elevation={0} sx={{ borderRadius: 1 }}>
        <Toolbar>
          <IconButton 
            edge="start" 
            color="inherit" 
            onClick={handleBack}
            sx={{ mr: 2 }}
            aria-label="Back to dashboard"
          >
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Session Details
            {performanceMetrics && (
              <Typography variant="caption" sx={{ ml: 2, opacity: 0.8 }}>
                {performanceMetrics.totalInteractions} interactions • {performanceMetrics.stagesCount} stages
                {performanceMetrics.isVeryLargeSession && ' • Large Session'}
              </Typography>
            )}
          </Typography>
          
          {/* Performance mode toggle */}
          {showPerformanceMode && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={useVirtualization || false}
                    onChange={handleVirtualizationToggle}
                    size="small"
                    color="default"
                  />
                }
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Speed fontSize="small" />
                    <Typography variant="caption" sx={{ color: 'inherit' }}>
                      Optimized
                    </Typography>
                  </Box>
                }
                sx={{ m: 0, color: 'inherit' }}
              />
            </Box>
          )}
          
          {/* Performance indicators */}
          {performanceMetrics?.isVeryLargeSession && (
            <Chip 
              icon={<Speed />}
              label="Large Session"
              size="small"
              color="warning"
              sx={{ mr: 1 }}
            />
          )}
          
          {/* Real-time status indicator */}
          {session && (session.status === 'in_progress' || session.status === 'pending') && !loading && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2, color: 'inherit' }}>
              <CircularProgress size={16} sx={{ color: 'inherit' }} />
              <Typography variant="body2" sx={{ color: 'inherit' }}>
                Live Updates
              </Typography>
            </Box>
          )}
          
          {loading && (
            <CircularProgress size={20} sx={{ color: 'inherit' }} />
          )}
        </Toolbar>
      </AppBar>

      <Box sx={{ mt: 2 }}>
        {/* Loading state with progressive skeletons */}
        {loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <HeaderSkeleton />
            <AlertCardSkeleton />
            <TimelineSkeleton />
          </Box>
        )}

        {/* Error state */}
        {error && !loading && (
          <Alert 
            severity="error" 
            sx={{ mb: 2 }}
            action={
              <IconButton
                color="inherit"
                size="small"
                onClick={handleRetry}
                aria-label="Retry"
              >
                <Typography variant="button">Retry</Typography>
              </IconButton>
            }
          >
            <Typography variant="body1" gutterBottom>
              Failed to load session details
            </Typography>
            <Typography variant="body2">
              {error}
            </Typography>
          </Alert>
        )}

        {/* Performance warning for large sessions */}
        {performanceMetrics?.isVeryLargeSession && !loading && (
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="body2" gutterBottom>
              <strong>Large Session Detected:</strong> This session has {performanceMetrics.totalInteractions} interactions.
            </Typography>
            <Typography variant="body2">
              Performance optimizations are {useVirtualization ? 'enabled' : 'disabled'}. 
              You can toggle optimized rendering using the switch in the header.
            </Typography>
          </Alert>
        )}

        {/* Session detail content with lazy loading */}
        {session && !loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Session Header - Lazy loaded */}
            <Suspense fallback={<HeaderSkeleton />}>
              <SessionHeader 
                session={session} 
                onRefresh={() => sessionId && refreshSessionSummary(sessionId)} 
              />
            </Suspense>

            {/* Original Alert Data - Lazy loaded */}
            <Suspense fallback={<AlertCardSkeleton />}>
              <OriginalAlertCard alertData={session.alert_data} />
            </Suspense>

            {/* Enhanced Processing Timeline - Conditional rendering based on performance settings */}
            {session.stages && session.stages.length > 0 ? (
              <Suspense fallback={<TimelineSkeleton />}>
                {useVirtualization ? (
                  <VirtualizedAccordionTimeline
                    chainExecution={{
                      chain_id: session.chain_id,
                      chain_definition: session.chain_definition,
                      current_stage_index: session.current_stage_index,
                      current_stage_id: session.current_stage_id,
                      stages: session.stages
                    }}
                    maxVisibleInteractions={LARGE_SESSION_THRESHOLD}
                  />
                ) : (
                  <NestedAccordionTimeline
                    chainExecution={{
                      chain_id: session.chain_id,
                      chain_definition: session.chain_definition,
                      current_stage_index: session.current_stage_index,
                      current_stage_id: session.current_stage_id,
                      stages: session.stages
                    }}
                  />
                )}
              </Suspense>
            ) : (
              <Alert severity="error" sx={{ mb: 2 }}>
                <Typography variant="h6" gutterBottom>
                  Backend Chain Execution Error
                </Typography>
                <Typography variant="body2">
                  This session is missing stage execution data. All sessions should be processed as chains.
                </Typography>
                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2" color="text.secondary">
                    Session ID: {session.session_id}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Agent Type: {session.agent_type}
                  </Typography>
                </Box>
              </Alert>
            )}

            {/* Final AI Analysis - Lazy loaded */}
            <Suspense fallback={<Skeleton variant="rectangular" height={200} />}>
              <FinalAnalysisCard 
                analysis={session.final_analysis}
                sessionStatus={session.status}
                errorMessage={session.error_message}
              />
            </Suspense>
          </Box>
        )}

        {/* Empty state */}
        {!session && !loading && !error && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body1">
              Session not found or no longer available
            </Typography>
          </Alert>
        )}

        {/* Performance metrics display (dev mode) */}
        {process.env.NODE_ENV === 'development' && performanceMetrics && (
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="caption">
              <strong>Performance Metrics:</strong> {performanceMetrics.totalInteractions} interactions, 
              {performanceMetrics.stagesCount} stages, largest stage: {performanceMetrics.largestStage} interactions,
              estimated size: {(performanceMetrics.estimatedSize / 1024).toFixed(1)}KB
            </Typography>
          </Alert>
        )}
      </Box>
    </Container>
  );
}

export default OptimizedSessionDetailPage;
