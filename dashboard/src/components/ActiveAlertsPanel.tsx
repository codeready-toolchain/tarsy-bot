import React, { useState, useEffect } from 'react';
import {
  Paper,
  Typography,
  Box,
  Button,
  CircularProgress,
  Alert,
  Stack,
  Chip,
} from '@mui/material';
import { Refresh, WifiOff, Wifi } from '@mui/icons-material';
import ActiveAlertCard from './ActiveAlertCard';
import ChainProgressCard from './ChainProgressCard';
import { webSocketService } from '../services/websocket';
import type { ActiveAlertsPanelProps, SessionUpdate, ChainProgressUpdate, StageProgressUpdate } from '../types';

/**
 * ActiveAlertsPanel component displays currently active/processing alerts
 * with real-time updates via WebSocket connection
 */
const ActiveAlertsPanel: React.FC<ActiveAlertsPanelProps> = ({
  sessions = [],
  loading = false,
  error = null,
  onRefresh,
  onSessionClick,
}) => {
  const [progressData, setProgressData] = useState<Record<string, number>>({});
  const [chainProgressData, setChainProgressData] = useState<Record<string, ChainProgressUpdate>>({});
  const [stageProgressData, setStageProgressData] = useState<Record<string, StageProgressUpdate[]>>({});
  const [wsConnected, setWsConnected] = useState(false);

  // Set up WebSocket event handlers
  useEffect(() => {
    // Session update handlers
    const handleSessionUpdate = (update: SessionUpdate) => {
      console.log('Active session update:', update);
      
      // Update progress data for in_progress sessions
      if (update.progress !== undefined) {
        setProgressData(prev => ({
          ...prev,
          [update.session_id]: update.progress!
        }));
      }
    };

    const handleSessionCompleted = (update: SessionUpdate) => {
      console.log('Session completed:', update);
      // Remove from progress tracking when completed
      setProgressData(prev => {
        const newProgress = { ...prev };
        delete newProgress[update.session_id];
        return newProgress;
      });
    };

    const handleSessionFailed = (update: SessionUpdate) => {
      console.log('Session failed:', update);
      // Remove from progress tracking when failed
      setProgressData(prev => {
        const newProgress = { ...prev };
        delete newProgress[update.session_id];
        return newProgress;
      });
      // Also clean up chain progress data
      setChainProgressData(prev => {
        const newData = { ...prev };
        delete newData[update.session_id];
        return newData;
      });
      setStageProgressData(prev => {
        const newData = { ...prev };
        delete newData[update.session_id];
        return newData;
      });
    };

    // Chain progress handlers
    const handleChainProgress = (update: ChainProgressUpdate) => {
      console.log('Chain progress update:', update);
      setChainProgressData(prev => ({
        ...prev,
        [update.session_id]: update
      }));
    };

    const handleStageProgress = (update: StageProgressUpdate) => {
      console.log('Stage progress update:', update);
      setStageProgressData(prev => {
        const current = prev[update.session_id] || [];
        const existingIndex = current.findIndex(s => s.stage_execution_id === update.stage_execution_id);
        
        let updated;
        if (existingIndex >= 0) {
          // Update existing stage
          updated = [...current];
          updated[existingIndex] = update;
        } else {
          // Add new stage
          updated = [...current, update];
        }
        
        return {
          ...prev,
          [update.session_id]: updated.sort((a, b) => a.stage_index - b.stage_index)
        };
      });
    };

    // Subscribe to WebSocket events
    const unsubscribeUpdate = webSocketService.onSessionUpdate(handleSessionUpdate);
    const unsubscribeCompleted = webSocketService.onSessionCompleted(handleSessionCompleted);
    const unsubscribeFailed = webSocketService.onSessionFailed(handleSessionFailed);
    
    // Subscribe to chain progress events (with fallback for services that don't support them yet)
    const unsubscribeChainProgress = webSocketService.onChainProgress ? 
      webSocketService.onChainProgress(handleChainProgress) : () => {};
    const unsubscribeStageProgress = webSocketService.onStageProgress ? 
      webSocketService.onStageProgress(handleStageProgress) : () => {};

    // Connect to WebSocket
    (async () => {
      try {
        await webSocketService.connect();
        setWsConnected(webSocketService.isConnected);
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error);
      }
    })();

    // Check connection status periodically
    const connectionCheck = setInterval(() => {
      setWsConnected(webSocketService.isConnected);
    }, 1000);

    // Cleanup
    return () => {
      unsubscribeUpdate();
      unsubscribeCompleted();
      unsubscribeFailed();
      unsubscribeChainProgress();
      unsubscribeStageProgress();
      clearInterval(connectionCheck);
    };
  }, []);

  // Handle session card click
  const handleSessionClick = (sessionId: string) => {
    console.log('Active session clicked:', sessionId);
    if (onSessionClick) {
      onSessionClick(sessionId);
    }
  };

  // Handle manual refresh
  const handleRefresh = () => {
    if (onRefresh) {
      onRefresh();
    }
  };

  return (
    <Paper sx={{ p: 3, mb: 3 }}>
      {/* Panel Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            Active Alerts
          </Typography>
          
          {/* Active count badge */}
          {sessions.length > 0 && (
            <Chip
              label={sessions.length}
              color="primary"
              size="small"
              sx={{ fontWeight: 600 }}
            />
          )}

          {/* WebSocket connection indicator */}
          <Chip
            icon={wsConnected ? <Wifi sx={{ fontSize: 16 }} /> : <WifiOff sx={{ fontSize: 16 }} />}
            label={wsConnected ? 'Live' : 'Offline'}
            color={wsConnected ? 'success' : 'default'}
            size="small"
            variant={wsConnected ? 'filled' : 'outlined'}
          />
        </Box>

        {/* Refresh Button */}
        <Button
          variant="outlined"
          size="small"
          startIcon={loading ? <CircularProgress size={16} /> : <Refresh />}
          onClick={handleRefresh}
          disabled={loading}
        >
          {loading ? 'Loading...' : 'Refresh'}
        </Button>
      </Box>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Loading State */}
      {loading && sessions.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {/* Active Alerts List */}
          {sessions.length === 0 ? (
            <Box sx={{ py: 6, textAlign: 'center' }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No Active Alerts
              </Typography>
              <Typography variant="body2" color="text.secondary">
                All alerts are currently completed or there are no alerts in the system.
              </Typography>
            </Box>
          ) : (
            <Stack spacing={2}>
              {sessions.map((session) => {
                // Use ChainProgressCard for chain sessions, ActiveAlertCard for regular sessions
                const isChainSession = session.chain_id !== undefined;
                
                if (isChainSession) {
                  return (
                    <ChainProgressCard
                      key={session.session_id}
                      session={session}
                      chainProgress={chainProgressData[session.session_id]}
                      stageProgress={stageProgressData[session.session_id]}
                      onClick={handleSessionClick}
                      compact={false}
                    />
                  );
                } else {
                  return (
                    <ActiveAlertCard
                      key={session.session_id}
                      session={session}
                      progress={progressData[session.session_id]}
                      onClick={handleSessionClick}
                    />
                  );
                }
              })}
            </Stack>
          )}

          {/* Summary */}
          {sessions.length > 0 && (
            <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
              <Typography variant="body2" color="text.secondary">
                Showing {sessions.length} active alert{sessions.length !== 1 ? 's' : ''}
                {wsConnected && ' • Live updates enabled'}
              </Typography>
            </Box>
          )}
        </>
      )}
    </Paper>
  );
};

export default ActiveAlertsPanel; 