import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Container, AppBar, Toolbar, Typography, Box, Tooltip, CircularProgress, IconButton } from '@mui/material';
import { FiberManualRecord, Refresh } from '@mui/icons-material';
import DashboardLayout from './DashboardLayout';
import FilterPanel from './FilterPanel';
import { apiClient, handleAPIError } from '../services/api';
import { webSocketService } from '../services/websocket';
import {
  saveFiltersToStorage,
  loadFiltersFromStorage,
  savePaginationToStorage,
  loadPaginationFromStorage,
  saveSortToStorage,
  loadSortFromStorage,
  saveAdvancedFiltersVisibility,
  loadAdvancedFiltersVisibility,
  getDefaultFilters,
  getDefaultPagination,
  getDefaultSort,
  mergeWithDefaults
} from '../utils/filterPersistence';
import type { Session, SessionUpdate, SessionFilter, PaginationState, SortState, FilterOptions } from '../types';

/**
 * DashboardView component for the Tarsy Dashboard - Phase 6
 * Contains the main dashboard logic with advanced filtering, pagination, sorting, and persistence
 */
function DashboardView() {
  const navigate = useNavigate();
  
  // Dashboard state
  const [activeAlerts, setActiveAlerts] = useState<Session[]>([]);
  const [historicalAlerts, setHistoricalAlerts] = useState<Session[]>([]);
  const [activeLoading, setActiveLoading] = useState<boolean>(true);
  const [historicalLoading, setHistoricalLoading] = useState<boolean>(true);
  const [activeError, setActiveError] = useState<string | null>(null);
  const [historicalError, setHistoricalError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);

  // Phase 6: Advanced filtering, sorting, and pagination state
  const [filters, setFilters] = useState<SessionFilter>(() => {
    const savedFilters = loadFiltersFromStorage();
    return mergeWithDefaults(savedFilters, getDefaultFilters());
  });
  const [filteredCount, setFilteredCount] = useState<number>(0);
  const [pagination, setPagination] = useState<PaginationState>(() => {
    const savedPagination = loadPaginationFromStorage();
    return mergeWithDefaults(savedPagination, getDefaultPagination());
  });
  const [sortState, setSortState] = useState<SortState>(() => {
    const savedSort = loadSortFromStorage();
    return mergeWithDefaults(savedSort, getDefaultSort());
  });
  const [filterOptions, setFilterOptions] = useState<FilterOptions | undefined>();
  const [showAdvancedFilters, setShowAdvancedFilters] = useState<boolean>(() => 
    loadAdvancedFiltersVisibility()
  );

  // Throttling state for API calls
  const refreshTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const REFRESH_THROTTLE_MS = 1000; // Wait 1 second between refreshes

  // Clean up throttling timeout on unmount
  useEffect(() => {
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, []);

  // Fetch active sessions
  const fetchActiveAlerts = async () => {
    try {
      setActiveLoading(true);
      setActiveError(null);
      const response = await apiClient.getActiveSessions();
      setActiveAlerts(response.active_sessions);
    } catch (err) {
      const errorMessage = handleAPIError(err);
      setActiveError(errorMessage);
      console.error('Failed to fetch active sessions:', err);
    } finally {
      setActiveLoading(false);
    }
  };

  // Fetch historical sessions with optional filtering (Phase 4)
  const fetchHistoricalAlerts = async (applyFilters: boolean = false) => {
    try {
      setHistoricalLoading(true);
      setHistoricalError(null);
      
      let response;
      if (applyFilters && (
        (filters.search && filters.search.trim()) ||
        (filters.status && filters.status.length > 0) ||
        (filters.agent_type && filters.agent_type.length > 0) ||
        (filters.alert_type && filters.alert_type.length > 0) ||
        filters.start_date ||
        filters.end_date ||
        filters.time_range_preset
      )) {
        // Use filtered API if filters are active
        console.log('🔍 Fetching filtered historical sessions:', filters, 'Page:', pagination.page, 'PageSize:', pagination.pageSize);
        const historicalFilters: SessionFilter = {
          ...filters,
          // For historical view, include completed and failed by default unless specific status filter is applied
          status: filters.status && filters.status.length > 0 
            ? filters.status 
            : ['completed', 'failed'] as ('completed' | 'failed' | 'in_progress' | 'pending')[]
        };
        response = await apiClient.getFilteredSessions(historicalFilters, pagination.page, pagination.pageSize);
      } else {
        // Use the original historical API (completed + failed sessions only)
        response = await apiClient.getHistoricalSessions(pagination.page, pagination.pageSize);
      }
      
      setHistoricalAlerts(response.sessions);
      setFilteredCount(response.pagination.total_items);
      
      // Update pagination with backend pagination info
      setPagination(prev => ({
        ...prev,
        totalItems: response.pagination.total_items,
        totalPages: response.pagination.total_pages,
        page: response.pagination.page
      }));
      
      console.log('📊 Historical alerts updated:', {
        totalSessions: response.sessions.length,
        filtersApplied: applyFilters,
        activeFilters: filters
      });
    } catch (err) {
      const errorMessage = handleAPIError(err);
      setHistoricalError(errorMessage);
      console.error('Failed to fetch historical sessions:', err);
    } finally {
      setHistoricalLoading(false);
    }
  };

  // Throttled refresh function to prevent excessive API calls
  const throttledRefresh = useCallback(() => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }
    
    refreshTimeoutRef.current = setTimeout(() => {
      console.log('🔄 Executing throttled dashboard refresh');
      fetchActiveAlerts();
      fetchHistoricalAlerts(true); // Use filtering on refresh
      refreshTimeoutRef.current = null;
    }, REFRESH_THROTTLE_MS);
  }, [filters]); // Add filters as dependency

  // Phase 6: Enhanced filter handlers with persistence
  const handleFiltersChange = (newFilters: SessionFilter) => {
    console.log('🔄 Filters changed:', newFilters);
    setFilters(newFilters);
    saveFiltersToStorage(newFilters);
    // Reset to first page when filters change
    setPagination(prev => ({ ...prev, page: 1 }));
    savePaginationToStorage({ page: 1 });
  };

  const handleClearFilters = () => {
    console.log('🧹 Clearing all filters');
    const clearedFilters = getDefaultFilters();
    setFilters(clearedFilters);
    saveFiltersToStorage(clearedFilters);
    // Reset pagination when clearing filters
    const defaultPagination = getDefaultPagination();
    setPagination(defaultPagination);
    savePaginationToStorage(defaultPagination);
  };

  // Phase 6: Pagination handlers
  const handlePageChange = (newPage: number) => {
    console.log('📄 Page changed:', newPage);
    setPagination(prev => ({ ...prev, page: newPage }));
    savePaginationToStorage({ page: newPage });
  };

  const handlePageSizeChange = (newPageSize: number) => {
    console.log('📄 Page size changed:', newPageSize);
    const newPage = Math.max(1, Math.ceil(((pagination.page - 1) * pagination.pageSize + 1) / newPageSize));
    const newTotalPages = Math.max(1, Math.ceil(pagination.totalItems / newPageSize));
    setPagination(prev => ({ 
      ...prev, 
      pageSize: newPageSize, 
      page: newPage,
      totalPages: newTotalPages
    }));
    savePaginationToStorage({ pageSize: newPageSize, page: newPage });
  };

  // Phase 6: Sort handlers
  const handleSortChange = (field: string) => {
    console.log('🔄 Sort changed:', field);
    const newDirection = sortState.field === field && sortState.direction === 'asc' ? 'desc' : 'asc';
    const newSortState = { field, direction: newDirection as 'asc' | 'desc' };
    setSortState(newSortState);
    saveSortToStorage(newSortState);
  };

  // Phase 6: Advanced filters visibility handler
  const handleToggleAdvancedFilters = (isVisible: boolean) => {
    console.log('🔧 Advanced filters visibility:', isVisible);
    setShowAdvancedFilters(isVisible);
    saveAdvancedFiltersVisibility(isVisible);
  };

  // Initial load and filter options
  useEffect(() => {
    fetchActiveAlerts();
    fetchHistoricalAlerts();
    
    // Phase 6: Load filter options from API
    const loadFilterOptions = async () => {
      try {
        const options = await apiClient.getFilterOptions();
        setFilterOptions(options);
        console.log('📋 Filter options loaded:', options);
      } catch (error) {
        console.warn('Failed to load filter options:', error);
        // Continue without filter options - components will use defaults
      }
    };
    
    loadFilterOptions();
  }, []);

  // Phase 6: Re-fetch when filters change (with debouncing)
  useEffect(() => {
    // Debounce filter changes to prevent excessive API calls
    const filterTimeout = setTimeout(() => {
      // Check if any filters are active
      const hasActiveFilters = Boolean(
        (filters.search && filters.search.trim()) ||
        (filters.status && filters.status.length > 0) ||
        (filters.agent_type && filters.agent_type.length > 0) ||
        (filters.alert_type && filters.alert_type.length > 0) ||
        filters.start_date ||
        filters.end_date ||
        filters.time_range_preset
      );

      if (hasActiveFilters) {
        console.log('🔍 Filters changed - refetching historical alerts:', filters);
        fetchHistoricalAlerts(true);
      } else {
        // When no filters are active, fetch without filtering
        console.log('🧹 No active filters - fetching unfiltered historical alerts');
        fetchHistoricalAlerts(false);
      }
    }, 300); // 300ms debounce for filter API calls

    return () => clearTimeout(filterTimeout);
  }, [filters]);

  // Phase 6: Re-fetch immediately when pagination or sorting changes
  useEffect(() => {
    console.log('📄 Pagination/sort changed - refetching historical alerts:', {
      page: pagination.page,
      pageSize: pagination.pageSize,
      sortState
    });
    
    // Check if any filters are active to determine which API to use
    const hasActiveFilters = Boolean(
      (filters.search && filters.search.trim()) ||
      (filters.status && filters.status.length > 0) ||
      (filters.agent_type && filters.agent_type.length > 0) ||
      (filters.alert_type && filters.alert_type.length > 0) ||
      filters.start_date ||
      filters.end_date ||
      filters.time_range_preset
    );

    fetchHistoricalAlerts(hasActiveFilters);
  }, [pagination.page, pagination.pageSize, sortState]);

  // Set up WebSocket event handlers for real-time updates
  useEffect(() => {
    const handleSessionUpdate = (update: SessionUpdate) => {
      console.log('DashboardView received session update:', update);
      // Update active alerts if the session is still active
      setActiveAlerts(prev => 
        prev.map(session => 
          session.session_id === update.session_id 
            ? { ...session, status: update.status, duration_ms: update.duration_ms || session.duration_ms }
            : session
        )
      );
    };

    const handleSessionCompleted = (update: SessionUpdate) => {
      console.log('DashboardView received session completed:', update);
      // Remove from active alerts and add to historical alerts
      setActiveAlerts(prev => prev.filter(session => session.session_id !== update.session_id));
      
      // Refresh historical alerts to include the newly completed session
      fetchHistoricalAlerts();
    };

    const handleSessionFailed = (update: SessionUpdate) => {
      console.log('DashboardView received session failed:', update);
      // Remove from active alerts and add to historical alerts
      setActiveAlerts(prev => prev.filter(session => session.session_id !== update.session_id));
      
      // Refresh historical alerts to include the newly failed session
      fetchHistoricalAlerts();
    };

    // WebSocket error handler
    const handleWebSocketError = (error: Event) => {
      console.warn('WebSocket connection error - real-time updates unavailable:', error);
      console.log('💡 Use manual refresh buttons if needed');
      setWsConnected(false); // Update connection status immediately
    };

    // WebSocket close handler  
    const handleWebSocketClose = (event: CloseEvent) => {
      console.warn('WebSocket connection closed - real-time updates unavailable:', {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean
      });
      console.log('💡 Use manual refresh buttons if needed');
      setWsConnected(false); // Update connection status immediately
    };

    // Dashboard update handler - handles real-time dashboard updates from backend
    const handleDashboardUpdate = (update: any) => {
      console.log('📊 Real-time dashboard update received:', update);
      
      // Handle different types of updates
      if (update.type === 'system_metrics' && update.active_sessions_list) {
        const newActiveCount = update.active_sessions_list.length;
        const currentActiveCount = activeAlerts.length;
        
        // Only refresh if the number of active sessions changed
        if (newActiveCount !== currentActiveCount) {
          console.log(`🔄 Active sessions changed: ${currentActiveCount} → ${newActiveCount}, refreshing data`);
          throttledRefresh();
        } else {
          console.log('📊 System metrics update - no session changes, skipping refresh');
        }
      } else if (update.type === 'session_status_change') {
        // Session status changes affect the main dashboard
        console.log('🔄 Session status change - refreshing dashboard data');
        throttledRefresh();
      } else if (update.type === 'llm_interaction' || update.type === 'mcp_communication') {
        // Session-specific updates don't require dashboard refresh - these are for detail views
        console.log('📊 Session-specific update - no dashboard refresh needed');
      } else if (update.type === 'batched_session_updates') {
        // Batched timeline updates are session-specific - no dashboard refresh needed
        console.log('📊 Batched session updates - no dashboard refresh needed');
      } else if (update.type === 'session_timeline_update') {
        // Individual timeline updates are session-specific - no dashboard refresh needed
        console.log('📊 Session timeline update - no dashboard refresh needed');
      } else if (update.session_id && (update.type === 'llm' || update.type === 'mcp' || update.type === 'system')) {
        // Timeline-specific updates with session_id - no dashboard refresh needed
        console.log('📊 Timeline interaction update - no dashboard refresh needed');
      } else if (update.session_started || update.session_ended) {
        // Session lifecycle events - refresh dashboard
        console.log('🔄 Session lifecycle event - refreshing dashboard data');
        throttledRefresh();
      } else if (!update.type && update.session_id) {
        // Generic session update without specific type - might be status or timeline
        // Check if it looks like a status change
        if (update.status || update.completed_at_us || update.error_message) {
          console.log('🔄 Detected session status update - refreshing dashboard data');
          throttledRefresh();
        } else {
          // Likely a timeline update - no dashboard refresh needed
          console.log('📊 Generic session update (likely timeline) - no dashboard refresh needed');
        }
      } else {
        // For genuinely unknown updates, log more details and refresh cautiously
        console.log('🔄 Unknown update type:', update.type, 'Keys:', Object.keys(update), '- refreshing dashboard data');
        throttledRefresh();
      }
    };

    // Connection change handler - updates UI immediately when WebSocket connection changes
    const handleConnectionChange = (connected: boolean) => {
      setWsConnected(connected);
      if (connected) {
        console.log('✅ WebSocket connected - real-time updates active');
        // Sync with backend state after reconnection (handles backend restarts)
        console.log('🔄 WebSocket reconnected - syncing dashboard with backend state');
        fetchActiveAlerts();
        fetchHistoricalAlerts(true); // Use filtering to maintain current view
      } else {
        console.log('❌ WebSocket disconnected - use manual refresh buttons');
      }
    };

    // Subscribe to WebSocket events
    const unsubscribeUpdate = webSocketService.onSessionUpdate(handleSessionUpdate);
    const unsubscribeCompleted = webSocketService.onSessionCompleted(handleSessionCompleted);
    const unsubscribeFailed = webSocketService.onSessionFailed(handleSessionFailed);
    const unsubscribeDashboard = webSocketService.onDashboardUpdate(handleDashboardUpdate);
    const unsubscribeConnection = webSocketService.onConnectionChange(handleConnectionChange);
    const unsubscribeError = webSocketService.onError(handleWebSocketError);
    const unsubscribeClose = webSocketService.onClose(handleWebSocketClose);

    // Connect to WebSocket with enhanced logging
    console.log('🔌 Connecting to WebSocket for real-time updates...');
    webSocketService.connect();

    // Set initial connection status
    setWsConnected(webSocketService.isConnected);

    // Cleanup
    return () => {
      console.log('DashboardView cleaning up WebSocket subscriptions');
      unsubscribeUpdate();
      unsubscribeCompleted();
      unsubscribeFailed();
      unsubscribeDashboard();
      unsubscribeConnection();
      unsubscribeError();
      unsubscribeClose();
    };
  }, []);

  // Handle session click with same-tab navigation
  const handleSessionClick = (sessionId: string) => {
    console.log('Navigating to session detail:', sessionId);
    navigate(`/sessions/${sessionId}`);
  };

  // Handle refresh actions
  const handleRefreshActive = () => {
    fetchActiveAlerts();
  };

  const handleRefreshHistorical = () => {
    fetchHistoricalAlerts();
  };

  // Handle WebSocket retry
  const handleWebSocketRetry = () => {
    console.log('🔄 Manual WebSocket retry requested');
    webSocketService.retry();
  };

  return (
    <Container maxWidth={false} sx={{ px: 2 }}>
      {/* AppBar with dashboard title and live indicator */}
      <AppBar position="static" elevation={0} sx={{ borderRadius: 1 }}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Tarsy Dashboard
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {/* Connection Status Indicator */}
            <Tooltip 
              title={wsConnected 
                ? "Connected - Real-time updates active" 
                : "Disconnected - Use manual refresh buttons or retry connection"
              }
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <FiberManualRecord 
                  sx={{ 
                    fontSize: 12, 
                    color: wsConnected ? 'success.main' : 'error.main',
                    animation: wsConnected ? 'none' : 'pulse 2s infinite',
                    '@keyframes pulse': {
                      '0%': { opacity: 0.5 },
                      '50%': { opacity: 1 },
                      '100%': { opacity: 0.5 },
                    }
                  }} 
                />
                <Typography variant="body2" sx={{ color: 'inherit' }}>
                  {wsConnected ? 'Live' : 'Manual'}
                </Typography>
              </Box>
            </Tooltip>

            {/* WebSocket Retry Button - only show when disconnected */}
            {!wsConnected && (
              <Tooltip title="Retry WebSocket connection">
                <IconButton
                  size="small"
                  onClick={handleWebSocketRetry}
                  sx={{ 
                    color: 'inherit',
                    '&:hover': {
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    }
                  }}
                >
                  <Refresh fontSize="small" />
                </IconButton>
              </Tooltip>
            )}

            {/* Loading indicator for active refreshes */}
            {(activeLoading || historicalLoading) && (
              <Tooltip title="Loading data...">
                <CircularProgress size={20} sx={{ color: 'inherit' }} />
              </Tooltip>
            )}
          </Box>
        </Toolbar>
      </AppBar>

      {/* Phase 6: Advanced Filter Panel */}
      <FilterPanel
        filters={filters}
        onFiltersChange={handleFiltersChange}
        onClearFilters={handleClearFilters}
        filterOptions={filterOptions}
        loading={historicalLoading}
        showAdvanced={showAdvancedFilters}
        onToggleAdvanced={handleToggleAdvancedFilters}
      />

      {/* Main content area with two-section layout */}
      <Box sx={{ mt: 2 }}>
        <DashboardLayout
          activeAlerts={activeAlerts}
          historicalAlerts={historicalAlerts}
          activeLoading={activeLoading}
          historicalLoading={historicalLoading}
          activeError={activeError}
          historicalError={historicalError}
          onRefreshActive={handleRefreshActive}
          onRefreshHistorical={handleRefreshHistorical}
          onSessionClick={handleSessionClick}
          filters={filters}
          filteredCount={filteredCount}
          // Phase 6: Additional props for enhanced functionality
          sortState={sortState}
          onSortChange={handleSortChange}
          pagination={pagination}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      </Box>
    </Container>
  );
}

export default DashboardView; 