import React, { useState, useEffect } from 'react';
import {
  Paper,
  Button,
  Box,
  Typography,
  Chip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  InputAdornment,
  Switch,
  FormControlLabel,
  Collapse,
  Divider
} from '@mui/material';
import {
  Search,
  Clear,
  FilterList,
  TuneOutlined
} from '@mui/icons-material';
import { format, parseISO } from 'date-fns';
import TimeRangeModal from './TimeRangeModal';
import type { FilterPanelProps } from '../types';

/**
 * FilterPanel component for Phase 6 - Advanced Filtering & Pagination
 * Comprehensive filtering interface with multiple criteria and collapsible advanced options
 */
const FilterPanel: React.FC<FilterPanelProps> = ({
  filters,
  onFiltersChange,
  onClearFilters,
  filterOptions,
  showAdvanced = false,
  onToggleAdvanced
}) => {
  // Local state for advanced filters toggle
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(showAdvanced || false);
  const [timeRangeModalOpen, setTimeRangeModalOpen] = useState(false);

  // Phase 6: Load default values from localStorage if no filters provided
  useEffect(() => {
    setShowAdvancedFilters(showAdvanced || false);
  }, [showAdvanced]);

  // Calculate if any filters are active
      const hasActiveFilters = Boolean(
      (filters.search && filters.search.trim()) ||
      (filters.status && filters.status.length > 0) ||
      (filters.agent_type && filters.agent_type.length > 0) ||
      (filters.alert_type && filters.alert_type.length > 0) ||
      filters.start_date ||
      filters.end_date ||
      filters.time_range_preset
    );

  const activeFiltersCount = [
    filters.search && filters.search.trim() ? 1 : 0,
    filters.status && filters.status.length > 0 ? filters.status.length : 0,
    filters.agent_type && filters.agent_type.length > 0 ? filters.agent_type.length : 0,
    filters.alert_type && filters.alert_type.length > 0 ? filters.alert_type.length : 0,
    (filters.start_date || filters.end_date || filters.time_range_preset) ? 1 : 0
  ].reduce((sum, count) => sum + count, 0);

  // Filter options with defaults
  // Always show all possible status options, regardless of what's in the database
  const allStatusOptions = ['completed', 'failed', 'cancelled', 'in_progress', 'pending', 'canceling'];
  
  const defaultFilterOptions = {
    agent_types: filterOptions?.agent_types || ['kubernetes', 'network', 'database'],
    alert_types: filterOptions?.alert_types || ['NamespaceTerminating', 'PodCrashLooping', 'NodeNotReady'],
    status_options: allStatusOptions
  };

  // Handler functions
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onFiltersChange({
      ...filters,
      search: event.target.value
    });
  };

  const handleStatusChange = (statuses: string[]) => {
    onFiltersChange({
      ...filters,
      status: statuses as ('completed' | 'failed' | 'cancelled' | 'in_progress' | 'pending' | 'canceling')[]
    });
  };

  const handleAgentTypeChange = (agentTypes: string[]) => {
    onFiltersChange({
      ...filters,
      agent_type: agentTypes
    });
  };

  const handleAlertTypeChange = (alertTypes: string[]) => {
    onFiltersChange({
      ...filters,
      alert_type: alertTypes
    });
  };

  const handleToggleAdvanced = () => {
    const newShowAdvanced = !showAdvancedFilters;
    setShowAdvancedFilters(newShowAdvanced);
    onToggleAdvanced?.(newShowAdvanced);
  };

  // Helper functions for chip display and colors
  const getStatusDisplayName = (status: string): string => {
    switch (status) {
      case 'completed': return 'Completed';
      case 'failed': return 'Failed';
      case 'in_progress': return 'In Progress';
      case 'pending': return 'Pending';
      default: return status;
    }
  };

  const getStatusColor = (status: string): 'success' | 'error' | 'info' | 'warning' | 'default' => {
    switch (status) {
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'in_progress': return 'info';
      case 'pending': return 'warning';
      default: return 'default';
    }
  };

  // Clear handlers for individual filter chips
  const handleClearSearch = () => {
    onFiltersChange({ ...filters, search: '' });
  };

  const handleClearStatus = (statusToRemove: string) => {
    const newStatuses = filters.status?.filter(status => status !== statusToRemove) || [];
    onFiltersChange({ ...filters, status: newStatuses });
  };

  const handleClearAgentType = (agentTypeToRemove: string) => {
    const newAgentTypes = filters.agent_type?.filter(type => type !== agentTypeToRemove) || [];
    onFiltersChange({ ...filters, agent_type: newAgentTypes });
  };

  const handleClearAlertType = (alertTypeToRemove: string) => {
    const newAlertTypes = filters.alert_type?.filter(type => type !== alertTypeToRemove) || [];
    onFiltersChange({ ...filters, alert_type: newAlertTypes });
  };

  const handleTimeRangeApply = (startDate: Date | null, endDate: Date | null, preset?: string) => {
    onFiltersChange({
      ...filters,
      start_date: startDate ? startDate.toISOString() : null,
      end_date: endDate ? endDate.toISOString() : null,
      time_range_preset: preset || null
    });
    setTimeRangeModalOpen(false);
  };

  const handleClearDateRange = () => {
    onFiltersChange({ ...filters, start_date: null, end_date: null, time_range_preset: null });
  };

  return (
    <>
      <Paper sx={{ mt: 2, p: 2 }}>
        {/* Filter Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <FilterList />
            Filters
            {activeFiltersCount > 0 && (
              <Chip 
                label={activeFiltersCount} 
                size="small" 
                color="primary" 
                variant="filled"
              />
            )}
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={showAdvancedFilters}
                onChange={handleToggleAdvanced}
                color="primary"
              />
            }
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <TuneOutlined fontSize="small" />
                <Typography variant="body2">Advanced</Typography>
              </Box>
            }
          />
        </Box>

        {/* Basic Filters */}
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Search */}
          <Box sx={{ flex: '2 1 300px', minWidth: 200 }}>
            <TextField
              fullWidth
              placeholder="Search alerts by type, error message..."
              variant="outlined"
              size="small"
              value={filters.search || ''}
              onChange={handleSearchChange}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search fontSize="small" />
                  </InputAdornment>
                ),
                endAdornment: filters.search && (
                  <InputAdornment position="end">
                    <Button
                      size="small"
                      onClick={handleClearSearch}
                      sx={{ minWidth: 'auto', p: 0.5 }}
                    >
                      <Clear fontSize="small" />
                    </Button>
                  </InputAdornment>
                )
              }}
            />
          </Box>

          {/* Status Filter */}
          <Box sx={{ flex: '1 1 200px', minWidth: 150 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Status</InputLabel>
              <Select
                multiple
                value={filters.status || []}
                onChange={(e) => handleStatusChange(e.target.value as string[])}
                label="Status"
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip 
                        key={value} 
                        label={getStatusDisplayName(value)} 
                        size="small" 
                        color={getStatusColor(value)}
                      />
                    ))}
                  </Box>
                )}
              >
                {defaultFilterOptions.status_options.map((status) => (
                  <MenuItem key={status} value={status}>
                    {getStatusDisplayName(status)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          {/* Time Range Button */}
          <Button
            variant="outlined"
            onClick={() => setTimeRangeModalOpen(true)}
            startIcon={<Search />}
            sx={{ height: 40 }}
          >
            {filters.time_range_preset ? (
              `Range: ${filters.time_range_preset}`
            ) : filters.start_date || filters.end_date ? (
              `Custom Range`
            ) : (
              'Time Range'
            )}
          </Button>

          {/* Clear All Button */}
          {hasActiveFilters && (
            <Button
              variant="text"
              color="secondary"
              onClick={onClearFilters}
              startIcon={<Clear />}
              sx={{ height: 40 }}
            >
              Clear All
            </Button>
          )}
        </Box>

        {/* Advanced Filters (Collapsible) */}
        <Collapse in={showAdvancedFilters}>
          <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <TuneOutlined fontSize="small" />
              Advanced Filters
            </Typography>
            
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              {/* Agent Type Filter */}
              <Box sx={{ flex: '1 1 200px', minWidth: 150 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Agent Type
                </Typography>
                <FormControl fullWidth size="small">
                  <Select
                    multiple
                    value={filters.agent_type || []}
                    onChange={(e) => handleAgentTypeChange(e.target.value as string[])}
                    renderValue={(selected) => (
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {selected.map((value) => (
                          <Chip 
                            key={value} 
                            label={value} 
                            size="small" 
                            color="default"
                          />
                        ))}
                      </Box>
                    )}
                  >
                    {defaultFilterOptions.agent_types.map((agentType) => (
                      <MenuItem key={agentType} value={agentType}>
                        {agentType}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>

              {/* Alert Type Filter */}
              <Box sx={{ flex: '1 1 200px', minWidth: 150 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Alert Type
                </Typography>
                <FormControl fullWidth size="small">
                  <Select
                    multiple
                    value={filters.alert_type || []}
                    onChange={(e) => handleAlertTypeChange(e.target.value as string[])}
                    renderValue={(selected) => (
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {selected.map((value) => (
                          <Chip 
                            key={value} 
                            label={value} 
                            size="small" 
                            color="info"
                          />
                        ))}
                      </Box>
                    )}
                  >
                    {defaultFilterOptions.alert_types.map((alertType) => (
                      <MenuItem key={alertType} value={alertType}>
                        {alertType}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
            </Box>
          </Box>
        </Collapse>

        {/* Active Filter Summary */}
        {hasActiveFilters && (
          <Box sx={{ mt: 2 }}>
            <Divider sx={{ mb: 1 }} />
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Active Filters ({activeFiltersCount}):
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {/* Search filter chip */}
              {filters.search && filters.search.trim() && (
                <Chip
                  key="search"
                  label={`Search: "${filters.search}"`}
                  onDelete={handleClearSearch}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              )}

              {/* Status filter chips */}
              {filters.status && filters.status.map(status => (
                <Chip
                  key={status}
                  label={`Status: ${getStatusDisplayName(status)}`}
                  onDelete={() => handleClearStatus(status)}
                  size="small"
                  variant="outlined"
                  color={getStatusColor(status)}
                />
              ))}

              {/* Agent type filter chips */}
              {filters.agent_type && filters.agent_type.map(agentType => (
                <Chip
                  key={agentType}
                  label={`Agent: ${agentType}`}
                  onDelete={() => handleClearAgentType(agentType)}
                  size="small"
                  variant="outlined"
                  color="default"
                />
              ))}

              {/* Alert type filter chips */}
              {filters.alert_type && filters.alert_type.map(alertType => (
                <Chip
                  key={alertType}
                  label={`Alert: ${alertType}`}
                  onDelete={() => handleClearAlertType(alertType)}
                  size="small"
                  variant="outlined"
                  color="info"
                />
              ))}

              {/* Date range filter chip */}
              {(filters.start_date || filters.end_date || filters.time_range_preset) && (
                <Chip
                  key="date-range"
                  label={
                    filters.time_range_preset 
                      ? `Range: ${filters.time_range_preset}`
                      : filters.start_date && filters.end_date
                        ? `${format(parseISO(filters.start_date), 'MMM d')} - ${format(parseISO(filters.end_date), 'MMM d')}`
                        : filters.start_date
                          ? `From: ${format(parseISO(filters.start_date), 'MMM d, yyyy')}`
                          : `Until: ${format(parseISO(filters.end_date!), 'MMM d, yyyy')}`
                  }
                  onDelete={handleClearDateRange}
                  size="small"
                  variant="outlined"
                  color="secondary"
                />
              )}
            </Box>
          </Box>
        )}
      </Paper>

      {/* Time Range Modal */}
      <TimeRangeModal
        open={timeRangeModalOpen}
        onClose={() => setTimeRangeModalOpen(false)}
        startDate={filters.start_date ? parseISO(filters.start_date) : null}
        endDate={filters.end_date ? parseISO(filters.end_date) : null}
        onApply={handleTimeRangeApply}
      />
    </>
  );
};

export default FilterPanel; 