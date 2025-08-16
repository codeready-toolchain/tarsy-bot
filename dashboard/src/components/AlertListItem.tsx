import React from 'react';
import { TableRow, TableCell, Typography, IconButton, Tooltip } from '@mui/material';
import { OpenInNew } from '@mui/icons-material';
import StatusBadge from './StatusBadge';
import { highlightSearchTerm } from '../utils/search';
import type { AlertListItemProps } from '../types';
import { formatTimestamp, formatDurationMs, formatDuration } from '../utils/timestamp';

/**
 * AlertListItem component represents a single session row in the alerts table
 * Displays basic session information with Phase 4 search highlighting support
 * Uses Unix timestamp utilities for optimal performance and consistent formatting
 */
const AlertListItem: React.FC<AlertListItemProps> = ({ session, onClick, searchTerm }) => {
  const handleRowClick = () => {
    if (onClick) {
      if (!session.session_id) {
        console.warn('Session has no ID:', session);
        return;
      }
      onClick(session.session_id);
    }
  };

  // Handle new tab icon click
  const handleNewTabClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row click
    if (session.session_id) {
      const url = `${window.location.origin}/sessions/${session.session_id}`;
      window.open(url, '_blank');
    }
  };

  // Calculate duration if not provided
  const duration = session.duration_ms || 
    (session.completed_at_us ? formatDuration(session.started_at_us, session.completed_at_us) : null);

  return (
    <TableRow 
      hover 
      onClick={handleRowClick}
      sx={{ 
        cursor: onClick ? 'pointer' : 'default',
        '&:hover': {
          backgroundColor: 'action.hover',
        },
      }}
    >
      <TableCell>
        <StatusBadge status={session.status} />
      </TableCell>
      <TableCell>
        <Typography 
          variant="body2" 
          sx={{ fontWeight: 500 }}
          dangerouslySetInnerHTML={{
            __html: highlightSearchTerm(session.alert_type || '', searchTerm || '')
          }}
        />
      </TableCell>
      <TableCell>
        <Typography variant="body2">
          {session.agent_type}
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2" color="text.secondary">
          {formatTimestamp(session.started_at_us, 'short')}
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2" color="text.secondary">
          {typeof duration === 'string' ? duration : 
           duration !== null ? formatDurationMs(duration) : '-'}
        </Typography>
      </TableCell>
      <TableCell sx={{ width: 60, textAlign: 'center' }}>
        <Tooltip title="Open in new tab">
          <IconButton
            size="small"
            onClick={handleNewTabClick}
            sx={{
              opacity: 0.7,
              '&:hover': {
                opacity: 1,
                backgroundColor: 'action.hover',
              },
            }}
          >
            <OpenInNew fontSize="small" />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
};

export default AlertListItem; 