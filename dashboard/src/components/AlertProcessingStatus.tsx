/**
 * Alert processing status component - EP-0018
 * Adapted from alert-dev-ui ProcessingStatus.tsx for dashboard integration
 * Shows real-time progress of alert processing via WebSocket
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  LinearProgress,
  Alert,
  Chip,
  Paper,
  Button,
  Tooltip,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  HourglassTop as HourglassIcon,
  OpenInNew as OpenInNewIcon,
  Visibility as VisibilityIcon,
} from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';

import type { ProcessingStatus, ProcessingStatusProps } from '../types';
import { websocketService } from '../services/websocketService';
import { apiClient } from '../services/api';

const AlertProcessingStatus: React.FC<ProcessingStatusProps> = ({ sessionId, onComplete }) => {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Store onComplete in a ref to avoid effect re-runs when it changes
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;
  
  // Track if component is mounted to prevent state updates after unmount
  const isMountedRef = useRef(true);
  
  // Track if onComplete has been called for this alert to prevent duplicates
  const didCompleteRef = useRef(false);
  
  // Track terminal state immediately (not waiting for React state update)
  const isTerminalRef = useRef(false);

  useEffect(() => {
    // Reset mount flag on (re)mount or session change
    isMountedRef.current = true;
    // New session -> allow onComplete again
    didCompleteRef.current = false;
    // Reset terminal state for new session
    isTerminalRef.current = false;
    
    // Initialize WebSocket connection status
    const initialConnectionStatus = websocketService.isConnected;
    setWsConnected(initialConnectionStatus);
    if (!initialConnectionStatus) {
      setWsError('Connecting...');
      setTimeout(() => {
        if (websocketService.isConnected) {
          setWsError(null);
        }
      }, 1000);
    }

    // Set initial processing status
    setStatus({
      session_id: sessionId,
      status: 'processing',
      progress: 10,
      current_step: 'Session initialized, processing alert...',
      timestamp: new Date().toISOString()
    });

    // Handle connection changes
    const handleConnectionChange = (connected: boolean) => {
      setWsConnected(connected);
      setWsError(connected ? null : 'Connection lost');
    };

    // Set up basic connection monitoring
    const unsubscribeConnection = websocketService.onConnectionChange(handleConnectionChange);
    
    return () => {
      isMountedRef.current = false; // Mark component as unmounted
      unsubscribeConnection();
    };
  }, [sessionId]);

  // Set up session-specific WebSocket subscription
  useEffect(() => {
    // Ensure WebSocket is connected before subscribing
    const setupSubscription = async () => {
      try {
        await websocketService.connect();
      } catch (error) {
        console.error('Failed to connect to WebSocket before subscription:', error);
      }
    };
    
    setupSubscription();
    
    // Handle session-specific updates using pattern matching for robustness
    const handleSessionUpdate = (update: any) => {
      const eventType = update.type || '';
      
      // Prevent overwriting terminal states with intermediate events (catchup protection)
      // Once completed or errored, ignore all processing/stage/interaction events
      // Use ref to check immediately (React state updates are async)
      if (isTerminalRef.current && !eventType.startsWith('session.')) {
        return;
      }
      
      let updatedStatus: ProcessingStatus | null = null;

      if (eventType.startsWith('session.')) {
        // Session lifecycle events
        const isCompleted = eventType === 'session.completed';
        const isFailed = eventType === 'session.failed';
        
        updatedStatus = {
          session_id: sessionId,
          status: isCompleted ? 'completed' : isFailed ? 'error' : 'processing',
          progress: 0,
          current_step: isCompleted ? 'Processing completed' : 
                       isFailed ? 'Processing failed' : 'Processing...',
          timestamp: new Date().toISOString(),
          error: update.error_message || undefined,
          result: update.final_analysis || undefined
        };
        
        // Fetch final analysis when session completes (real-time events don't include it)
        if (isCompleted && sessionId && !update.final_analysis) {
          (async () => {
            try {
              const sessionDetails = await apiClient.getSessionDetail(sessionId);
              if (sessionDetails.final_analysis && isMountedRef.current) {
                setStatus(prev => prev ? {
                  ...prev,
                  result: sessionDetails.final_analysis || undefined
                } : prev);
              }
            } catch (error) {
              console.error('Failed to fetch final analysis:', error);
            }
          })();
        }
      } 
      else if (eventType.startsWith('stage.')) {
        // Stage events - always keep status as 'processing'
        // Terminal state is only determined by session.completed/session.failed
        updatedStatus = {
          session_id: sessionId,
          status: 'processing',
          progress: 0,
          current_step: `Stage: ${update.stage_name || 'Processing'}`,
          timestamp: new Date().toISOString()
        };
      } 
      else if (eventType.startsWith('llm.')) {
        // LLM interaction events
        updatedStatus = {
          session_id: sessionId,
          status: 'processing',
          progress: 0,
          current_step: 'Analyzing with AI...',
          timestamp: new Date().toISOString()
        };
      } 
      else if (eventType.startsWith('mcp.')) {
        // MCP interaction events
        updatedStatus = {
          session_id: sessionId,
          status: 'processing',
          progress: 0,
          current_step: 'Gathering system information...',
          timestamp: new Date().toISOString()
        };
      }

      if (updatedStatus) {
        // Mark terminal state immediately (before React state update) to prevent race conditions
        // Only session.completed or session.failed should trigger terminal state
        const isSessionTerminal = eventType === 'session.completed' || eventType === 'session.failed';
        if (isSessionTerminal) {
          isTerminalRef.current = true;
        }
        
        setStatus(updatedStatus);
        
        // Call onComplete callback only when session completes or fails (not on stage.failed)
        if (isSessionTerminal && onCompleteRef.current && !didCompleteRef.current) {
          didCompleteRef.current = true; // Mark as completed to prevent duplicate calls
          setTimeout(() => {
            if (onCompleteRef.current) {
              onCompleteRef.current();
            }
          }, 1000);
        }
      }
    };
    
    // Set up the session-specific event handler
    const sessionChannel = `session:${sessionId}`;
    const unsubscribeSession = websocketService.subscribeToChannel(sessionChannel, handleSessionUpdate);

    return () => {
      unsubscribeSession();
    };
  }, [sessionId]); // sessionId dependency

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'queued':
      case 'processing':
        return 'info'; // Match main dashboard color for processing
      case 'completed':
        return 'success';
      case 'error':
        return 'error';
      default:
        return 'primary';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon color="success" />;
      case 'error':
        return <ErrorIcon color="error" />;
      case 'processing':
      case 'queued':
        return <HourglassIcon color="primary" />;
      default:
        return null;
    }
  };

  if (!status) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Processing...
          </Typography>
          <LinearProgress />
          {wsError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {wsError}
            </Alert>
          )}
        </CardContent>
      </Card>
    );
  }

  // Handle opening alert detail view
  const handleViewDetails = () => {
    if (status?.session_id) {
      const url = `${window.location.origin}/sessions/${status.session_id}`;
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h6">
              Alert Processing Status
            </Typography>
            <Box display="flex" alignItems="center" gap={1}>
              {getStatusIcon(status.status)}
              <Chip 
                label={status.status.toUpperCase()} 
                color={getStatusColor(status.status)} 
                size="small"
              />
            </Box>
          </Box>

          <Box 
            display="flex" 
            alignItems="center" 
            justifyContent="space-between" 
            flexWrap="wrap"
            gap={2}
            mb={2}
          >
            <Typography variant="body2" color="text.secondary">
              Session ID: {status.session_id}
            </Typography>
            
            <Tooltip title="Open detailed alert view in new tab" arrow>
              <Button
                variant="contained"
                color="success"
                size="medium"
                startIcon={<VisibilityIcon />}
                endIcon={<OpenInNewIcon />}
                onClick={handleViewDetails}
                sx={{ 
                  boxShadow: 2,
                  px: 2.5,
                  '&:hover': {
                    boxShadow: 4,
                  }
                }}
              >
                View Full Details
              </Button>
            </Tooltip>
          </Box>

          <Box mb={3}>
            <Typography variant="body1" gutterBottom>
              {status.current_step}
            </Typography>
            {status.status === 'processing' && (
              <LinearProgress 
                variant="indeterminate" 
                sx={{ 
                  height: 8,
                  borderRadius: 1,
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 1,
                  }
                }} 
                color={getStatusColor(status.status)} 
              />
            )}
          </Box>

          {status.error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="body2">
                <strong>Error:</strong> {status.error}
              </Typography>
            </Alert>
          )}

          <Box mt={2}>
            <Typography variant="body2" color="text.secondary">
              Connection Status: {wsConnected ? '🟢 Connected' : (wsError === 'Connecting...' ? '🟡 Connecting...' : '🔴 Disconnected')}
            </Typography>
            {status.timestamp && (
              <Typography variant="body2" color="text.secondary">
                Last Update: {new Date(status.timestamp).toLocaleString()}
              </Typography>
            )}
          </Box>
        </CardContent>
      </Card>

      {status.result && status.status === 'completed' && (
        <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Processing Result
              </Typography>
              <Paper 
                variant="outlined" 
                sx={{ 
                  p: 3, 
                  bgcolor: 'grey.50',
                  maxHeight: '70vh',
                  overflow: 'auto'
                }}
              >
                <ReactMarkdown
                  urlTransform={defaultUrlTransform}
                  components={{
                    // Custom styling for markdown elements
                    h1: ({ children, ...props }) => (
                      <Typography variant="h5" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold' }} {...props}>
                        {children}
                      </Typography>
                    ),
                    h2: ({ children, ...props }) => (
                      <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 2 }} {...props}>
                        {children}
                      </Typography>
                    ),
                    h3: ({ children, ...props }) => (
                      <Typography variant="subtitle1" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 1.5 }} {...props}>
                        {children}
                      </Typography>
                    ),
                    p: ({ children, ...props }) => (
                      <Typography 
                        variant="body1" 
                        sx={{ 
                          lineHeight: 1.6,
                          fontSize: '0.95rem',
                          mb: 1
                        }}
                        {...props}
                      >
                        {children}
                      </Typography>
                    ),
                    ul: ({ children, ...props }) => (
                      <Box component="ul" sx={{ pl: 2, mb: 1 }} {...props}>
                        {children}
                      </Box>
                    ),
                    li: ({ children, ...props }) => (
                      <Typography component="li" variant="body1" sx={{ fontSize: '0.95rem', lineHeight: 1.6, mb: 0.5 }} {...props}>
                        {children}
                      </Typography>
                    ),
                    code: ({ children, className, ...props }) => (
                      <Typography
                        component={className ? "pre" : "code"}
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.85rem',
                          bgcolor: className ? 'grey.100' : 'grey.200',
                          p: className ? 1 : 0.5,
                          borderRadius: 1,
                          display: className ? 'block' : 'inline',
                          whiteSpace: className ? 'pre-wrap' : 'pre',
                          wordBreak: 'break-word',
                          border: `1px solid`,
                          borderColor: 'divider'
                        }}
                        {...props}
                      >
                        {children}
                      </Typography>
                    ),
                    blockquote: ({ children, ...props }) => (
                      <Box
                        component="blockquote"
                        sx={{
                          borderLeft: '4px solid',
                          borderColor: 'primary.main',
                          pl: 2,
                          py: 1,
                          bgcolor: 'grey.50',
                          fontStyle: 'italic',
                          mb: 1
                        }}
                        {...props}
                      >
                        {children}
                      </Box>
                    ),
                  }}
                >
                  {status.result}
                </ReactMarkdown>
              </Paper>
            </CardContent>
          </Card>
      )}
    </Box>
  );
};

export default AlertProcessingStatus;
