import { Paper, Button, Box, Typography, Chip, CircularProgress, Stack } from '@mui/material';
import { Clear } from '@mui/icons-material';
import SearchBar from './SearchBar';
import StatusFilter from './StatusFilter';
import type { FilterBarProps } from '../types';

/**
 * FilterBar component for Phase 4 - Search & Basic Filtering
 * Container component that holds search bar and filters with active filter display
 */
const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  onFiltersChange,
  onClearFilters,
  loading = false
}) => {
  // Calculate if any filters are active
  const hasActiveFilters = Boolean(
    (filters.search && filters.search.trim()) ||
    (filters.status && filters.status.length > 0)
  );

  const activeFiltersCount = [
    filters.search && filters.search.trim() ? 1 : 0,
    filters.status && filters.status.length > 0 ? filters.status.length : 0
  ].reduce((sum, count) => sum + count, 0);

  // Get display name for status values
  const getStatusDisplayName = (status: string): string => {
    switch (status) {
      case 'completed':
        return 'Completed';
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      case 'in_progress':
        return 'In Progress';
      case 'pending':
        return 'Pending';
      case 'canceling':
        return 'Canceling';
      default:
        return status;
    }
  };

  // Get color for status chip
  const getStatusColor = (status: string): 'success' | 'error' | 'info' | 'warning' | 'default' => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      case 'cancelled':
        return 'default';
      case 'in_progress':
        return 'info';
      case 'pending':
        return 'warning';
      case 'canceling':
        return 'warning';
      default:
        return 'default';
    }
  };

  const handleSearchChange = (value: string) => {
    onFiltersChange({
      ...filters,
      search: value
    });
  };

  const handleSearchSubmit = (searchTerm: string) => {
    // The search is already handled by handleSearchChange due to debouncing
    // This is called for immediate search (Enter key)
    console.log('🔍 FilterBar: Search submitted:', searchTerm);
  };

  const handleStatusChange = (statuses: string[]) => {
    onFiltersChange({
      ...filters,
      status: statuses as ('completed' | 'failed' | 'cancelled' | 'in_progress' | 'pending' | 'canceling')[]
    });
  };

  const handleClearSearch = () => {
    onFiltersChange({
      ...filters,
      search: ''
    });
  };

  const handleClearStatusFilter = (statusToRemove: string) => {
    const newStatuses = filters.status?.filter(status => status !== statusToRemove) || [];
    onFiltersChange({
      ...filters,
      status: newStatuses
    });
  };

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
        {/* Search Bar */}
        <Box sx={{ flex: 2 }}>
          <SearchBar
            value={filters.search || ''}
            onChange={handleSearchChange}
            onSearch={handleSearchSubmit}
            placeholder="Search alerts by type, error message..."
          />
        </Box>

        {/* Status Filter */}
        <Box sx={{ flex: 1, minWidth: 200 }}>
          <StatusFilter
            value={filters.status || []}
            onChange={handleStatusChange}
          />
        </Box>

        {/* Clear Filters Button */}
        <Box sx={{ flex: 1, minWidth: 150 }}>
          <Button
            variant="outlined"
            startIcon={loading ? <CircularProgress size={16} /> : <Clear />}
            onClick={onClearFilters}
            fullWidth
            disabled={!hasActiveFilters || loading}
          >
            Clear Filters
          </Button>
        </Box>
      </Stack>

      {/* Active Filter Summary */}
      {hasActiveFilters && (
        <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Active filters ({activeFiltersCount}):
          </Typography>
          
          {/* Search filter chip */}
          {filters.search && filters.search.trim() && (
            <Chip
              label={`Search: "${filters.search}"`}
              onDelete={handleClearSearch}
              size="small"
              variant="outlined"
              deleteIcon={<Clear />}
            />
          )}
          
          {/* Status filter chips */}
          {filters.status && filters.status.map(status => (
            <Chip
              key={status}
              label={`Status: ${getStatusDisplayName(status)}`}
              onDelete={() => handleClearStatusFilter(status)}
              size="small"
              variant="outlined"
              color={getStatusColor(status)}
              deleteIcon={<Clear />}
            />
          ))}
        </Box>
      )}
    </Paper>
  );
};

export default FilterBar; 