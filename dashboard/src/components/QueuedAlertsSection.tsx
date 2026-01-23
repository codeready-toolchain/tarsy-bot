import React, { useState, useRef, useEffect } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Box,
  Typography,
  IconButton,
  Button,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  CircularProgress,
  Tooltip,
  List,
  ListItem,
  ListItemText,
  alpha,
} from '@mui/material';
import {
  ExpandMore,
  Schedule,
  CancelOutlined,
  OpenInNew,
} from '@mui/icons-material';
import { apiClient, handleAPIError } from '../services/api';
import { formatDurationMs } from '../utils/timestamp';
import type { Session } from '../types';

interface QueuedAlertsSectionProps {
  sessions: Session[];
  onSessionClick?: (sessionId: string) => void;
  onRefresh?: () => void;
}

// Wait time refresh interval in milliseconds (10 seconds)
const WAIT_TIME_REFRESH_INTERVAL_MS = 10000;

// Delay after cancel before refreshing session list (500ms)
// This gives the backend time to process the cancellation
const POST_CANCEL_REFRESH_DELAY_MS = 500;

/**
 * QueuedAlertsSection component displays queued (PENDING) sessions
 * in a collapsible accordion format
 */
const QueuedAlertsSection: React.FC<QueuedAlertsSectionProps> = ({
  sessions,
  onSessionClick,
  onRefresh,
}) => {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [sessionToCancel, setSessionToCancel] = useState<string | null>(null);
  const [isCanceling, setIsCanceling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [, forceUpdate] = useState(0);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  // Refresh wait times periodically to keep them accurate
  useEffect(() => {
    if (sessions.length === 0) return;

    const interval = setInterval(() => {
      forceUpdate((n) => n + 1);
    }, WAIT_TIME_REFRESH_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [sessions.length]);

  // Handle cancel button click
  const handleCancelClick = (sessionId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent accordion toggle
    setSessionToCancel(sessionId);
    setCancelDialogOpen(true);
    setCancelError(null);
  };

  // Handle dialog close
  const handleDialogClose = () => {
    if (!isCanceling) {
      setCancelDialogOpen(false);
      setSessionToCancel(null);
      setCancelError(null);
    }
  };

  // Handle cancel confirmation
  const handleConfirmCancel = async () => {
    if (!sessionToCancel) return;

    setIsCanceling(true);
    setCancelError(null);

    try {
      await apiClient.cancelSession(sessionToCancel);
      setCancelDialogOpen(false);
      setSessionToCancel(null);
      setIsCanceling(false);
      
      // Trigger refresh after brief delay to allow backend to process
      if (onRefresh) {
        timeoutRef.current = setTimeout(onRefresh, POST_CANCEL_REFRESH_DELAY_MS);
      }
    } catch (error) {
      const errorMessage = handleAPIError(error);
      setCancelError(errorMessage);
      setIsCanceling(false);
    }
  };

  // Handle view details button click
  const handleViewClick = (sessionId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent accordion toggle
    if (onSessionClick) {
      onSessionClick(sessionId);
    }
  };

  // Calculate wait time for a session
  const calculateWaitTime = (startedAtUs: number): string => {
    const now = Date.now() * 1000; // Convert to microseconds
    const durationUs = now - startedAtUs;
    const durationMs = durationUs / 1000;
    return formatDurationMs(durationMs);
  };

  return (
    <>
      <Accordion
        defaultExpanded={false}
        sx={{
          backgroundColor: (theme) => alpha(theme.palette.warning.main, 0.05),
          border: '1px solid',
          borderColor: (theme) => alpha(theme.palette.warning.main, 0.2),
          '&:before': {
            display: 'none',
          },
          boxShadow: 1,
        }}
      >
        <AccordionSummary
          expandIcon={<ExpandMore />}
          sx={{
            '&:hover': {
              backgroundColor: (theme) => alpha(theme.palette.warning.main, 0.08),
            },
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%', pr: 2 }}>
            <Schedule sx={{ color: 'warning.main', fontSize: 20 }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Queued Alerts
            </Typography>
            <Chip
              label={sessions.length}
              color="warning"
              size="small"
              sx={{ fontWeight: 600 }}
            />
            <Typography variant="body2" color="text.secondary">
              • Expected to start soon
            </Typography>
          </Box>
        </AccordionSummary>

        <AccordionDetails sx={{ pt: 0 }}>
          <List sx={{ width: '100%', p: 0 }}>
            {sessions.map((session, index) => (
              <ListItem
                key={session.session_id}
                sx={{
                  borderTop: index === 0 ? 'none' : '1px solid',
                  borderColor: 'divider',
                  py: 2,
                  px: 2,
                  '&:hover': {
                    backgroundColor: 'action.hover',
                  },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', width: '100%', gap: 2 }}>
                  {/* Position number */}
                  <Box
                    sx={{
                      minWidth: 32,
                      height: 32,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: 'warning.main',
                      color: 'white',
                      borderRadius: '50%',
                      fontWeight: 700,
                      fontSize: '0.875rem',
                    }}
                  >
                    {index + 1}
                  </Box>

                  {/* Alert info */}
                  <ListItemText
                    primary={
                      <Typography variant="body1" sx={{ fontWeight: 600 }}>
                        {session.alert_type || 'Unknown Alert'}
                      </Typography>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                        <Typography variant="caption" color="text.secondary">
                          Waiting: {calculateWaitTime(session.started_at_us)}
                        </Typography>
                        {session.agent_type && (
                          <>
                            <Typography variant="caption" color="text.secondary">
                              •
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {session.agent_type}
                            </Typography>
                          </>
                        )}
                        {session.author && (
                          <>
                            <Typography variant="caption" color="text.secondary">
                              •
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              by {session.author}
                            </Typography>
                          </>
                        )}
                      </Box>
                    }
                  />

                  {/* Action buttons */}
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Tooltip title="View session details">
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<OpenInNew fontSize="small" />}
                        onClick={(e) => handleViewClick(session.session_id, e)}
                        sx={{
                          textTransform: 'none',
                          minWidth: 100,
                        }}
                      >
                        View
                      </Button>
                    </Tooltip>

                    <Tooltip title="Cancel this queued session">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={(e) => handleCancelClick(session.session_id, e)}
                        sx={{
                          '&:hover': {
                            backgroundColor: (theme) => alpha(theme.palette.error.main, 0.1),
                          },
                        }}
                      >
                        <CancelOutlined fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </ListItem>
            ))}
          </List>

          {/* No sessions message (shouldn't happen but defensive) */}
          {sessions.length === 0 && (
            <Box sx={{ py: 3, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                No queued sessions
              </Typography>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      {/* Cancel Confirmation Dialog */}
      <Dialog
        open={cancelDialogOpen}
        onClose={handleDialogClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Cancel Queued Session?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to cancel this queued session? It will be removed from the queue
            and will not be processed.
          </DialogContentText>
          {cancelError && (
            <Box
              sx={{
                mt: 2,
                p: 1.5,
                bgcolor: (theme) => alpha(theme.palette.error.main, 0.05),
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'error.main',
              }}
            >
              <Typography variant="body2" color="error.main">
                {cancelError}
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleDialogClose} disabled={isCanceling} color="inherit">
            Keep in Queue
          </Button>
          <Button
            onClick={handleConfirmCancel}
            variant="contained"
            color="error"
            disabled={isCanceling}
            startIcon={isCanceling ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            {isCanceling ? 'Canceling...' : 'Yes, Cancel Session'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default QueuedAlertsSection;
