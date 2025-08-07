import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  IconButton,
  useTheme,
} from '@mui/material';
import { 
  Psychology, 
  PlayArrow, 
  Visibility, 
  Assessment,
  CheckCircle,
  ExpandMore,
  ExpandLess
} from '@mui/icons-material';
import type { ReasoningTrace } from '../types';
import { formatTimestamp } from '../utils/timestamp';

interface ReasoningStepCardProps {
  step: ReasoningTrace;
  expanded?: boolean;
  onToggle?: () => void;
}

const ReasoningStepCard: React.FC<ReasoningStepCardProps> = ({
  step,
  expanded = false,
  onToggle
}) => {
  const theme = useTheme();

  const getStepIcon = (stepType: ReasoningTrace['step_type']) => {
    switch (stepType) {
      case 'thought':
        return <Psychology color="primary" />;
      case 'action':
        return <PlayArrow color="success" />;
      case 'observation':
        return <Visibility color="info" />;
      case 'analysis':
        return <Assessment color="warning" />;
      case 'conclusion':
        return <CheckCircle color="success" />;
      default:
        return <Psychology />;
    }
  };

  const getStepColor = (stepType: ReasoningTrace['step_type']) => {
    switch (stepType) {
      case 'thought':
        return theme.palette.primary.main;
      case 'action':
        return theme.palette.success.main;
      case 'observation':
        return theme.palette.info.main;
      case 'analysis':
        return theme.palette.warning.main;
      case 'conclusion':
        return theme.palette.success.main;
      default:
        return theme.palette.grey[500];
    }
  };

  const getConfidenceColor = (level?: string): 'success' | 'warning' | 'error' | 'default' => {
    switch (level) {
      case 'high':
        return 'success';
      case 'medium':
        return 'warning';
      case 'low':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 1,
        borderLeft: `4px solid ${getStepColor(step.step_type)}`,
        '&:hover': {
          boxShadow: 2,
        },
      }}
    >
      <CardContent sx={{ pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
          {/* Step Icon */}
          <Box sx={{ mt: 0.5 }}>
            {getStepIcon(step.step_type)}
          </Box>

          {/* Step Content */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
              <Typography variant="h6" sx={{ textTransform: 'capitalize', fontSize: '1.1rem' }}>
                {step.step_type}
              </Typography>
              
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip
                  label={`Iteration ${step.iteration_number}`}
                  size="small"
                  variant="outlined"
                  color="primary"
                />
                
                {step.confidence_level && (
                  <Chip
                    label={`${step.confidence_level} confidence`}
                    size="small"
                    color={getConfidenceColor(step.confidence_level)}
                    variant="filled"
                  />
                )}
              </Box>

              <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                {formatTimestamp(step.timestamp_us, 'time-only')}
              </Typography>
            </Box>

            {/* Reasoning Text */}
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
              {expanded ? step.reasoning_text : (
                step.reasoning_text.length > 200 
                  ? `${step.reasoning_text.substring(0, 200)}...`
                  : step.reasoning_text
              )}
            </Typography>

            {/* Context Data (if available) */}
            {expanded && step.context_data && Object.keys(step.context_data).length > 0 && (
              <Box sx={{ mt: 2, p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 'bold' }}>
                  Context:
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  {JSON.stringify(step.context_data, null, 2)}
                </Typography>
              </Box>
            )}
          </Box>

          {/* Expand/Collapse Button */}
          {(step.reasoning_text.length > 200 || (step.context_data && Object.keys(step.context_data).length > 0)) && (
            <IconButton
              size="small"
              onClick={onToggle}
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

export default ReasoningStepCard;