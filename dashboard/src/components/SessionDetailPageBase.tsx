import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
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
  ToggleButton,
  ToggleButtonGroup,
  IconButton
} from '@mui/material';
import { Psychology, BugReport } from '@mui/icons-material';
import SharedHeader from './SharedHeader';
import VersionFooter from './VersionFooter';
import FloatingSubmitAlertFab from './FloatingSubmitAlertFab';
import { websocketService } from '../services/websocketService';
import { useSession } from '../contexts/SessionContext';
import type { DetailedSession } from '../types';
import { useAdvancedAutoScroll } from '../hooks/useAdvancedAutoScroll';
import { isTerminalSessionEvent } from '../utils/eventTypes';
import { SESSION_STATUS } from '../utils/statusConstants';

// Lazy load shared components
const SessionHeader = lazy(() => import('./SessionHeader'));
const OriginalAlertCard = lazy(() => import('./OriginalAlertCard'));
const FinalAnalysisCard = lazy(() => import('./FinalAnalysisCard'));

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
  timelineComponent: (session: DetailedSession, autoScroll?: boolean) => ReactNode;
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
    refreshSessionStages
  } = useSession(sessionId);

  // Auto-scroll settings - only enable by default for active sessions
  const [autoScrollEnabled, setAutoScrollEnabled] = useState<boolean>(() => {
    // Initialize based on session status if available
    return session ? (session.status === SESSION_STATUS.IN_PROGRESS || session.status === SESSION_STATUS.PENDING) : false;
  });
  
  // Track previous session status to detect transitions
  const prevStatusRef = useRef<string | undefined>(undefined);
  const disableTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasPerformedInitialScrollRef = useRef<boolean>(false);
  
  // Reset initial scroll flag when sessionId changes
  useEffect(() => {
    hasPerformedInitialScrollRef.current = false;
  }, [sessionId]);
  
  // Update auto-scroll enabled state when session transitions between active/inactive
  useEffect(() => {
    if (session) {
      const previousActive = prevStatusRef.current === SESSION_STATUS.IN_PROGRESS || prevStatusRef.current === SESSION_STATUS.PENDING;
      const currentActive = session.status === SESSION_STATUS.IN_PROGRESS || session.status === SESSION_STATUS.PENDING;
      
      // Only update auto-scroll on first load or when crossing active↔inactive boundary
      if (prevStatusRef.current === undefined || previousActive !== currentActive) {
        if (currentActive) {
          // Transitioning to active - enable auto-scroll immediately and clear any pending disable
          if (disableTimeoutRef.current) {
            clearTimeout(disableTimeoutRef.current);
            disableTimeoutRef.current = null;
          }
          setAutoScrollEnabled(true);
        } else {
          // Transitioning to inactive - delay disable to allow final content to scroll
          if (disableTimeoutRef.current) {
            clearTimeout(disableTimeoutRef.current);
          }
          disableTimeoutRef.current = setTimeout(() => {
            setAutoScrollEnabled(false);
            disableTimeoutRef.current = null;
          }, 2000); // Wait 2 seconds for final content to render and scroll
        }
        prevStatusRef.current = session.status;
      }
    }
  }, [session?.status]);
  
  // Perform initial scroll to bottom for active sessions
  useEffect(() => {
    if (
      session && 
      !loading && 
      !hasPerformedInitialScrollRef.current && 
      autoScrollEnabled &&
      (session.status === SESSION_STATUS.IN_PROGRESS || session.status === SESSION_STATUS.PENDING)
    ) {
      // Wait for content to render, then scroll to bottom
      const scrollTimer = setTimeout(() => {
        window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
        hasPerformedInitialScrollRef.current = true;
      }, 300); // Small delay to ensure content is rendered
      
      return () => clearTimeout(scrollTimer);
    }
  }, [session, loading, autoScrollEnabled]);
  
  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (disableTimeoutRef.current) {
        clearTimeout(disableTimeoutRef.current);
      }
    };
  }, []);
  
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

  // WebSocket setup for real-time updates (catchup events handle race conditions)
  useEffect(() => {
    if (!sessionId) return;

    console.log(`🔌 Setting up WebSocket for ${viewType} view:`, sessionId);
    
    (async () => {
      try {
        await websocketService.connect();
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error);
      }
    })();

    // Handle granular session updates for better performance
    const handleSessionUpdate = (update: any) => {
      console.log(`📡 ${viewType} view received update:`, update.type);
      
      const eventType = update.type || '';
      
      // Use pattern matching for robust event handling
      if (eventType.startsWith('session.')) {
        // Session lifecycle events (session.created, session.started, session.completed, session.failed, session.cancelled)
        console.log('🔄 Session lifecycle event, refreshing data');
        
        // For terminal session events, refresh everything
        if (isTerminalSessionEvent(eventType)) {
          console.log('🔄 Session reached terminal state - full refresh');
          throttledUpdate(() => {
            if (sessionId) {
              refreshSessionStages(sessionId);
            }
          }, 200);
        }
        
        // Always update summary for session events
        if (sessionId) {
          refreshSessionSummary(sessionId);
        }
      }
      else if (eventType.startsWith('stage.')) {
        // Stage events (stage.started, stage.completed, stage.failed)
        console.log('🔄 Stage event, using partial refresh');
        
        // Update summary immediately
        if (sessionId) {
          refreshSessionSummary(sessionId);
        }
        
        // Use throttled partial update for stage content
        throttledUpdate(() => {
          if (sessionId) {
            refreshSessionStages(sessionId);
          }
        }, 250);
      }
      else if (eventType.startsWith('llm.') || eventType.startsWith('mcp.')) {
        // LLM/MCP interaction events (llm.interaction, mcp.tool_call, mcp.list_tools)
        // Only update if session is in progress
        if (sessionRef.current?.status === SESSION_STATUS.IN_PROGRESS) {
          console.log('🔄 Activity update, using partial refresh');
          
          // Always update summary for real-time statistics (lightweight)
          if (sessionId) {
            refreshSessionSummary(sessionId);
          }
          
          // Use throttled partial stage updates
          const updateDelay = viewType === 'conversation' ? 800 : 500;
          throttledUpdate(() => {
            if (sessionId) {
              refreshSessionStages(sessionId);
            }
          }, updateDelay);
        }
      }
      else {
        // Unknown event type or custom events - conservative update
        console.log(`🔄 Unknown update type: ${eventType}, using partial refresh`);
        if (sessionId) {
          refreshSessionSummary(sessionId);
        }
        
        // If it contains data that might affect content, use partial refresh
        if (update.data || update.content || update.analysis) {
          throttledUpdate(() => {
            if (sessionId) {
              refreshSessionStages(sessionId);
            }
          }, 800);
        }
      }
    };

    const unsubscribeUpdate = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      handleSessionUpdate
    );

    // Cleanup
    return () => {
      console.log(`🔌 Cleaning up ${viewType} view WebSocket`);
      unsubscribeUpdate();
      
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
                {timelineComponent(session, autoScrollEnabled)}
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

      {/* Version footer */}
      <VersionFooter />

      {/* Floating Action Button for quick alert submission access */}
      <FloatingSubmitAlertFab />
    </Container>
  );
}

export default SessionDetailPageBase;
