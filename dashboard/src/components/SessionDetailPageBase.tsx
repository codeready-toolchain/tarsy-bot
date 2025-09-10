import React, { useState, useEffect, useRef, lazy, Suspense, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Container, 
  Typography, 
  Box, 
  Paper, 
  Alert, 
  CircularProgress,
  Skeleton,
  Switch,
  FormControlLabel,
  Chip,
  ToggleButton,
  ToggleButtonGroup,
  IconButton
} from '@mui/material';
import { Speed, Psychology, BugReport } from '@mui/icons-material';
import SharedHeader from './SharedHeader';
import { webSocketService } from '../services/websocket';
import { useSession } from '../contexts/SessionContext';
import type { DetailedSession } from '../types';
import { useAdvancedAutoScroll } from '../hooks/useAdvancedAutoScroll';

// Lazy load shared components
const SessionHeader = lazy(() => import('./SessionHeader'));
const OriginalAlertCard = lazy(() => import('./OriginalAlertCard'));
const FinalAnalysisCard = lazy(() => import('./FinalAnalysisCard'));

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

interface SessionDetailPageBaseProps {
  viewType: 'conversation' | 'technical';
  timelineComponent: (session: DetailedSession, useVirtualization?: boolean, autoScroll?: boolean) => ReactNode;
  timelineSkeleton?: ReactNode;
  onViewChange?: (newView: 'conversation' | 'technical') => void;
}

/**
 * Shared base component for both conversation and technical session detail pages
 * Handles common functionality: WebSocket updates, loading states, shared UI structure
 */
function SessionDetailPageBase({ 
  viewType, 
  timelineComponent,
  timelineSkeleton = <TimelineSkeleton />,
  onViewChange
}: SessionDetailPageBaseProps) {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  
  // Use shared session context instead of local state
  const { 
    session, 
    loading, 
    error, 
    refetch, 
    refreshSessionSummary,
    refreshSessionStages,
    updateFinalAnalysis,
    updateSessionStatus 
  } = useSession(sessionId);

  // Performance optimization settings
  const [useVirtualization, setUseVirtualization] = useState<boolean | null>(null); // null = auto-detect
  const [showPerformanceMode, setShowPerformanceMode] = useState<boolean>(false);
  
  // Auto-scroll settings
  const [autoScrollEnabled, setAutoScrollEnabled] = useState<boolean>(true);
  
  // Advanced centralized auto-scroll
  useAdvancedAutoScroll({
    enabled: autoScrollEnabled,
    threshold: 10,
    scrollDelay: 300,
    observeSelector: '[data-autoscroll-container]',
    debug: process.env.NODE_ENV !== 'production'
  });
  
  // View toggle state
  const [currentView, setCurrentView] = useState<string>(viewType);
  
  // Sync local state with prop changes to prevent desync
  useEffect(() => {
    setCurrentView(viewType);
  }, [viewType]);

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
  const lastUpdateRef = useRef<number>(0);
  const updateThrottleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  // Throttled update function to prevent UI overload
  const throttledUpdate = (updateFn: () => void, delay: number = 500) => {
    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateRef.current;
    
    // Clear any pending update
    if (updateThrottleRef.current) {
      clearTimeout(updateThrottleRef.current);
    }
    
    // If enough time has passed, update immediately
    if (timeSinceLastUpdate >= delay) {
      lastUpdateRef.current = now;
      updateFn();
    } else {
      // Otherwise, schedule the update
      const remainingDelay = delay - timeSinceLastUpdate;
      updateThrottleRef.current = setTimeout(() => {
        lastUpdateRef.current = Date.now();
        updateFn();
      }, remainingDelay);
    }
  };



  // No need for manual setup - the hook handles everything automatically

  // Helper functions are now provided by the SessionContext



  // WebSocket setup for real-time updates
  useEffect(() => {
    if (!sessionId) return;

    console.log(`🔌 Setting up WebSocket for ${viewType} view:`, sessionId);
    
    (async () => {
      try {
        await webSocketService.connect();
        webSocketService.subscribeToSessionChannel(sessionId);
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error);
      }
    })();

    // Handle granular session updates for better performance
    const handleSessionUpdate = (update: any) => {
      console.log(`📡 ${viewType} view received update:`, update.type);
      
      // Handle different update types with granular updates for optimal performance
      switch (update.type) {
        case 'summary_update':
          // Quick summary refresh - lightweight API call
          console.log('🔄 Summary update, using lightweight summary refresh');
          if (sessionId) {
            refreshSessionSummary(sessionId);
          }
          break;
          
        case 'session_status_change':
          // Update status immediately to prevent UI lag
          updateSessionStatus(update.status, update.error_message);
          
          // For major status changes, also refresh stages and analysis
          if (['completed', 'failed'].includes(update.status)) {
            console.log('🔄 Major status change, refreshing stages');
            throttledUpdate(() => {
              if (sessionId) {
                refreshSessionStages(sessionId);
                
                // Auto-scroll when session completes (MutationObserver will handle this automatically)
                // tryAutoScroll is no longer needed here
              }
            }, 200);
          }
          
          // Always update summary for accurate counts
          if (sessionId) {
            refreshSessionSummary(sessionId);
          }
          break;
          
        case 'llm_interaction':
        case 'mcp_communication':
        case 'mcp_interaction':
          // For ongoing sessions, use lightweight updates
          if (sessionRef.current?.status === 'in_progress') {
            console.log('🔄 Activity update, using partial refresh');
            
            // Always update summary for real-time statistics (lightweight)
            if (sessionId) {
              refreshSessionSummary(sessionId);
            }
            
            // Use throttled partial stage updates instead of full session refresh
            const updateDelay = viewType === 'conversation' ? 800 : 500;
            throttledUpdate(() => {
              if (sessionId) {
                refreshSessionStages(sessionId);
                // MutationObserver will detect content changes and auto-scroll automatically
              }
            }, updateDelay);
          }
          break;
          
        case 'stage_update':
        case 'stage_completed':
        case 'stage_failed':
          // Stage events use partial updates
          console.log('🔄 Stage update, using partial refresh');
          
          // Update summary immediately
          if (sessionId) {
            refreshSessionSummary(sessionId);
          }
          
          // Use throttled partial update for stage content
          throttledUpdate(() => {
            if (sessionId) {
              refreshSessionStages(sessionId);
              // MutationObserver will detect content changes and auto-scroll automatically
            }
          }, 250);
          break;
          
        case 'final_analysis_update':
          // Final analysis updates - use direct update if data is available
          console.log('🔄 Final analysis update');
          
          if (update.analysis) {
            // Direct update if analysis is provided in update
            updateFinalAnalysis(update.analysis);
            
            // MutationObserver will detect the analysis change and auto-scroll automatically
          } else {
            // Otherwise use partial refresh
            throttledUpdate(() => {
              if (sessionId) {
                refreshSessionStages(sessionId);
                
                // MutationObserver will detect content changes and auto-scroll automatically
              }
            }, 150);
          }
          break;
          
        case 'stage_progress':
          // Stage progress updates - these often coincide with final analysis
          console.log('🔄 Stage progress update');
          
          if (sessionId) {
            refreshSessionSummary(sessionId);
                          throttledUpdate(() => {
                if (sessionId) {
                  refreshSessionStages(sessionId);
                  // MutationObserver will detect content changes and auto-scroll automatically
                }
              }, 300);
          }
          break;

        default:
          // Unknown update types - be conservative and update summary
          console.log(`🔄 Unknown update type: ${update.type}, using partial refresh`);
          if (sessionId) {
            refreshSessionSummary(sessionId);
          }
          
          // If it contains data that might affect content, use partial refresh
          if (update.data || update.content) {
            throttledUpdate(() => {
              if (sessionId) {
                refreshSessionStages(sessionId);
                // MutationObserver will detect content changes and auto-scroll automatically
              }
            }, 800);
          }
      }
    };

    const unsubscribeUpdate = webSocketService.onSessionSpecificUpdate(
      `session_${sessionId}`, 
      handleSessionUpdate
    );

    // Cleanup
    return () => {
      console.log(`🔌 Cleaning up ${viewType} view WebSocket`);
      unsubscribeUpdate();
      webSocketService.unsubscribeFromSessionChannel(sessionId);
      
      // Clear any pending throttled updates
      if (updateThrottleRef.current) {
        clearTimeout(updateThrottleRef.current);
        updateThrottleRef.current = null;
      }
    };
  }, [sessionId, viewType]);



  // Note: Initial load is now handled by the SessionContext automatically

  // Navigation handlers (back navigation now handled by SharedHeader)

  const handleViewChange = (_event: React.MouseEvent<HTMLElement>, newView: string) => {
    if (newView !== null && (newView === 'conversation' || newView === 'technical')) {
      if (onViewChange) {
        // Use external view change handler if provided (for unified wrapper)
        onViewChange(newView);
      } else {
        // Fallback to direct navigation (for legacy usage)
        if (newView === 'technical' && sessionId) {
          navigate(`/sessions/${sessionId}/technical`);
        } else if (newView === 'conversation' && sessionId) {
          navigate(`/sessions/${sessionId}`);
        }
      }
      setCurrentView(newView);
    }
  };

  const handleRetry = () => {
    if (sessionId) {
      refetch();
    }
  };

  const handleVirtualizationToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    setUseVirtualization(event.target.checked);
  };

  const handleAutoScrollToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    setAutoScrollEnabled(event.target.checked);
  };

  return (
    <Container maxWidth={false} sx={{ py: 2, px: { xs: 1, sm: 2 } }}>
      {/* Header with navigation and controls */}
      <SharedHeader 
        title={`${viewType === 'conversation' ? 'AI Reasoning View' : 'Debug View'}${session ? ` - ${session.session_id?.slice(-8) || sessionId}` : ''}`}
        showBackButton={true}
        backUrl="/"
      >
        {/* Session info */}
        {session && (
          <Typography variant="body2" sx={{ mr: 2, opacity: 0.8, color: 'white' }}>
            {session.stages?.length || 0} stages • {session.total_interactions || 0} interactions
          </Typography>
        )}
        
        {/* Live Updates indicator */}
        {session && (session.status === 'in_progress' || session.status === 'pending') && !loading && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2 }}>
            <CircularProgress size={14} sx={{ color: 'inherit' }} />
            <Typography variant="caption" sx={{ color: 'inherit', fontSize: '0.75rem' }}>
              Live
            </Typography>
          </Box>
        )}
          
          {/* Enhanced View Toggle */}
          <ToggleButtonGroup
            value={currentView}
            exclusive
            onChange={handleViewChange}
            size="small"
            sx={{
              mr: 2,
              bgcolor: 'rgba(255,255,255,0.1)',
              borderRadius: 3,
              padding: 0.5,
              border: '1px solid rgba(255,255,255,0.2)',
              '& .MuiToggleButton-root': {
                color: 'rgba(255,255,255,0.8)',
                border: 'none',
                borderRadius: 2,
                px: 2,
                py: 1,
                minWidth: 100,
                fontWeight: 500,
                fontSize: '0.875rem',
                textTransform: 'none',
                transition: 'all 0.2s ease-in-out',
                '&:hover': {
                  bgcolor: 'rgba(255,255,255,0.15)',
                  color: 'rgba(255,255,255,0.95)',
                  transform: 'translateY(-1px)',
                },
                '&.Mui-selected': {
                  bgcolor: 'rgba(255,255,255,0.25)',
                  color: '#fff',
                  fontWeight: 600,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
                  '&:hover': {
                    bgcolor: 'rgba(255,255,255,0.3)',
                  }
                }
              }
            }}
          >
            <ToggleButton value="conversation">
              <Psychology fontSize="small" sx={{ mr: 1 }} />
              Reasoning
            </ToggleButton>
            <ToggleButton value="technical">
              <BugReport fontSize="small" sx={{ mr: 1 }} />
              Debug
            </ToggleButton>
          </ToggleButtonGroup>
          


          {/* Auto-scroll toggle - only show for active sessions */}
          {session && (session.status === 'in_progress' || session.status === 'pending') && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={autoScrollEnabled}
                    onChange={handleAutoScrollToggle}
                    size="small"
                    color="default"
                  />
                }
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Typography variant="caption" sx={{ color: 'inherit' }}>
                      🔄 Auto-scroll
                    </Typography>
                  </Box>
                }
                sx={{ m: 0, color: 'inherit' }}
              />
            </Box>
          )}

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
          

          
          {loading && (
            <CircularProgress size={20} sx={{ color: 'inherit' }} />
          )}
      </SharedHeader>

      <Box sx={{ mt: 2 }} data-autoscroll-container>
        {/* Loading state with progressive skeletons */}
        {loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <HeaderSkeleton />
            <AlertCardSkeleton />
            {timelineSkeleton}
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

            {/* Timeline Content - Conditional based on view type */}
            {session.stages && session.stages.length > 0 ? (
              <Suspense fallback={timelineSkeleton}>
                {timelineComponent(session, useVirtualization ?? undefined, autoScrollEnabled)}
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
      </Box>
    </Container>
  );
}

export default SessionDetailPageBase;
