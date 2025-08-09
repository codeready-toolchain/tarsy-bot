/**
 * Processing status component to show real-time progress
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
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  HourglassTop as HourglassIcon,
} from '@mui/icons-material';

import { ProcessingStatus as ProcessingStatusType } from '../types';
import WebSocketService from '../services/websocket';
import ResultDisplay from './ResultDisplay';

interface ProcessingStatusProps {
  alertId: string;
  onComplete?: () => void;
}

const ProcessingStatus: React.FC<ProcessingStatusProps> = ({ alertId, onComplete }) => {
  const [status, setStatus] = useState<ProcessingStatusType | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  
  // Create WebSocket service only once per component lifecycle
  const wsServiceRef = useRef<WebSocketService | null>(null);
  
  if (!wsServiceRef.current) {
    wsServiceRef.current = new WebSocketService();
  }
  
  const wsService = wsServiceRef.current;

  // Store onComplete in a ref to avoid effect re-runs when it changes
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    const initializeWebSocket = async () => {
      try {
        // Skip if already connected to the same alert
        if (wsService.isConnected() && wsService.getCurrentAlertId() === alertId) {
          return;
        }

        // Set up event handlers
        wsService.onStatusUpdateHandler((statusUpdate) => {
          setStatus(statusUpdate);
          
          // Call onComplete callback when processing is done
          if (statusUpdate.status === 'completed' && onCompleteRef.current) {
            setTimeout(() => {
              if (onCompleteRef.current) onCompleteRef.current();
            }, 1000); // Small delay to show completion
          }
        });

        wsService.onErrorHandler((error) => {
          setWsError(error);
          setWsConnected(false);
        });

        wsService.onCloseHandler(() => {
          setWsConnected(false);
        });

        // Connect to WebSocket
        await wsService.connect(alertId);
        setWsConnected(true);
        setWsError(null); // Clear any previous errors
        
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error);
        setWsError('Failed to connect to real-time updates');
        setWsConnected(false);
      }
    };

    initializeWebSocket();

    // Only cleanup when component unmounts, not on effect re-runs
    return () => {
      // No cleanup here to prevent race conditions
    };
  }, [alertId]); // Removed onComplete from dependencies

  // Separate cleanup effect that only runs on unmount
  useEffect(() => {
    return () => {
      if (wsServiceRef.current) {
        wsServiceRef.current.disconnect();
        wsServiceRef.current = null;
      }
    };
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'queued':
        return 'info';
      case 'processing':
        return 'warning';
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

  // Simplified - no detailed steps, just processing or done

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
      <Card>
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
              <LinearProgress color={getStatusColor(status.status)} />
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
              Connection Status: {wsConnected ? '🟢 Connected' : '🔴 Disconnected'}
            </Typography>
          </Box>
        </CardContent>
      </Card>

      {status.result && status.status === 'completed' && (
        <Box mt={3}>
          <ResultDisplay result={status.result} />
        </Box>
      )}
    </Box>
  );
};

export default ProcessingStatus; 