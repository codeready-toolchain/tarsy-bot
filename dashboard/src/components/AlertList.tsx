import React, { useState, useEffect } from 'react';
import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  CircularProgress,
  Alert,
  Box,
  Button,
} from '@mui/material';
import { Refresh } from '@mui/icons-material';
import AlertListItem from './AlertListItem';
import { apiClient, handleAPIError } from '../services/api';
import type { Session } from '../types';

/**
 * AlertList component displays a table of all alert sessions
 * Handles loading states, errors, and data fetching from the API
 */
const AlertList: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [totalItems, setTotalItems] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch sessions from API
  const fetchSessions = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.getSessions();
      setSessions(response.sessions);
      setTotalItems(response.pagination.total_items);
    } catch (err) {
      const errorMessage = handleAPIError(err);
      setError(errorMessage);
      console.error('Failed to fetch sessions:', err);
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchSessions();
  }, []);

  // Handle session row click (Phase 1 - no navigation yet)
  const handleSessionClick = (sessionId: string) => {
    if (!sessionId) {
      console.warn('Session clicked but no ID provided');
      return;
    }
    console.log('Session clicked:', sessionId);
    // Navigation will be implemented in Phase 3
  };

  // Handle manual refresh
  const handleRefresh = () => {
    fetchSessions();
  };

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" gutterBottom>
          Alert History (All alerts - newest first)
        </Typography>
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

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading && !sessions.length ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Status</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Agent Chain</TableCell>
                  <TableCell>Time</TableCell>
                  <TableCell>Duration</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sessions.length === 0 ? (
                  <TableRow key="empty-state">
                    <TableCell colSpan={5} align="center">
                      <Typography color="text.secondary" sx={{ py: 4 }}>
                        No alerts found
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  sessions.map((session) => (
                    <AlertListItem
                      key={session.session_id || `session-${Math.random()}`}
                      session={session}
                      onClick={handleSessionClick}
                    />
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>

          {sessions.length > 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Showing all {sessions.length} alerts (Total: {totalItems})
            </Typography>
          )}
        </>
      )}
    </Paper>
  );
};

export default AlertList; 