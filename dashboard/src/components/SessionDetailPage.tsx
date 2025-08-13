import { useState, useEffect } from 'react';
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
  Skeleton
} from '@mui/material';
import { ArrowBack } from '@mui/icons-material';
import { apiClient, handleAPIError } from '../services/api';
import { webSocketService } from '../services/websocket';
import type { DetailedSession, SessionUpdate } from '../types';
import SessionHeader from './SessionHeader';
import OriginalAlertCard from './OriginalAlertCard';
import FinalAnalysisCard from './FinalAnalysisCard';
import TimelineVisualization from './TimelineVisualization';
import NestedAccordionTimeline from './NestedAccordionTimeline';


/**
 * SessionDetailPage component - Phase 3
 * Displays comprehensive session details including original alert data, timeline, and final analysis
 */
function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  
  // Session detail state
  const [session, setSession] = useState<DetailedSession | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch session detail data
  const fetchSessionDetail = async (id: string) => {
    try {
      setLoading(true);
      setError(null);
      console.log('Fetching session detail for ID:', id);
      
      const sessionData = await apiClient.getSessionDetail(id);
      
      // Validate and normalize session status to prevent "Unknown" status
      const normalizedStatus = ['completed', 'failed', 'in_progress', 'pending'].includes(sessionData.status) 
        ? sessionData.status 
        : 'in_progress'; // Default to in_progress if status is unexpected
      
      const normalizedSession = {
        ...sessionData,
        status: normalizedStatus as 'completed' | 'failed' | 'in_progress' | 'pending'
      };
      
      setSession(normalizedSession);
      console.log('Session detail loaded:', normalizedSession);
    } catch (err) {
      const errorMessage = handleAPIError(err);
      setError(errorMessage);
      console.error('Failed to fetch session detail:', err);
    } finally {
      setLoading(false);
    }
  };

  // Set up WebSocket subscriptions immediately when component mounts
  useEffect(() => {
    if (!sessionId) return;

    console.log('Setting up WebSocket subscriptions for session:', sessionId);
    
    // Connect to WebSocket and subscribe to session-specific channel FIRST
    webSocketService.connect();
    webSocketService.subscribeToSessionChannel(sessionId);

    // Set up handlers after subscription
    const setupHandlers = () => {
      // Handle session updates (status changes, progress updates, etc.)
      const handleSessionUpdate = (update: SessionUpdate) => {
        console.log('SessionDetailPage received session update:', update);
        
        // Only process updates for the current session
        if (update.session_id === sessionId) {
          console.log('Processing update for current session:', sessionId);
          
          // Check if this update contains timeline-related data - handle incrementally
          if (update.data && (update.data.interaction_type === 'llm' || update.data.interaction_type === 'mcp')) {
            console.log('Timeline interaction found in session update, updating timeline');
            return;
          }
          
          // Check if this is a status change - handle incrementally
          if (update.data && update.data.type === 'session_status_change') {
            console.log('Session status change found in session update, updating status');
            setSession(prevSession => {
              if (!prevSession) return prevSession;
              
              // Validate status before updating
              const newStatus = update.data.status;
              const validatedStatus = ['completed', 'failed', 'in_progress', 'pending'].includes(newStatus) 
                ? newStatus 
                : prevSession.status;
              
              return {
                ...prevSession,
                status: validatedStatus,
                completed_at_us: validatedStatus === 'completed' ? Date.now() * 1000 : prevSession.completed_at_us,
                final_analysis: update.data.final_analysis || prevSession.final_analysis,
                error_message: update.data.error_message || prevSession.error_message
              };
            });
            return;
          }
          
          // Update session with new data from the update
          setSession(prevSession => {
            if (!prevSession) return prevSession;
            
            // Validate status before updating
            const newStatus = update.status;
            const validatedStatus = ['completed', 'failed', 'in_progress', 'pending'].includes(newStatus) 
              ? newStatus 
              : prevSession.status;
            
            const updatedSession = {
              ...prevSession,
              status: validatedStatus,
              duration_ms: update.duration_ms ?? prevSession.duration_ms,
              error_message: update.error_message ?? prevSession.error_message,
              completed_at_us: update.completed_at_us ?? prevSession.completed_at_us
            };
            
            console.log('Updated session state:', updatedSession);
            return updatedSession;
          });
        } else {
          console.log('Ignoring update for different session:', update.session_id);
        }
      };

      // Handle session-specific timeline updates (LLM/MCP interactions)
      const handleSessionSpecificUpdate = async (data: any) => {
        console.log('SessionDetailPage received session-specific update:', data);
        
        // Handle session status changes - update session state without refetching
        if (data.type === 'session_status_change') {
          console.log('Session status change detected, updating session state');
          
          // Check if this is a chain session that might have stage changes
          const isChainSession = session?.chain_id || session?.chain_execution;
          
          // For chain sessions, we need to refetch to get updated stage information
          // because stage progress updates are critical for the UI
          if (isChainSession && (data.status === 'in_progress' || data.current_stage_index !== undefined)) {
            console.log('Chain session stage-related status change detected, fetching updated session data');
            fetchSessionDetail(sessionId);
            return;
          }
          
          setSession(prevSession => {
            if (!prevSession) return prevSession;
            
            // Validate status before updating
            const newStatus = data.status;
            const validatedStatus = ['completed', 'failed', 'in_progress', 'pending'].includes(newStatus) 
              ? newStatus 
              : prevSession.status;
            
            return {
              ...prevSession,
              status: validatedStatus,
              completed_at_us: validatedStatus === 'completed' ? Date.now() * 1000 : prevSession.completed_at_us,
              final_analysis: data.final_analysis || prevSession.final_analysis,
              error_message: data.error_message || prevSession.error_message,
              // Update duration if we can calculate it
              duration_ms: validatedStatus === 'completed' && prevSession.started_at_us ? 
                Math.round((Date.now() * 1000 - prevSession.started_at_us) / 1000) : 
                prevSession.duration_ms
            };
          });
          
          console.log('Session state updated from WebSocket data, no refetch needed');
          return;
        }
        // Handle batched timeline updates - intelligently update only new timeline items
        else if (data.type === 'batched_session_updates' && data.updates) {
          console.log('Timeline batch update detected, fetching new timeline items smoothly');
          
          // Get the current timeline length to detect new items
          const currentTimelineLength = session?.chronological_timeline?.length || 0;
          
          // WebSocket updates only contain previews, so we need to refetch for complete details
          // But we'll do it smartly to avoid full screen refresh
          try {
            const updatedSessionData = await apiClient.getSessionDetail(sessionId);
            
            // Only update if we actually have new timeline items
            if (updatedSessionData.chronological_timeline.length > currentTimelineLength) {
              setSession(prevSession => {
                if (!prevSession) return updatedSessionData;
                
                // Merge with existing session data, only updating timeline and essential fields
                return {
                  ...prevSession,
                  chronological_timeline: updatedSessionData.chronological_timeline,
                  status: updatedSessionData.status,
                  duration_ms: updatedSessionData.duration_ms,
                  completed_at_us: updatedSessionData.completed_at_us,
                  final_analysis: updatedSessionData.final_analysis || prevSession.final_analysis,
                  error_message: updatedSessionData.error_message || prevSession.error_message
                };
              });
              
              console.log(`Timeline updated smoothly: ${updatedSessionData.chronological_timeline.length - currentTimelineLength} new items added`);
            } else {
              console.log('No new timeline items detected, skipping update');
            }
          } catch (error) {
            console.error('Failed to fetch updated timeline:', error);
            // Fallback to basic session update without timeline details
          }
        }
        // Handle stage progress updates - update chain execution smoothly without full refresh
        else if (data.type === 'stage_progress') {
          console.log('Stage progress update detected, updating chain execution smoothly');
          
          try {
            // Fetch updated session data to get latest stage information
            const updatedSessionData = await apiClient.getSessionDetail(sessionId);
            
            setSession(prevSession => {
              if (!prevSession) return updatedSessionData;
              
              // Only update the chain execution and essential fields, preserve everything else
              return {
                ...prevSession,
                chain_execution: updatedSessionData.chain_execution || prevSession.chain_execution,
                current_stage_index: updatedSessionData.current_stage_index ?? prevSession.current_stage_index,
                completed_stages: updatedSessionData.completed_stages ?? prevSession.completed_stages,
                failed_stages: updatedSessionData.failed_stages ?? prevSession.failed_stages,
                status: updatedSessionData.status || prevSession.status,
                duration_ms: updatedSessionData.duration_ms ?? prevSession.duration_ms,
                completed_at_us: updatedSessionData.completed_at_us ?? prevSession.completed_at_us,
                final_analysis: updatedSessionData.final_analysis || prevSession.final_analysis,
                error_message: updatedSessionData.error_message || prevSession.error_message
              };
            });
            
            console.log(`Stage progress updated smoothly for stage: ${data.stage_name} (${data.status})`);
          } catch (error) {
            console.error('Failed to fetch updated stage data:', error);
          }
          
          return;
        }
        // Handle individual timeline interactions (fallback) - rarely used now
        else if (data.interaction_type === 'llm' || data.interaction_type === 'mcp') {
          console.log('Individual timeline interaction detected, updating timeline smoothly');
          // Use the same smooth update approach as batched updates
          try {
            const updatedSessionData = await apiClient.getSessionDetail(sessionId);
            const currentTimelineLength = session?.chronological_timeline?.length || 0;
            
            if (updatedSessionData.chronological_timeline.length > currentTimelineLength) {
              setSession(prevSession => {
                if (!prevSession) return updatedSessionData;
                
                return {
                  ...prevSession,
                  chronological_timeline: updatedSessionData.chronological_timeline,
                  status: updatedSessionData.status,
                  duration_ms: updatedSessionData.duration_ms,
                  completed_at_us: updatedSessionData.completed_at_us,
                  final_analysis: updatedSessionData.final_analysis || prevSession.final_analysis,
                  error_message: updatedSessionData.error_message || prevSession.error_message
                };
              });
            }
          } catch (error) {
            console.error('Failed to fetch updated timeline for individual interaction:', error);
          }
        } 
        // Handle individual LLM/MCP interactions - refresh timeline to show new interactions
        else if (data.type === 'llm_interaction' || data.type === 'mcp_communication' || data.type === 'mcp_tool_list') {
          console.log(`New ${data.type} detected, refreshing timeline to show latest interactions`);
          
          try {
            const updatedSessionData = await apiClient.getSessionDetail(sessionId);
            
            // Update session with latest timeline data
            setSession(prevSession => {
              if (!prevSession) return updatedSessionData;
              
              return {
                ...prevSession,
                chronological_timeline: updatedSessionData.chronological_timeline,
                llm_interaction_count: updatedSessionData.llm_interaction_count,
                mcp_communication_count: updatedSessionData.mcp_communication_count
              };
            });
            
            console.log('Timeline updated with new interaction data');
          } catch (error) {
            console.error('Failed to refresh timeline after interaction update:', error);
          }
        }
        // Handle any other session-specific updates - log and potentially ignore
        else {
          console.log('Other session-specific update type:', data.type, '- ignoring to prevent unnecessary refetch');
        }
      };

      // Handle session completion - refresh full session data to get final analysis and timeline
      const handleSessionCompleted = (update: SessionUpdate) => {
        console.log('SessionDetailPage received session completed:', update);
        
        // Only process updates for the current session
        if (update.session_id === sessionId) {
          console.log('Current session completed, refreshing full session data');
          // Fetch fresh session data to get final analysis and complete timeline
          fetchSessionDetail(sessionId);
        }
      };

      // Handle session failure - refresh full session data to get error details
      const handleSessionFailed = (update: SessionUpdate) => {
        console.log('SessionDetailPage received session failed:', update);
        
        // Only process updates for the current session
        if (update.session_id === sessionId) {
          console.log('Current session failed, refreshing full session data');
          // Fetch fresh session data to get error details and final state
          fetchSessionDetail(sessionId);
        }
      };

      // Note: Stage progress updates are now handled smoothly in handleSessionSpecificUpdate above
      // to avoid full page refreshes

      // Handle WebSocket connection changes - refresh data on reconnection
      const handleConnectionChange = (connected: boolean) => {
        if (connected) {
          console.log('✅ WebSocket reconnected in SessionDetailPage - syncing session data');
          // Refresh session data to sync with backend state after reconnection
          fetchSessionDetail(sessionId);
        } else {
          console.log('❌ WebSocket disconnected in SessionDetailPage');
        }
      };

      // Subscribe to WebSocket events
      const unsubscribeUpdate = webSocketService.onSessionUpdate(handleSessionUpdate);
      const unsubscribeCompleted = webSocketService.onSessionCompleted(handleSessionCompleted);
      const unsubscribeFailed = webSocketService.onSessionFailed(handleSessionFailed);
      const unsubscribeConnection = webSocketService.onConnectionChange(handleConnectionChange);
      
      // Note: Stage progress events are now handled in session-specific updates
      // No need for separate stage progress subscription
      const unsubscribeStageProgress = () => {};

      // Subscribe to session-specific channel for timeline updates
      const sessionChannel = `session_${sessionId}`;
      const unsubscribeSessionSpecific = webSocketService.onSessionSpecificUpdate(
        sessionChannel, 
        handleSessionSpecificUpdate
      );

      return { unsubscribeUpdate, unsubscribeCompleted, unsubscribeFailed, unsubscribeConnection, unsubscribeStageProgress, unsubscribeSessionSpecific };
    };

    const { unsubscribeUpdate, unsubscribeCompleted, unsubscribeFailed, unsubscribeConnection, unsubscribeStageProgress, unsubscribeSessionSpecific } = setupHandlers();

    // Cleanup subscriptions
    return () => {
      console.log('SessionDetailPage cleaning up WebSocket subscriptions');
      unsubscribeUpdate();
      unsubscribeCompleted();
      unsubscribeFailed();
      unsubscribeConnection();
      unsubscribeStageProgress();
      unsubscribeSessionSpecific();
      
      // Unsubscribe from session-specific channel
      webSocketService.unsubscribeFromSessionChannel(sessionId);
    };
  }, [sessionId]);

  // Load session data AFTER WebSocket subscriptions are set up
  useEffect(() => {
    if (sessionId) {
      // Small delay to ensure WebSocket subscription is active
      const timeoutId = setTimeout(() => {
        fetchSessionDetail(sessionId);
      }, 100);
      
      return () => clearTimeout(timeoutId);
    } else {
      setError('Session ID not provided');
      setLoading(false);
    }
  }, [sessionId]);

  // Handle back navigation
  const handleBack = () => {
    navigate('/dashboard');
  };

  // Handle retry
  const handleRetry = () => {
    if (sessionId) {
      fetchSessionDetail(sessionId);
    }
  };

  return (
    <Container maxWidth={false} sx={{ px: 2 }}>
      {/* AppBar with back button and title */}
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
          </Typography>
          
          {/* Real-time status indicator for active sessions */}
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
        {/* Loading state */}
        {loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Session header skeleton */}
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

            {/* Original alert card skeleton */}
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

            {/* Timeline skeleton */}
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

        {/* Session detail content */}
        {session && !loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Session Header */}
            <SessionHeader session={session} />

            {/* Original Alert Data */}
            <OriginalAlertCard alertData={session.alert_data} />

            {/* Enhanced Processing Timeline */}
            {session.chain_execution ? (
              <NestedAccordionTimeline
                chainExecution={session.chain_execution}
                timelineItems={session.chronological_timeline}
              />
            ) : (
              <TimelineVisualization 
                timelineItems={session.chronological_timeline}
                isActive={session.status === 'in_progress' || session.status === 'pending'}
                sessionId={session.session_id}
              />
            )}

            {/* Final AI Analysis */}
            <FinalAnalysisCard 
              analysis={session.final_analysis}
              sessionStatus={session.status}
              errorMessage={session.error_message}
            />
          </Box>
        )}

        {/* Empty state for missing session */}
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

export default SessionDetailPage; 