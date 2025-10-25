import React from 'react';
import { Chip, type ChipProps } from '@mui/material';
import { 
  CheckCircle, 
  Error, 
  Schedule, 
  Refresh,
  HourglassEmpty,
  Cancel
} from '@mui/icons-material';
import type { StatusBadgeProps } from '../types';

// Status configuration mapping
const getStatusConfig = (status: string): { 
  color: ChipProps['color'], 
  icon: React.ReactElement | undefined, 
  label: string 
} => {
  switch (status) {
    case 'pending': 
      return { 
        color: 'warning', 
        icon: <Schedule sx={{ fontSize: 16 }} />, 
        label: 'Pending' 
      };
    case 'in_progress':
      return { 
        color: 'info', 
        icon: <Refresh sx={{ fontSize: 16 }} />, 
        label: 'In Progress' 
      };
    case 'canceling':
      return { 
        color: 'warning', 
        icon: <HourglassEmpty sx={{ fontSize: 16 }} />, 
        label: 'Canceling' 
      };
    case 'completed': 
      return { 
        color: 'success', 
        icon: <CheckCircle sx={{ fontSize: 16 }} />, 
        label: 'Completed' 
      };
    case 'failed': 
      return { 
        color: 'error', 
        icon: <Error sx={{ fontSize: 16 }} />, 
        label: 'Failed' 
      };
    case 'cancelled': 
      return { 
        color: 'default', 
        icon: <Cancel sx={{ fontSize: 16 }} />, 
        label: 'Cancelled' 
      };
    default: 
      return { 
        color: 'default', 
        icon: undefined, 
        label: 'Unknown' 
      };
  }
};

/**
 * StatusBadge component displays session status as a Material-UI Chip
 * with appropriate color and icon based on the status value
 */
const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'small' }) => {
  const { color, icon, label } = getStatusConfig(status);
  
  return (
    <Chip
      size={size}
      color={color}
      icon={icon}
      label={label}
      variant="filled"
      sx={{
        fontWeight: 500,
        '& .MuiChip-icon': {
          marginLeft: '4px',
        },
      }}
    />
  );
};

export default StatusBadge; 