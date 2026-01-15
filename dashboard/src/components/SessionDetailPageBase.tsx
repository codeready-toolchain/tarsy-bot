import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container, 
  Typography, 
  Box, 
  Paper, 
  Alert, 
  AlertTitle,
  CircularProgress,
  Skeleton,
  Switch,
  FormControlLabel,
  ToggleButton,
  ToggleButtonGroup,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Tooltip,
  alpha,
} from '@mui/material';
import { Psychology, BugReport, KeyboardDoubleArrowDown, KeyboardDoubleArrowUp, PauseCircle, PlayArrow } from '@mui/icons-material';
import SharedHeader from './SharedHeader';
import VersionFooter from './VersionFooter';
import FloatingSubmitAlertFab from './FloatingSubmitAlertFab';
import ChatPanel from './Chat/ChatPanel';
import { websocketService } from '../services/websocketService';
import { useSession } from '../contexts/SessionContext';
import { useAuth } from '../contexts/AuthContext';
import { useChatState } from '../hooks/useChatState';
import type { DetailedSession } from '../types';
import { useAdvancedAutoScroll } from '../hooks/useAdvancedAutoScroll';
import { isTerminalSessionEvent } from '../utils/eventTypes';
import { isActiveSessionStatus, isTerminalSessionStatus, isActiveStageStatus, SESSION_STATUS } from '../utils/statusConstants';
import { mapEventToProgressStatus, ProgressStatusMessage, StageName, isTerminalProgressStatus } from '../utils/statusMapping';
import { STAGE_STATUS } from '../utils/statusConstants';

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
  timelineComponent: (
    session: DetailedSession,
    autoScroll?: boolean,
    progressStatus?: string,
    agentProgressStatuses?: Map<string, string>,
    onSelectedAgentChange?: (executionId: string | null) => void
  ) => ReactNode;
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
    handleParallelStageStarted
  } = useSession(sessionId);

  // Auth context for user information
  const { user } = useAuth();

  // Chat state management (EP-0027)
  const {
    chat,
    isAvailable: chatAvailable,
    createChat,
    sendMessage,
    cancelExecution,
    loading: chatLoading,
    error: chatError,
    sendingMessage,
    activeExecutionId,
    canceling,
  } = useChatState(sessionId || '', session?.status);

  // Auto-scroll settings - only enable by default for active sessions
  const [autoScrollEnabled, setAutoScrollEnabled] = useState<boolean>(() => {
    // Initialize based on session status if available
    return session ? isActiveSessionStatus(session.status) : false;
  });

  // Chat expansion state - use counter to force collapse every time (not boolean)
  const [collapseCounter, setCollapseCounter] = useState(0);
  
  // Final Analysis expansion state - use counter to force expand every time (not boolean)
  const [expandCounter, setExpandCounter] = useState(0);
  
  // Track if there's an active chat stage in progress (for disabling chat input)
  const [chatStageInProgress, setChatStageInProgress] = useState<boolean>(false);
  
  // Trigger to force chat panel expansion (e.g., from "Jump to Chat" button)
  const [shouldExpandChat, setShouldExpandChat] = useState(false);
  
  // Track current progress status message (Investigating/Synthesizing/Summarizing)
  // For parallel agents, track per-agent status by stage_execution_id
  // Values can be progress statuses ("Investigating...", "Concluding...") or terminal statuses ("Completed", "Failed", "Cancelled")
  const [progressStatus, setProgressStatus] = useState<string>(ProgressStatusMessage.PROCESSING);
  const [agentProgressStatuses, setAgentProgressStatuses] = useState<Map<string, string>>(new Map());
  
  // Track which parallel parent stage we've updated status for (to avoid duplicates)
  const parallelStageStatusUpdated = useRef<string | null>(null);
  
  // Track currently selected agent execution ID for display purposes
  const [selectedAgentExecutionId, setSelectedAgentExecutionId] = useState<string | null>(null);
  
  // Track previous session status to detect transitions
  const prevStatusRef = useRef<string | undefined>(undefined);
  
  // ============================================================================
  // Initial Status Initialization Effects
  // ============================================================================
  // The following two effects both run on [session?.session_id, loading] to
  // initialize related but separate state when the session first loads:
  // 1. progressStatus: Session-level status (e.g., "Investigating...", "Synthesizing...")
  // 2. agentProgressStatuses: Per-agent statuses for parallel executions
  // Both must initialize from the same session data to ensure UI consistency.
  
  // Initialize progress status from current session state on load
  useEffect(() => {
    if (!session || loading) return;
    
    // Only set initial status if session is actively processing
    if (!isActiveSessionStatus(session.status)) return;
    
    // Find the currently active stage
    const activeStage = session.stages?.find((s: any) => s.status === STAGE_STATUS.ACTIVE);
    if (!activeStage) return;
    
    // Set initial status based on active stage type
    if (activeStage.stage_name === StageName.SYNTHESIS) {
      setProgressStatus(ProgressStatusMessage.SYNTHESIZING);
    } else if (activeStage.parallel_executions && activeStage.parallel_executions.length > 0) {
      // Parallel stage - set to Processing (we can't know exact per-agent phase from DB)
      setProgressStatus(ProgressStatusMessage.PROCESSING);
    } else {
      // Regular non-parallel stage
      setProgressStatus(ProgressStatusMessage.INVESTIGATING);
    }
  }, [session?.session_id, loading]);
  
  // Initialize per-agent progress statuses for parallel executions on load
  useEffect(() => {
    if (!session || loading) return;
    
    // Only initialize if session is actively processing
    if (!isActiveSessionStatus(session.status)) return;
    
    // Find parallel parent stages (active, pending, or paused - might have active children)
    const parallelStages = session.stages?.filter((s: any) => {
      const hasParallelExecutions = s.parallel_executions && s.parallel_executions.length > 0;
      const isRelevantStatus = isActiveStageStatus(s.status);
      return isRelevantStatus && hasParallelExecutions;
    });
    
    if (!parallelStages || parallelStages.length === 0) return;
    
    // Build initial Map from parallel executions' current state
    const initialStatusMap = new Map<string, string>();
    
    for (const stage of parallelStages) {
      if (!stage.parallel_executions) continue;
      
      for (const execution of stage.parallel_executions) {
        // Set status based on execution state
        if (isActiveStageStatus(execution.status)) {
          // Active/pending/paused parallel agents show Investigating
          initialStatusMap.set(execution.execution_id, ProgressStatusMessage.INVESTIGATING);
        } else if (execution.status === STAGE_STATUS.COMPLETED) {
          // Completed agents get terminal status
          initialStatusMap.set(execution.execution_id, ProgressStatusMessage.COMPLETED);
        } else if (execution.status === STAGE_STATUS.FAILED) {
          // Failed agents get terminal status
          initialStatusMap.set(execution.execution_id, ProgressStatusMessage.FAILED);
        } else if (execution.status === STAGE_STATUS.CANCELLED) {
          // Cancelled agents get terminal status
          initialStatusMap.set(execution.execution_id, ProgressStatusMessage.CANCELLED);
        }
      }
    }
    
    // Only update if we found relevant parallel executions
    if (initialStatusMap.size > 0) {
      setAgentProgressStatuses(initialStatusMap);
    }
  }, [session?.session_id, loading]);
  
  // Bottom cancel dialog state
  const [showBottomCancelDialog, setShowBottomCancelDialog] = useState(false);
  const [isBottomCanceling, setIsBottomCanceling] = useState(false);
  const [bottomCancelError, setBottomCancelError] = useState<string | null>(null);
  
  // Bottom resume state
  const [isBottomResuming, setIsBottomResuming] = useState(false);
  const [bottomResumeError, setBottomResumeError] = useState<string | null>(null);
  
  // Ref for Final Analysis Card (includes summary + analysis)
  const finalAnalysisRef = useRef<HTMLDivElement>(null);
  const disableTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasPerformedInitialScrollRef = useRef<boolean>(false);
  
  // Reset scroll flags when sessionId changes
  useEffect(() => {
    hasPerformedInitialScrollRef.current = false;
  }, [sessionId]);
  
  // Clear bottom resuming state when session status changes away from paused
  useEffect(() => {
    if (session?.status !== SESSION_STATUS.PAUSED && isBottomResuming) {
      setIsBottomResuming(false);
    }
  }, [session?.status, isBottomResuming]);
  
  // Clear bottom resume error when session status or pause_metadata changes
  useEffect(() => {
    setBottomResumeError(null);
  }, [session?.status, session?.pause_metadata]);
  
  // Clear bottom canceling state when session status changes to cancelled
  useEffect(() => {
    if (session?.status === SESSION_STATUS.CANCELLED && isBottomCanceling) {
      setIsBottomCanceling(false);
    }
  }, [session?.status, isBottomCanceling]);
  
  // Update auto-scroll enabled state when session transitions between active/inactive
  useEffect(() => {
    if (session) {
      const previousActive = prevStatusRef.current
        ? isActiveSessionStatus(prevStatusRef.current)
        : false;
      const currentActive = isActiveSessionStatus(session.status);
      
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
  
  // Enable auto-scroll when chat becomes active (even in terminal sessions)
  useEffect(() => {
    const isChatActive = sendingMessage || chatStageInProgress || activeExecutionId !== null;
    
    if (isChatActive && !autoScrollEnabled) {
      // Chat activity detected - enable auto-scroll
      if (disableTimeoutRef.current) {
        clearTimeout(disableTimeoutRef.current);
        disableTimeoutRef.current = null;
      }
      setAutoScrollEnabled(true);
      
      // Scroll to bottom immediately so useAdvancedAutoScroll can track properly
      setTimeout(() => {
        window.scrollTo({ 
          top: document.documentElement.scrollHeight, 
          behavior: 'smooth' 
        });
      }, 300);
    }
  }, [sendingMessage, chatStageInProgress, activeExecutionId, autoScrollEnabled]);
  
  // Perform initial scroll to bottom for active sessions
  // Always scroll to bottom when opening an active session, regardless of autoScrollEnabled state
  useEffect(() => {
    if (
      session &&
      !loading &&
      !hasPerformedInitialScrollRef.current &&
      isActiveSessionStatus(session.status)
    ) {
      // Wait for content to render, then scroll to bottom
      const scrollTimer = setTimeout(() => {
        window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
        hasPerformedInitialScrollRef.current = true;
      }, 500); // Increased delay to ensure content is fully rendered
      
      return () => clearTimeout(scrollTimer);
    }
  }, [session, loading]);
  
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


  // Refs to hold latest values to avoid stale closures in WebSocket handlers
  const sessionRef = useRef<DetailedSession | null>(null);
  const chatRef = useRef<any>(null);
  const lastUpdateRef = useRef<number>(0);
  const updateThrottleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);
  
  useEffect(() => {
    chatRef.current = chat;
  }, [chat]);

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

  // Track chat stage progress for disabling chat input
  useEffect(() => {
    if (!sessionId) return;
    
    const handleStageEvent = (event: any) => {
      // Only track chat stages (those with chat_id)
      if (!event.chat_id) return;
      
      if (event.type === 'stage.started') {
        console.log('💬 Chat stage started - disabling chat input');
        setChatStageInProgress(true);
      } else if (event.type === 'stage.completed' || event.type === 'stage.failed') {
        console.log('💬 Chat stage ended - enabling chat input');
        setChatStageInProgress(false);
      }
    };
    
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      handleStageEvent
    );
    
    return () => unsubscribe();
  }, [sessionId]);

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
      
      // Update progress status based on event
      if (eventType.startsWith('stage.') || eventType === 'session.progress_update') {
        // Check if this is a parallel-related event (child or parent)
        // Use explicit presence checks to handle parallel_index === 0 correctly
        const isParallelChildUpdate = (eventType === 'session.progress_update' && update.stage_execution_id !== undefined && update.stage_execution_id !== null && update.parallel_index !== undefined && update.parallel_index !== null) || 
                                      (eventType.startsWith('stage.') && update.parent_stage_execution_id !== undefined && update.parent_stage_execution_id !== null);
        const isParallelParentEvent = eventType.startsWith('stage.') && update.expected_parallel_count && update.expected_parallel_count > 0;
        const isParallelUpdate = isParallelChildUpdate || isParallelParentEvent;
        
        if (isParallelUpdate) {
          
          // Per-agent status update for parallel execution (child agents only)
          if (eventType === 'session.progress_update' && isParallelChildUpdate) {
            // Update session-level status when FIRST parallel child update arrives
            const parentId = update.parent_stage_execution_id;
            if (parentId !== undefined && parentId !== null && parentId !== parallelStageStatusUpdated.current) {
              parallelStageStatusUpdated.current = parentId;
              setProgressStatus('Processing...');
            }
            const statusInfo = mapEventToProgressStatus(update, true);
            if (statusInfo.stageExecutionId) {
              setAgentProgressStatuses(prev => {
                const newMap = new Map(prev);
                newMap.set(statusInfo.stageExecutionId!, statusInfo.status);
                return newMap;
              });
            }
          } else if (eventType === 'stage.completed' || eventType === 'stage.failed') {
            // Backend sends stage_id, not stage_execution_id in completion events
            const executionId = update.stage_execution_id || update.stage_id;
            if (executionId && isParallelChildUpdate) {
              // Set terminal status when this specific parallel child stage completes or fails
              // Use executionId (from stage_id or stage_execution_id) to match the key format from mapEventToProgressStatus
              const terminalStatus = eventType === 'stage.completed' ? ProgressStatusMessage.COMPLETED : ProgressStatusMessage.FAILED;
              setAgentProgressStatuses(prev => {
                const newMap = new Map(prev);
                newMap.set(executionId, terminalStatus);
                return newMap;
              });
            } else if (update.expected_parallel_count && update.expected_parallel_count > 0 && (update.parent_stage_execution_id === undefined || update.parent_stage_execution_id === null)) {
              // Clear all agent statuses when the parallel parent completes or fails
              // Parent stages have expected_parallel_count > 0 and no parent_stage_execution_id
              parallelStageStatusUpdated.current = null;
              setAgentProgressStatuses(new Map());
            }
          }
          // For parallel-related events (child stages and parent stages),
          // don't update session-level status
        } else {
          // Session-level status update (non-parallel or stage events)
          const newStatus = mapEventToProgressStatus(update);
          setProgressStatus(newStatus);
        }
      }
      
      // Handle chat events (EP-0027)
      if (eventType === 'chat.created' || eventType === 'chat.user_message') {
        console.log('💬 Chat event received:', eventType);
        // Chat state will be updated through the API response
        // No need to refresh session data for chat events
        return;
      }
      
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
        
        // Check if this is a parallel stage starting (has expected_parallel_count)
        if (eventType === 'stage.started' && update.expected_parallel_count && update.expected_parallel_count > 0) {
          console.log('🚀 Parallel parent stage starting - injecting placeholders immediately');
          
          // Create a minimal StageExecution object for placeholder injection
          const parentStage = {
            execution_id: update.stage_id,
            session_id: update.session_id,
            stage_id: update.stage_id,
            stage_index: 0, // Will be updated by full refresh
            stage_name: update.stage_name,
            agent: 'parallel', // Placeholder
            status: 'active' as const,
            started_at_us: null,
            paused_at_us: null,
            completed_at_us: null,
            duration_ms: null,
            stage_output: null,
            error_message: null,
            current_iteration: null,
            parent_stage_execution_id: null,
            parallel_index: 0,
            parallel_type: update.parallel_type,
            expected_parallel_count: update.expected_parallel_count,
            llm_interactions: [],
            mcp_communications: [],
            llm_interaction_count: 0,
            mcp_communication_count: 0,
            total_interactions: 0,
            stage_interactions_duration_ms: null,
            chronological_interactions: []
          };
          
          handleParallelStageStarted(parentStage);
        } else if (eventType === 'stage.started' && update.parent_stage_execution_id !== undefined && update.parent_stage_execution_id !== null) {
          console.log('🔄 Parallel child stage starting - will replace placeholder');
          // Child stage starting - will be handled by full refresh which will replace placeholder
        }
        
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
      else if (eventType.startsWith('agent.')) {
        // Agent events (agent.cancelled)
        console.log('🔄 Agent event, refreshing stages');
        
        // Update summary immediately
        if (sessionId) {
          refreshSessionSummary(sessionId);
        }
        
        // Refresh stages to show updated agent status
        throttledUpdate(() => {
          if (sessionId) {
            refreshSessionStages(sessionId);
          }
        }, 250);
      }
      else if (eventType.startsWith('llm.') || eventType.startsWith('mcp.')) {
        // LLM/MCP interaction events (llm.interaction, mcp.tool_call, mcp.list_tools)
        // Update if session is active OR if there's an active chat on a terminal session
        const hasActiveChat = chatRef.current !== null;
        const isActive = sessionRef.current?.status && isActiveSessionStatus(sessionRef.current.status);
        
        if (isActive || hasActiveChat) {
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
      >
        {/* Session info */}
        {session && (
          <Typography variant="body2" sx={{ mr: 2, opacity: 0.8, color: 'white' }}>
            {session.stages?.length || 0} stages • {session.total_interactions || 0} interactions
          </Typography>
        )}
        
        {/* Live Updates indicator */}
        {session && isActiveSessionStatus(session.status) && !loading && (
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
          {session && isActiveSessionStatus(session.status) && (
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

            {/* Jump to Summary/Analysis button - shown at top for quick navigation to conclusion */}
            {(session.final_analysis_summary || session.final_analysis) && (
              <Box sx={{ display: 'flex', justifyContent: 'center', my: 1.5 }}>
                <Button
                  variant="text"
                  size="medium"
                  onClick={() => {
                    // Increment counter to force Final Analysis expansion
                    setExpandCounter(prev => prev + 1);
                    
                    // Scroll to Final Analysis Card (contains both summary and analysis)
                    // Wait for expansion animation (400ms) + buffer (100ms)
                    setTimeout(() => {
                      if (finalAnalysisRef.current) {
                        const yOffset = -20; // Offset for better visual positioning
                        const y = finalAnalysisRef.current.getBoundingClientRect().top + window.pageYOffset + yOffset;
                        window.scrollTo({ top: y, behavior: 'smooth' });
                      }
                    }, 500);
                  }}
                  startIcon={<KeyboardDoubleArrowDown />}
                  endIcon={<KeyboardDoubleArrowDown />}
                  sx={{
                    textTransform: 'none',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    py: 1,
                    px: 3,
                    color: 'primary.main',
                    '&:hover': {
                      backgroundColor: 'action.hover',
                    },
                  }}
                >
                  {session.final_analysis_summary ? 'Jump to Summary' : 'Jump to Final Analysis'}
                </Button>
              </Box>
            )}

            {/* Timeline Content - Conditional based on view type */}
            {session.stages && session.stages.length > 0 ? (
              <Suspense fallback={timelineSkeleton}>
                {(() => {
                  // Compute display status based on selected agent and parallel execution state
                  const displayStatus = (() => {
                    // If Map is empty, we're not in parallel execution → use session-level status
                    if (agentProgressStatuses.size === 0) {
                      return progressStatus;
                    }
                    
                    if (!selectedAgentExecutionId) {
                      // No agent selected in parallel context, use session-level status
                      return progressStatus;
                    }
                    
                    // Get the selected agent's status from the map
                    const agentStatus = agentProgressStatuses.get(selectedAgentExecutionId);
                    
                    if (!agentStatus) {
                      // Agent hasn't received its first status update yet → starting
                      return 'Starting...';
                    }
                    
                    if (isTerminalProgressStatus(agentStatus)) {
                      // Agent has finished (completed/failed/cancelled)
                      // Check if other agents are still running (have non-terminal statuses)
                      const otherAgentsRunning = Array.from(agentProgressStatuses.entries())
                        .some(([id, status]) => id !== selectedAgentExecutionId && !isTerminalProgressStatus(status));
                      
                      if (otherAgentsRunning) {
                        return 'Waiting for other agents...';
                      }
                      
                      // All agents are done, use session-level status
                      return progressStatus;
                    }
                    
                    // Agent is running, show its specific status
                    return agentStatus;
                  })();
                  
                  return timelineComponent(session, autoScrollEnabled, displayStatus, agentProgressStatuses, setSelectedAgentExecutionId);
                })()}
              </Suspense>
            ) : (session.status === SESSION_STATUS.PENDING || session.status === SESSION_STATUS.IN_PROGRESS) ? (
              // Session is active but stages haven't been created yet - show loading state
              <Box sx={{ py: 8, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                <CircularProgress size={48} />
                <Typography variant="body1" color="text.secondary">
                  Initializing investigation...
                </Typography>
              </Box>
            ) : (
              // Session is terminal or inactive but has no stages - this is an error
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

            {/* Chat Panel - Only shown for terminated sessions (completed, failed, cancelled) */}
            {/* Positioned here (after timeline, before final analysis) for better UX */}
            {isTerminalSessionStatus(session.status) && (
              <Box id="chat-panel">
                <ChatPanel
                  chat={chat}
                  isAvailable={chatAvailable}
                  onCreateChat={createChat}
                  onSendMessage={async (content) => {
                    await sendMessage(content, user?.email || 'anonymous');
                  }}
                  onCancelExecution={cancelExecution}
                  loading={chatLoading}
                  error={chatError}
                  sendingMessage={sendingMessage}
                  chatStageInProgress={chatStageInProgress}
                  canCancel={!!activeExecutionId}
                  canceling={canceling}
                  forceExpand={shouldExpandChat}
                  onCollapseAnalysis={() => setCollapseCounter(prev => prev + 1)}
                />
              </Box>
            )}

            {/* Final AI Analysis - Unified card with summary and detailed analysis */}
            {/* Executive summary shown at top (always visible), full analysis collapsible below */}
            {/* Auto-collapses when Jump to Chat is clicked (via collapseCounter) */}
            {/* Auto-expands when Jump to Final Analysis is clicked (via expandCounter) */}
            <Suspense fallback={<Skeleton variant="rectangular" height={200} />}>
              <FinalAnalysisCard 
                ref={finalAnalysisRef}
                analysis={session.final_analysis}
                summary={session.final_analysis_summary}
                sessionStatus={session.status}
                errorMessage={session.error_message}
                collapseCounter={collapseCounter}
                expandCounter={expandCounter}
              />
            </Suspense>

            {/* Jump to Chat button - shown after Final Analysis when chat is available */}
            {isTerminalSessionStatus(session.status) && (chat || chatAvailable) && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                <Button
                  variant="text"
                  size="medium"
                  onClick={() => {
                    // Increment counter to force Final Analysis collapse every time
                    setCollapseCounter(prev => prev + 1);
                    
                    // Trigger chat expansion (will only expand if not already expanded)
                    setShouldExpandChat(true);
                    setTimeout(() => setShouldExpandChat(false), 500);
                    
                    // Always scroll to the very bottom of the page
                    // Wait for Final Analysis collapse animation (400ms) + buffer
                    setTimeout(() => {
                      window.scrollTo({ 
                        top: document.documentElement.scrollHeight, 
                        behavior: 'smooth' 
                      });
                    }, 500);
                  }}
                  startIcon={<KeyboardDoubleArrowUp />}
                  endIcon={<KeyboardDoubleArrowUp />}
                  sx={{
                    textTransform: 'none',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    py: 1,
                    px: 3,
                    color: 'primary.main',
                    '&:hover': {
                      backgroundColor: 'action.hover',
                    },
                  }}
                >
                  Jump to Follow-up Chat
                </Button>
              </Box>
            )}

            {/* Bottom Pause Alert - For paused sessions, shown at the end for easy access after scrolling */}
            {session.status === SESSION_STATUS.PAUSED && session.pause_metadata && (
              <>
                <Alert 
                  severity="warning" 
                  icon={<PauseCircle />}
                  sx={{ mt: 3 }}
                  action={
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Tooltip title="Resumes all paused agents" arrow>
                        <span>
                          <Button
                            color="inherit"
                            size="small"
                            variant="contained"
                            startIcon={isBottomResuming ? <CircularProgress size={14} color="inherit" /> : <PlayArrow />}
                            disabled={isBottomResuming || isBottomCanceling}
                            aria-label={isBottomResuming ? "Resuming session" : "Resume paused session"}
                            onClick={async () => {
                              setIsBottomResuming(true);
                              setBottomResumeError(null);
                              try {
                                const { apiClient } = await import('../services/api');
                                await apiClient.resumeSession(session.session_id);
                                // WebSocket will update the session status
                              } catch (error) {
                                const { handleAPIError } = await import('../services/api');
                                const errorMessage = handleAPIError(error);
                                setBottomResumeError(errorMessage);
                              } finally {
                                setIsBottomResuming(false);
                              }
                            }}
                            sx={{
                              fontWeight: 600,
                              backgroundColor: 'warning.main',
                              color: 'white',
                              '& .MuiSvgIcon-root': {
                                color: 'white',
                              },
                              '&:hover': {
                                backgroundColor: 'warning.dark',
                              },
                            }}
                          >
                            {isBottomResuming ? 'Resuming...' : 'Resume'}
                          </Button>
                        </span>
                      </Tooltip>
                      <Tooltip title="Cancels entire session" arrow>
                        <span>
                          <Button
                            color="error"
                            size="small"
                            variant="outlined"
                            startIcon={isBottomCanceling ? <CircularProgress size={14} color="inherit" /> : undefined}
                            onClick={() => {
                              setShowBottomCancelDialog(true);
                              setBottomCancelError(null);
                            }}
                            disabled={isBottomCanceling || isBottomResuming}
                            aria-label={isBottomCanceling ? "Canceling session" : "Cancel session"}
                            sx={{
                              fontWeight: 600,
                              '&:hover': {
                                backgroundColor: 'error.main',
                                borderColor: 'error.main',
                                color: 'white',
                              },
                            }}
                          >
                            {isBottomCanceling ? 'Canceling...' : 'Cancel'}
                          </Button>
                        </span>
                      </Tooltip>
                    </Box>
                  }
                >
                  <AlertTitle sx={{ fontWeight: 600 }}>Session Paused</AlertTitle>
                  {session.pause_metadata.message || 'Session is paused and awaiting action.'}
                  {bottomResumeError && (
                    <Box sx={(theme) => ({ 
                      mt: 2, 
                      p: 2, 
                      bgcolor: alpha(theme.palette.error.main, 0.05), 
                      borderRadius: 1, 
                      border: '1px solid', 
                      borderColor: 'error.main' 
                    })}>
                      <Typography variant="body2" color="error.main">
                        {bottomResumeError}
                      </Typography>
                    </Box>
                  )}
                </Alert>

                {/* Bottom Cancel Confirmation Dialog */}
                <Dialog
                  open={showBottomCancelDialog}
                  onClose={() => {
                    if (!isBottomCanceling) {
                      setShowBottomCancelDialog(false);
                      setBottomCancelError(null);
                    }
                  }}
                  maxWidth="sm"
                  fullWidth
                >
                  <DialogTitle>Cancel Session?</DialogTitle>
                  <DialogContent>
                    <DialogContentText>
                      Are you sure you want to cancel this session? This action cannot be undone.
                      The session will be marked as cancelled and any ongoing processing will be stopped.
                    </DialogContentText>
                    {bottomCancelError && (
                      <Box sx={(theme) => ({ 
                        mt: 2, 
                        p: 2, 
                        bgcolor: alpha(theme.palette.error.main, 0.05), 
                        borderRadius: 1, 
                        border: '1px solid', 
                        borderColor: 'error.main' 
                      })}>
                        <Typography variant="body2" color="error.main">
                          {bottomCancelError}
                        </Typography>
                      </Box>
                    )}
                  </DialogContent>
                  <DialogActions sx={{ px: 3, pb: 2 }}>
                    <Button 
                      onClick={() => {
                        setShowBottomCancelDialog(false);
                        setBottomCancelError(null);
                      }}
                      disabled={isBottomCanceling}
                      color="inherit"
                    >
                      Cancel
                    </Button>
                    <Button 
                      onClick={async () => {
                        setIsBottomCanceling(true);
                        setBottomCancelError(null);
                        
                        try {
                          const { apiClient } = await import('../services/api');
                          await apiClient.cancelSession(session.session_id);
                          // Close dialog on success
                          setShowBottomCancelDialog(false);
                          // WebSocket will update the session status
                        } catch (error) {
                          // Show error, allow retry
                          const { handleAPIError } = await import('../services/api');
                          const errorMessage = handleAPIError(error);
                          setBottomCancelError(errorMessage);
                        } finally {
                          // Always reset the canceling flag after the API call completes
                          setIsBottomCanceling(false);
                        }
                      }}
                      variant="contained" 
                      color="warning"
                      disabled={isBottomCanceling}
                      startIcon={isBottomCanceling ? <CircularProgress size={16} color="inherit" /> : undefined}
                    >
                      {isBottomCanceling ? 'CANCELING...' : 'CONFIRM CANCELLATION'}
                    </Button>
                  </DialogActions>
                </Dialog>
              </>
            )}
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
