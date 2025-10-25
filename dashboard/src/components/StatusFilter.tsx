import { FormControl, InputLabel, Select, MenuItem, Chip, Box } from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import type { StatusFilterProps } from '../types';
import { ALL_STATUSES, getStatusDisplayName, getStatusColor } from '../utils/sessionStatus';

/**
 * StatusFilter component for Phase 4 - Search & Basic Filtering
 * Provides multi-select dropdown for session status filtering
 */
const StatusFilter: React.FC<StatusFilterProps> = ({
  value,
  onChange,
  options = ALL_STATUSES
}) => {
  const handleChange = (event: SelectChangeEvent<string[]>) => {
    const selectedValues = event.target.value as string[];
    onChange(selectedValues);
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