import React from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Box,
  Chip,
  Avatar,
  Alert,
  alpha
} from '@mui/material';
import {
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  PlayArrow,
  Build
} from '@mui/icons-material';
import type { StageConversation } from '../utils/conversationParser';
import ConversationStep from './ConversationStep';
import CopyButton from './CopyButton';
import TypingIndicator from './TypingIndicator';
import TokenUsageDisplay from './TokenUsageDisplay';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';

export interface StageConversationCardProps {
  stage: StageConversation;
  stageIndex: number;
  isRecentlyUpdated?: boolean;
}

// Helper function to get stage status configuration with better colors
const getStageStatusConfig = (status: string, stageIndex: number) => {
  // Use different colors for different stages to reduce green overload
  const stageColors = ['primary', 'info', 'warning', 'secondary'];
  const defaultColor = stageColors[stageIndex % stageColors.length];
  
  switch (status) {
    case 'completed':
      return {
        color: defaultColor as 'primary' | 'info' | 'warning' | 'secondary',
        icon: <CheckCircle />,
        label: 'Completed',
        bgColor: (theme: any) => alpha(theme.palette[defaultColor].main, 0.06),
        borderColor: `${defaultColor}.main`
      };
    case 'failed':
      return {
        color: 'error' as const,
        icon: <ErrorIcon />,
        label: 'Failed',
        bgColor: (theme: any) => alpha(theme.palette.error.main, 0.06),
        borderColor: 'error.main'
      };
    case 'active':
      return {
        color: 'primary' as const,
        icon: <PlayArrow />,
        label: 'Active',
        bgColor: (theme: any) => alpha(theme.palette.primary.main, 0.06),
        borderColor: 'primary.main'
      };
    case 'pending':
    default:
      return {
        color: 'default' as const,
        icon: <Schedule />,
        label: 'Pending',
        bgColor: (theme: any) => alpha(theme.palette.grey[400], 0.06),
        borderColor: 'grey.400'
      };
  }
};

/**
 * Stage conversation card component
 * Displays a single stage with its conversation steps in chronological order
 */
function StageConversationCard({ 
  stage, 
  stageIndex,
  isRecentlyUpdated = false
}: StageConversationCardProps) {
  const statusConfig = getStageStatusConfig(stage.status, stageIndex);
  
  const formatStageForCopy = (): string => {
    let content = `=== Stage ${stageIndex + 1}: ${stage.stage_name} ===\n`;
    content += `Agent: ${stage.agent}\n`;
    content += `Status: ${stage.status}\n`;
    
    if (stage.duration_ms) {
      content += `Duration: ${formatDurationMs(stage.duration_ms)}\n`;
    }
    
    content += '\n--- Conversation ---\n';
    
    stage.steps.forEach((step, stepIndex) => {
      const emoji = step.type === 'thought' ? '💭' : 
                   step.type === 'action' ? '🔧' : 
                   step.type === 'analysis' ? '🎯' : step.type === 'summarization' ? '📋' : '❌';
      
      content += `${emoji} ${step.content}\n`;
      
      if (step.type === 'action' && step.actionName) {
        content += `   Action: ${step.actionName}${step.actionInput ? ` ${step.actionInput}` : ''}\n`;
        
        if (step.actionResult) {
          const result = typeof step.actionResult === 'string' ? 
                        step.actionResult : 
                        JSON.stringify(step.actionResult, null, 2);
          content += `   Result: ${result}\n`;
        }
      }
      
      if (stepIndex < stage.steps.length - 1) {
        content += '\n';
      }
    });
    
    return content;
  };

  const getStepStats = () => {
    const stats = {
      thoughts: 0,
      actions: 0,
      analyses: 0,
      errors: 0,
      successfulActions: 0
    };

    stage.steps.forEach(step => {
      switch (step.type) {
        case 'thought':
          stats.thoughts++;
          break;
        case 'action':
          stats.actions++;
          if (step.success) {
            stats.successfulActions++;
          }
          break;
        case 'analysis':
          stats.analyses++;
          break;
        case 'error':
          stats.errors++;
          break;
      }
    });

    return stats;
  };

  const stats = getStepStats();

  return (
    <Card 
      sx={{ 
        mb: 3,
        border: `2px solid`,
        borderColor: statusConfig.borderColor,
        borderRadius: 2,
        overflow: 'visible'
      }}
    >
      {/* Stage Header */}
      <CardHeader
        avatar={
          <Avatar
            sx={{
              bgcolor: `${statusConfig.color}.main`,
              color: 'white',
              width: 48,
              height: 48
            }}
          >
            {statusConfig.icon}
          </Avatar>
        }
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '1.1rem' }}>
              Stage {stageIndex + 1}: {stage.stage_name}
            </Typography>
            {isRecentlyUpdated && (
              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  bgcolor: 'success.main',
                  color: 'white',
                  px: 0.75,
                  py: 0.25,
                  borderRadius: 1,
                  fontSize: '0.7rem',
                  fontWeight: 'medium',
                  animation: 'pulse 2s ease-in-out infinite',
                  '@keyframes pulse': {
                    '0%': { opacity: 1 },
                    '50%': { opacity: 0.7 },
                    '100%': { opacity: 1 }
                  }
                }}
              >
                🔄 Updated
              </Box>
            )}
          </Box>
        }
        subheader={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary">
              Agent: {stage.agent}
            </Typography>
            
            <Chip 
              label={statusConfig.label}
              size="small" 
              color={statusConfig.color}
              sx={{ height: 22 }}
            />
            
            {/* Step Statistics */}
            {stage.steps.length > 0 && (
              <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                <Chip
                  size="small"
                  label={`${stage.steps.length} steps`}
                  variant="outlined"
                  sx={{ height: 22, fontSize: '0.75rem' }}
                />
                
                {stats.actions > 0 && (
                  <Chip
                    size="small"
                    label={`${stats.successfulActions}/${stats.actions} actions`}
                    variant="outlined"
                    color={stats.successfulActions === stats.actions ? 'success' : 'warning'}
                    sx={{ height: 22, fontSize: '0.75rem' }}
                  />
                )}
                
                {stats.errors > 0 && (
                  <Chip
                    size="small"
                    label={`${stats.errors} errors`}
                    variant="outlined"
                    color="error"
                    sx={{ height: 22, fontSize: '0.75rem' }}
                  />
                )}
                
                {/* Token usage chip */}
                {(stage.stage_total_tokens != null || stage.stage_input_tokens != null || stage.stage_output_tokens != null) && (
                  <TokenUsageDisplay
                    tokenData={{
                      input_tokens: stage.stage_input_tokens,
                      output_tokens: stage.stage_output_tokens,
                      total_tokens: stage.stage_total_tokens
                    }}
                    variant="badge"
                    size="small"
                    color="success"
                  />
                )}
              </Box>
            )}
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {stage.duration_ms && (
              <Chip 
                label={formatDurationMs(stage.duration_ms)}
                size="small"
                variant="outlined"
                sx={{ fontSize: '0.75rem' }}
              />
            )}
            
            <CopyButton
              text={formatStageForCopy()}
              variant="icon"
              size="small"
              tooltip="Copy stage conversation"
            />
          </Box>
        }
        sx={{ 
          bgcolor: statusConfig.bgColor,
          borderBottom: 1,
          borderColor: 'divider'
        }}
      />

      {/* Stage Content */}
      <CardContent sx={{ pt: 2, pb: 2 }}>
        {/* Stage Error Message */}
        {stage.errorMessage && (
          <Alert 
            severity="error" 
            sx={{ mb: 2 }}
            icon={<ErrorIcon />}
          >
            <Typography variant="body2">
              <strong>Stage Error:</strong> {stage.errorMessage}
            </Typography>
          </Alert>
        )}

        {/* Timing Information */}
        {(stage.started_at_us || stage.completed_at_us) && (
          <Box sx={{ 
            mb: 2, 
            p: 1.5,
            bgcolor: (theme) => alpha(theme.palette.grey[400], 0.06),
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'grey.200'
          }}>
            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              {stage.started_at_us && (
                <Typography variant="body2" color="text.secondary">
                  <strong>Started:</strong> {formatTimestamp(stage.started_at_us, 'absolute')}
                </Typography>
              )}
              
              {stage.completed_at_us && (
                <Typography variant="body2" color="text.secondary">
                  <strong>Completed:</strong> {formatTimestamp(stage.completed_at_us, 'absolute')}
                </Typography>
              )}
              
              {stage.duration_ms && (
                <Typography variant="body2" color="text.secondary">
                  <strong>Duration:</strong> {formatDurationMs(stage.duration_ms)}
                </Typography>
              )}
            </Box>
          </Box>
        )}

        {/* Conversation Steps */}
        {stage.steps.length > 0 ? (
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            {stage.steps.map((step, stepIndex) => (
              <ConversationStep
                key={stepIndex}
                step={step}
                stepIndex={stepIndex}
                isLastStep={stepIndex === stage.steps.length - 1}
              />
            ))}
          </Box>
        ) : (
          <Box sx={{ 
            textAlign: 'center', 
            py: 4,
            color: 'text.secondary',
            fontStyle: 'italic'
          }}>
            <Build sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
            <Typography variant="body2">
              {stage.status === 'pending' ? 
                'Stage is waiting to begin...' :
                'No conversation steps recorded for this stage'
              }
            </Typography>
          </Box>
        )}

        {/* Show typing indicator for active or pending stages */}
        {(() => {
          const shouldShow = stage.status === 'active' || stage.status === 'pending';
          
          if (shouldShow) {
            return (
              <Box sx={{ mt: 2 }}>
                <TypingIndicator
                  dotsOnly={true}
                  size="small"
                />
              </Box>
            );
          }
          return null;
        })()}
      </CardContent>
    </Card>
  );
}

// Helper function to create a lightweight fingerprint of the last step
const createLastStepFingerprint = (steps: any[]) => {
  if (steps.length === 0) return '';
  const lastStep = steps[steps.length - 1];
  return `${lastStep.type || ''}-${lastStep.content?.substring(0, 50) || ''}-${lastStep.timestamp_us || ''}-${lastStep.success || ''}`;
};

// Wrap with React.memo to prevent unnecessary re-renders of individual stages
export default React.memo(StageConversationCard, (prevProps, nextProps) => {
  // Custom comparison function to optimize re-renders
  const prevStage = prevProps.stage;
  const nextStage = nextProps.stage;
  
  // Create fingerprints for the last step to detect content changes
  const prevLastStepFingerprint = createLastStepFingerprint(prevStage.steps);
  const nextLastStepFingerprint = createLastStepFingerprint(nextStage.steps);
  
  return (
    // Core stage identification
    prevStage.execution_id === nextStage.execution_id &&
    prevStage.status === nextStage.status &&
    prevProps.stageIndex === nextProps.stageIndex &&
    prevProps.isRecentlyUpdated === nextProps.isRecentlyUpdated &&
    
    // Step-related comparisons
    prevStage.steps.length === nextStage.steps.length &&
    prevLastStepFingerprint === nextLastStepFingerprint &&
    
    // Commonly-updated fields that indicate stage changes
    prevStage.completed_at_us === nextStage.completed_at_us &&
    prevStage.duration_ms === nextStage.duration_ms &&
    prevStage.started_at_us === nextStage.started_at_us &&
    prevStage.errorMessage === nextStage.errorMessage &&
    
    // Token fields
    prevStage.stage_total_tokens === nextStage.stage_total_tokens &&
    prevStage.stage_input_tokens === nextStage.stage_input_tokens &&
    prevStage.stage_output_tokens === nextStage.stage_output_tokens
  );
});
