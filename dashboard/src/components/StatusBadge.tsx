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
  
  // Custom styling for cancelled status to make it more noticeable
  const customSx = status === 'cancelled' 
    ? {
        fontWeight: 600,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        color: 'white',
        border: '1px solid rgba(0, 0, 0, 0.8)',
        '& .MuiChip-icon': {
          marginLeft: '4px',
          color: 'white',
        },
      }
    : {
        fontWeight: 500,
        '& .MuiChip-icon': {
          marginLeft: '4px',
        },
      };
  
  return (
    <Chip
      size={size}
      color={color}
      icon={icon}
      label={label}
      variant="filled"
      sx={customSx}
    />
  );
};

export default StatusBadge; 