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
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  HourglassTop as HourglassIcon,
} from '@mui/icons-material';
import ReactMarkdown from 'react-markdown';

import type { ProcessingStatus, ProcessingStatusProps } from '../types';
import { webSocketService } from '../services/websocket';

const AlertProcessingStatus: React.FC<ProcessingStatusProps> = ({ alertId, onComplete }) => {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Store onComplete in a ref to avoid effect re-runs when it changes
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    // Use the existing dashboard WebSocket service
    const initialConnectionStatus = webSocketService.isConnected;
    setWsConnected(initialConnectionStatus);
    // Don't show error during initial connection attempt
    if (!initialConnectionStatus) {
      setWsError('Connecting...');
      // Clear error after a moment to avoid flickering
      setTimeout(() => {
        if (webSocketService.isConnected) {
          setWsError(null);
        }
      }, 1000);
    }

    // Set initial processing status
    setStatus({
      alert_id: alertId,
      status: 'processing',
      progress: 10,
      current_step: 'Alert submitted, processing started...',
      timestamp: new Date().toISOString()
    });

    // Handle dashboard updates for this specific alert/session
    const handleDashboardUpdate = (update: any) => {
      console.log('🔄 Alert processing update:', update);

      // Handle different types of updates
      let updatedStatus: ProcessingStatus | null = null;

      if (update.type === 'session_status_change') {
        updatedStatus = {
          alert_id: alertId,
          status: update.status === 'completed' ? 'completed' : 
                 update.status === 'failed' ? 'error' : 'processing',
          progress: 0, // We'll use indeterminate progress
          current_step: update.status === 'completed' ? 'Processing completed' : 
                       update.status === 'failed' ? 'Processing failed' : 'Processing...',
          timestamp: new Date().toISOString(),
          error: update.error_message || undefined,
          result: update.final_analysis || undefined
        };
      } else if (update.type === 'stage_progress') {
        updatedStatus = {
          alert_id: alertId,
          status: update.status === 'completed' ? 'completed' : 
                 update.status === 'failed' ? 'error' : 'processing',
          progress: 0,
          current_step: `Stage: ${update.stage_name || 'Processing'}`,
          timestamp: new Date().toISOString()
        };
      } else if (update.type === 'llm_interaction') {
        updatedStatus = {
          alert_id: alertId,
          status: 'processing',
          progress: 0,
          current_step: 'Analyzing with AI...',
          timestamp: new Date().toISOString()
        };
      } else if (update.type === 'mcp_interaction') {
        updatedStatus = {
          alert_id: alertId,
          status: 'processing',
          progress: 0,
          current_step: 'Gathering system information...',
          timestamp: new Date().toISOString()
        };
      }

      if (updatedStatus) {
        setStatus(updatedStatus);
        
        // Call onComplete callback when processing is done
        if (updatedStatus.status === 'completed' && onCompleteRef.current) {
          setTimeout(() => {
            if (onCompleteRef.current) onCompleteRef.current();
          }, 1000);
        }
      }
    };

    // Handle connection changes
    const handleConnectionChange = (connected: boolean) => {
      console.log('🔗 WebSocket connection changed:', connected);
      setWsConnected(connected);
      setWsError(connected ? null : 'Connection lost');
    };

    // Subscribe to dashboard updates
    const unsubscribeDashboard = webSocketService.onDashboardUpdate(handleDashboardUpdate);
    const unsubscribeConnection = webSocketService.onConnectionChange(handleConnectionChange);

    return () => {
      unsubscribeDashboard();
      unsubscribeConnection();
    };
  }, [alertId]);

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

          <Typography variant="body2" color="text.secondary" gutterBottom>
            Alert ID: {status.alert_id}
          </Typography>

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
                  components={{
                    // Custom styling for markdown elements
                    h1: ({ children }) => (
                      <Typography variant="h5" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold' }}>
                        {children}
                      </Typography>
                    ),
                    h2: ({ children }) => (
                      <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 2 }}>
                        {children}
                      </Typography>
                    ),
                    h3: ({ children }) => (
                      <Typography variant="subtitle1" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 1.5 }}>
                        {children}
                      </Typography>
                    ),
                    p: ({ children }) => (
                      <Typography 
                        variant="body1" 
                        sx={{ 
                          lineHeight: 1.6,
                          fontSize: '0.95rem',
                          mb: 1
                        }}
                      >
                        {children}
                      </Typography>
                    ),
                    ul: ({ children }) => (
                      <Box component="ul" sx={{ pl: 2, mb: 1 }}>
                        {children}
                      </Box>
                    ),
                    li: ({ children }) => (
                      <Typography component="li" variant="body1" sx={{ fontSize: '0.95rem', lineHeight: 1.6, mb: 0.5 }}>
                        {children}
                      </Typography>
                    ),
                    code: ({ children, className }) => (
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
                      >
                        {children}
                      </Typography>
                    ),
                    blockquote: ({ children }) => (
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
