import React from 'react';
import { Chip, type ChipProps, type SxProps, type Theme } from '@mui/material';
import { 
  CheckCircle, 
  Error as ErrorIcon, 
  Schedule, 
  Refresh,
  HourglassEmpty,
  Cancel,
  PauseCircle
} from '@mui/icons-material';
import { SESSION_STATUS } from '../utils/statusConstants';
import type { StatusBadgeProps } from '../types';

// Status configuration mapping
const getStatusConfig = (status: string): { 
  color: ChipProps['color'], 
  icon: React.ReactElement | undefined, 
  label: string 
} => {
  switch (status) {
    case SESSION_STATUS.PENDING: 
      return { 
        color: 'warning', 
        icon: <Schedule sx={{ fontSize: 16 }} />, 
        label: 'Pending' 
      };
    case SESSION_STATUS.IN_PROGRESS:
      return { 
        color: 'info', 
        icon: <Refresh sx={{ fontSize: 16 }} />, 
        label: 'In Progress' 
      };
    case SESSION_STATUS.PAUSED:
      return { 
        color: 'warning', 
        icon: <PauseCircle sx={{ fontSize: 16 }} />, 
        label: 'Paused' 
      };
    case SESSION_STATUS.CANCELING:
      return { 
        color: 'warning', 
        icon: <HourglassEmpty sx={{ fontSize: 16 }} />, 
        label: 'Canceling' 
      };
    case SESSION_STATUS.COMPLETED: 
      return { 
        color: 'success', 
        icon: <CheckCircle sx={{ fontSize: 16 }} />, 
        label: 'Completed' 
      };
    case SESSION_STATUS.FAILED: 
      return { 
        color: 'error', 
        icon: <ErrorIcon sx={{ fontSize: 16 }} />, 
        label: 'Failed' 
      };
    case SESSION_STATUS.CANCELLED: 
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
  
  // Base styling for all status badges (non-interactive/static)
  const baseSx: SxProps<Theme> = {
    fontWeight: 500,
    transition: 'none', // Disable all transitions for static badges
    transform: 'none',  // Disable all transforms for static badges
    '&.MuiChip-root': {
      animation: 'none', // Disable default animations
    },
    // Consistent focus indicator for keyboard navigation (accessibility)
    '&:focus-visible': {
      outline: '2px solid',
      outlineColor: 'primary.main',
      outlineOffset: '2px',
      boxShadow: '0 0 0 4px rgba(25, 118, 210, 0.2)', // Subtle glow for visibility
    },
    // Disable ripple effect by targeting the ripple element
    '& .MuiTouchRipple-root': {
      display: 'none',
    },
    '& .MuiChip-icon': {
      marginLeft: '4px',
    },
  };

  // Custom styling for special statuses
  let customSx: SxProps<Theme> = { ...baseSx };

  if (status === SESSION_STATUS.CANCELLED) {
    customSx = {
      ...baseSx,
      fontWeight: 600,
      backgroundColor: 'rgba(0, 0, 0, 0.7)',
      color: 'white',
      border: '1px solid rgba(0, 0, 0, 0.8)',
      '& .MuiChip-icon': {
        marginLeft: '4px',
        color: 'white',
      },
    };
  } else if (status === SESSION_STATUS.PAUSED) {
    customSx = {
      ...baseSx,
      fontWeight: 600,
      backgroundColor: '#e65100',
      color: 'white',
      '& .MuiChip-icon': {
        marginLeft: '4px',
        color: 'white',
      },
      animation: 'pulse 2s ease-in-out infinite !important', // Force our custom animation (override baseSx)
      transition: 'none !important',
      transform: 'none !important',
      '&:focus-visible': {
        outline: '2px solid #ffffff',
        outlineOffset: '2px',
        boxShadow: '0 0 0 4px rgba(255, 152, 0, 0.4)',
      },
      '@keyframes pulse': {
        '0%, 100%': {
          backgroundColor: '#e65100',
        },
        '50%': {
          backgroundColor: '#ff9800',
        },
      },
    };
  }
  
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