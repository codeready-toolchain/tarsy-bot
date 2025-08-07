import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  IconButton,
  Collapse,
  Divider,
  useTheme,
} from '@mui/material';
import { 
  Timeline,
  CheckCircle,
  Cancel,
  ExpandMore,
  ExpandLess,
  AccessTime,
  TrackChanges
} from '@mui/icons-material';
import type { IterationSummary } from '../types';

interface IterationSummaryCardProps {
  summary: IterationSummary;
}

const IterationSummaryCard: React.FC<IterationSummaryCardProps> = ({ summary }) => {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(false);

  const formatDuration = (durationMs: number) => {
    if (durationMs < 1000) {
      return `${durationMs}ms`;
    }
    const seconds = (durationMs / 1000).toFixed(1);
    return `${seconds}s`;
  };

  const getContinueDecisionIcon = (decision: boolean) => {
    return decision ? (
      <CheckCircle color="success" sx={{ fontSize: '1.2rem' }} />
    ) : (
      <Cancel color="error" sx={{ fontSize: '1.2rem' }} />
    );
  };

  const getContinueDecisionColor = (decision: boolean): 'success' | 'error' => {
    return decision ? 'success' : 'error';
  };

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 2,
        borderLeft: `4px solid ${theme.palette.primary.main}`,
        '&:hover': {
          boxShadow: 2,
        },
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
          {/* Icon */}
          <Box sx={{ mt: 0.5 }}>
            <Timeline color="primary" />
          </Box>

          {/* Summary Content */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
              <Typography variant="h6" sx={{ fontSize: '1.1rem' }}>
                Iteration {summary.iteration_number}
              </Typography>
              
              <Chip
                icon={<AccessTime sx={{ fontSize: '0.9rem' }} />}
                label={formatDuration(summary.duration_ms)}
                size="small"
                variant="outlined"
                color="primary"
              />

              <Chip
                icon={getContinueDecisionIcon(summary.continue_decision)}
                label={summary.continue_decision ? 'Continued' : 'Completed'}
                size="small"
                color={getContinueDecisionColor(summary.continue_decision)}
                variant="filled"
              />
            </Box>

            {/* Objective */}
            <Box sx={{ mb: 1 }}>
              <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <TrackChanges sx={{ fontSize: '1rem' }} />
                Objective:
              </Typography>
              <Typography variant="body2" sx={{ pl: 2.5 }}>
                {summary.objective}
              </Typography>
            </Box>

            {/* Key Findings */}
            <Box sx={{ mb: expanded ? 2 : 0 }}>
              <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                Key Findings:
              </Typography>
              <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                {expanded ? summary.key_findings : (
                  summary.key_findings.length > 150 
                    ? `${summary.key_findings.substring(0, 150)}...`
                    : summary.key_findings
                )}
              </Typography>
            </Box>

            {/* Expanded Content */}
            <Collapse in={expanded}>
              {summary.continue_reasoning && (
                <>
                  <Divider sx={{ my: 1 }} />
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                      Decision Reasoning:
                    </Typography>
                    <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                      {summary.continue_reasoning}
                    </Typography>
                  </Box>
                </>
              )}

              {summary.next_steps && (
                <>
                  <Divider sx={{ my: 1 }} />
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                      Next Steps:
                    </Typography>
                    <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
                      {summary.next_steps}
                    </Typography>
                  </Box>
                </>
              )}
            </Collapse>
          </Box>

          {/* Expand/Collapse Button */}
          {(summary.key_findings.length > 150 || summary.continue_reasoning || summary.next_steps) && (
            <IconButton
              size="small"
              onClick={() => setExpanded(!expanded)}
              sx={{ mt: -0.5 }}
              aria-label={expanded ? "Collapse" : "Expand"}
            >
              {expanded ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

export default IterationSummaryCard;