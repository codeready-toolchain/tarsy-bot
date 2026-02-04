import React from 'react';
import { Box } from '@mui/material';
import ActiveAlertsPanel from './ActiveAlertsPanel';
import HistoricalAlertsList from './HistoricalAlertsList';
import type { DashboardLayoutProps } from '../types';

/**
 * DashboardLayout component provides the main two-section layout
 * for Phase 6: Active alerts at the top, historical alerts below with advanced features
 */
const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  activeAlerts,
  historicalAlerts,
  activeLoading = false,
  historicalLoading = false,
  activeError = null,
  historicalError = null,
  onRefreshActive,
  onRefreshHistorical,
  onSessionClick,
  onScoreClick,
  // Phase 4: Filter props
  filters,
  filteredCount,
  // Phase 6: Sorting and pagination props
  sortState,
  onSortChange,
  pagination,
  onPageChange,
  onPageSizeChange,
}) => {
  return (
    <Box sx={{ width: '100%' }}>
      {/* Active Alerts Section - Top Priority */}
      <ActiveAlertsPanel
        sessions={activeAlerts}
        loading={activeLoading}
        error={activeError}
        onRefresh={onRefreshActive}
        onSessionClick={onSessionClick}
      />

      {/* Historical Alerts Section - Below Active */}
      <HistoricalAlertsList
        sessions={historicalAlerts}
        loading={historicalLoading}
        error={historicalError}
        onRefresh={onRefreshHistorical}
        onSessionClick={onSessionClick}
        onScoreClick={onScoreClick}
        filters={filters}
        filteredCount={filteredCount}
        // Phase 6: Enhanced functionality props
        sortState={sortState}
        onSortChange={onSortChange}
        pagination={pagination}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />
    </Box>
  );
};

export default DashboardLayout; 