import { FormControl, InputLabel, Select, MenuItem, Chip, Box } from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import type { StatusFilterProps } from '../types';

/**
 * StatusFilter component for Phase 4 - Search & Basic Filtering
 * Provides multi-select dropdown for session status filtering
 */
const StatusFilter: React.FC<StatusFilterProps> = ({
  value,
  onChange,
  options = ['completed', 'failed', 'cancelled', 'in_progress', 'pending', 'canceling']
}) => {
  const handleChange = (event: SelectChangeEvent<string[]>) => {
    const selectedValues = event.target.value as string[];
    onChange(selectedValues);
  };

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

  return (
    <FormControl fullWidth size="small">
      <InputLabel id="status-filter-label">Status</InputLabel>
      <Select
        labelId="status-filter-label"
        id="status-filter"
        multiple
        value={value}
        label="Status"
        onChange={handleChange}
        renderValue={(selected) => (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {selected.map((statusValue) => (
              <Chip
                key={statusValue}
                label={getStatusDisplayName(statusValue)}
                size="small"
                color={getStatusColor(statusValue)}
                variant="outlined"
              />
            ))}
          </Box>
        )}
        MenuProps={{
          PaperProps: {
            style: {
              maxHeight: 48 * 4.5 + 8,
              width: 250,
            },
          },
        }}
        sx={{
          '& .MuiOutlinedInput-root': {
            backgroundColor: 'background.paper',
            '&:hover': {
              backgroundColor: 'background.paper',
            },
            '&.Mui-focused': {
              backgroundColor: 'background.paper',
            },
          },
        }}
      >
        {options.map((status) => (
          <MenuItem key={status} value={status}>
            <Chip
              label={getStatusDisplayName(status)}
              size="small"
              color={getStatusColor(status)}
              variant={value.includes(status) ? 'filled' : 'outlined'}
              sx={{ mr: 1 }}
            />
            {getStatusDisplayName(status)}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
};

export default StatusFilter; 