import React from 'react';
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
  TableSortLabel,
} from '@mui/material';
import { Refresh, SearchOff } from '@mui/icons-material';
import AlertListItem from './AlertListItem';
import PaginationControls from './PaginationControls';
import { hasActiveFilters } from '../utils/search';
import type { EnhancedHistoricalAlertsListProps } from '../types';

/**
 * HistoricalAlertsList component displays completed and failed alerts
 * in a table format, enhanced for Phase 6 with advanced filtering, sorting, and pagination
 */
const HistoricalAlertsList: React.FC<EnhancedHistoricalAlertsListProps> = ({
  sessions = [],
  loading = false,
  error = null,
  onRefresh,
  onSessionClick,
  // Phase 4: Filter props
  filters,
  filteredCount,
  searchTerm,
  // Phase 6: Sorting and pagination props
  sortState,
  onSortChange,
  pagination,
  onPageChange,
  onPageSizeChange,
}) => {
  // Handle session row click
  const handleSessionClick = (sessionId: string) => {
    if (!sessionId) {
      console.warn('Historical session clicked but no ID provided');
      return;
    }
    console.log('Historical session clicked:', sessionId);
    
    if (onSessionClick) {
      onSessionClick(sessionId);
    }
    // Phase 3 will implement navigation to detail view
  };

  // Handle manual refresh
  const handleRefresh = () => {
    if (onRefresh) {
      onRefresh();
    }
  };

  // Phase 6: Handle sort column click
  const handleSortClick = (field: string) => {
    if (onSortChange) {
      onSortChange(field);
    }
  };

  // Phase 6: Sortable columns configuration
  const sortableColumns = [
    { field: 'status', label: 'Status' },
    { field: 'alert_type', label: 'Type' },
    { field: 'agent_type', label: 'Agent Chain' },
    { field: 'started_at_us', label: 'Time' },
    { field: 'duration_ms', label: 'Duration' },
    { field: 'session_total_tokens', label: 'Tokens' }, // EP-0009: Add token column
  ];

  return (
    <Paper sx={{ p: 3 }}>
      {/* Panel Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          Alert History
          {/* Phase 4: Show filtered count */}
          {filteredCount !== undefined && (
            <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
              ({filteredCount.toLocaleString()} result{filteredCount !== 1 ? 's' : ''})
            </Typography>
          )}
        </Typography>
        
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
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => {}}>
          {error}
        </Alert>
      )}

      {/* Phase 4: Filter info message */}
      {filters && filters.search && filters.search.trim() && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Showing results for "{filters.search}"
          {filters.status && filters.status.length > 0 && (
            <> with status: {filters.status.join(', ')}</>
          )}
        </Alert>
      )}

      {/* Loading State */}
      {loading && sessions.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {/* Historical Alerts Table */}
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  {sortableColumns.map((column) => (
                    <TableCell key={column.field} sx={{ fontWeight: 600 }}>
                      {onSortChange ? (
                        <TableSortLabel
                          active={sortState?.field === column.field}
                          direction={sortState?.field === column.field ? sortState.direction : 'asc'}
                          onClick={() => handleSortClick(column.field)}
                        >
                          {column.label}
                        </TableSortLabel>
                      ) : (
                        column.label
                      )}
                    </TableCell>
                  ))}
                  <TableCell sx={{ fontWeight: 600, width: 60, textAlign: 'center' }}></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sessions.length === 0 ? (
                  <TableRow key="empty-state">
                    <TableCell colSpan={7} align="center">
                      <Box sx={{ py: 6, textAlign: 'center' }}>
                        {/* Phase 4: Different empty states for filtered vs unfiltered */}
                        {filters && hasActiveFilters(filters) ? (
                          <>
                            <SearchOff sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                            <Typography variant="h6" color="text.secondary" gutterBottom>
                              No alerts found
                            </Typography>
                            <Typography variant="body2" color="text.disabled">
                              Try adjusting your search terms or filters
                            </Typography>
                          </>
                        ) : (
                          <>
                            <Typography variant="h6" color="text.secondary" gutterBottom>
                              No Historical Alerts
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              No completed or failed alerts found.
                            </Typography>
                          </>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                ) : (
                  // Backend handles pagination, so display all returned sessions
                  sessions.map((session) => (
                    <AlertListItem
                      key={session.session_id || `session-${Math.random()}`}
                      session={session}
                      onClick={handleSessionClick}
                      searchTerm={searchTerm || filters?.search}
                    />
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Phase 6: Pagination Controls */}
          {pagination && onPageChange && onPageSizeChange && (
            <PaginationControls
              pagination={pagination}
              onPageChange={onPageChange}
              onPageSizeChange={onPageSizeChange}
              disabled={loading}
            />
          )}

          {/* Summary */}
          {sessions.length > 0 && !pagination && (
            <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
              <Typography variant="body2" color="text.secondary">
                Showing {sessions.length} historical alert{sessions.length !== 1 ? 's' : ''} (completed/failed)
              </Typography>
            </Box>
          )}
        </>
      )}
    </Paper>
  );
};

export default HistoricalAlertsList; 