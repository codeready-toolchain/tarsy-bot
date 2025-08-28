import React from 'react';
import { TableRow, TableCell, Typography, IconButton, Tooltip } from '@mui/material';
import { OpenInNew } from '@mui/icons-material';
import StatusBadge from './StatusBadge';
import TokenUsageDisplay from './TokenUsageDisplay';
import { highlightSearchTermNodes } from '../utils/search';
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
      window.open(url, '_blank', 'noopener,noreferrer');
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
        >
          {highlightSearchTermNodes(session.alert_type || '', searchTerm || '')}
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2">
          {session.chain_id}
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
      <TableCell>
        {/* EP-0009: Display session token totals */}
        {(session.session_total_tokens != null ||
          session.session_input_tokens != null ||
          session.session_output_tokens != null) ? (
          <TokenUsageDisplay
            tokenData={{
              input_tokens: session.session_input_tokens,
              output_tokens: session.session_output_tokens,
              total_tokens: session.session_total_tokens
            }}
            variant="inline"
            size="small"
            showBreakdown={false}
          />
        ) : (
          <Typography variant="body2" color="text.secondary">-</Typography>
        )}
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