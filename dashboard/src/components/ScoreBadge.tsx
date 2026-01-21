import React from 'react';
import { Chip, Tooltip, CircularProgress } from '@mui/material';
import { CheckCircle, Error, Warning, HourglassEmpty } from '@mui/icons-material';
import type { ScoringStatus } from '../types';

interface ScoreBadgeProps {
  score: number | null;
  status?: ScoringStatus;
  onClick?: (event: React.MouseEvent) => void;
  size?: 'small' | 'medium';
  label?: string; // Optional label to show after the score (e.g., 'score', 'points')
}

/**
 * ScoreBadge component displays session quality score with 3-tier color coding
 *
 * Color scheme (aligned with judge prompt scoring philosophy):
 * - 0-49: Red (failed investigation)
 * - 50-74: Yellow (weak investigation)
 * - 75-100: Green (good investigation)
 *
 * Also handles pending/in_progress/failed states
 */
const ScoreBadge: React.FC<ScoreBadgeProps> = ({
  score,
  status,
  onClick,
  size = 'small',
  label: customLabel,
}) => {
  // Handle different scoring states
  if (status === 'pending' || status === 'in_progress') {
    return (
      <Tooltip title={status === 'pending' ? 'Score pending' : 'Scoring in progress'} arrow>
        <Chip
          icon={status === 'in_progress' ? <CircularProgress size={14} /> : <HourglassEmpty />}
          label={status === 'in_progress' ? 'Scoring...' : 'Pending'}
          size={size}
          variant="outlined"
          color="default"
          onClick={onClick}
          sx={{ cursor: onClick ? 'pointer' : 'default' }}
        />
      </Tooltip>
    );
  }

  if (status === 'failed') {
    return (
      <Tooltip title="Scoring failed" arrow>
        <Chip
          icon={<Error />}
          label="Error"
          size={size}
          color="error"
          variant="outlined"
          onClick={onClick}
          sx={{ cursor: onClick ? 'pointer' : 'default' }}
        />
      </Tooltip>
    );
  }

  // No score available
  if (score === null || score === undefined) {
    return (
      <Tooltip title="Not scored" arrow>
        <Chip
          label="Not Scored"
          size={size}
          variant="outlined"
          color="default"
          onClick={onClick}
          sx={{ cursor: onClick ? 'pointer' : 'default' }}
        />
      </Tooltip>
    );
  }

  // Determine color and label based on score
  let color: 'error' | 'warning' | 'success' = 'success';
  let icon: React.ReactElement | undefined;
  let chipLabel = '';
  let tooltip = '';

  if (score < 50) {
    color = 'error';
    icon = <Error />;
    chipLabel = customLabel ? `${score} ${customLabel}` : `${score}`;
    tooltip = `Score: ${score}/100 - Failed investigation`;
  } else if (score < 75) {
    color = 'warning';
    icon = <Warning />;
    chipLabel = customLabel ? `${score} ${customLabel}` : `${score}`;
    tooltip = `Score: ${score}/100 - Weak investigation`;
  } else {
    color = 'success';
    icon = <CheckCircle />;
    chipLabel = customLabel ? `${score} ${customLabel}` : `${score}`;
    tooltip = `Score: ${score}/100 - Good investigation`;
  }

  return (
    <Tooltip title={tooltip} arrow>
      <Chip
        icon={icon}
        label={chipLabel}
        size={size}
        color={color}
        onClick={onClick}
        sx={{
          cursor: onClick ? 'pointer' : 'default',
          fontWeight: 600
        }}
      />
    </Tooltip>
  );
};

export default ScoreBadge;
