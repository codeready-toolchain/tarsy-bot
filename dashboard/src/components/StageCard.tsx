import React from 'react';
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Box,
  Chip,
  IconButton,
  Collapse,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Button,
  alpha,
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  PlayArrow,
  Psychology,
  Build,
  Timeline as TimelineIcon,
  Info,
} from '@mui/icons-material';
import TokenUsageDisplay from './TokenUsageDisplay';
import type { StageCardProps, TimelineItem } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';

// Helper function to get stage status configuration
const getStageStatusConfig = (status: string) => {
  switch (status) {
    case 'completed':
      return {
        color: 'success' as const,
        icon: <CheckCircle />,
        label: 'Completed',
        bgColor: 'success.light',
      };
    case 'failed':
      return {
        color: 'error' as const,
        icon: <ErrorIcon />,
        label: 'Failed',
        bgColor: 'error.light',
      };
    case 'active':
      return {
        color: 'primary' as const,
        icon: <PlayArrow />,
        label: 'Running',
        bgColor: 'primary.light',
      };
    case 'pending':
    default:
      return {
        color: 'default' as const,
        icon: <Schedule />,
        label: 'Pending',
        bgColor: 'grey.100',
      };
  }
};

// Helper function to get interaction type icon
const getInteractionIcon = (type: string) => {
  switch (type) {
    case 'llm':
    case 'llm_interaction':
      return <Psychology fontSize="small" />;
    case 'mcp':
    case 'mcp_communication':
      return <Build fontSize="small" />;
    default:
      return <TimelineIcon fontSize="small" />;
  }
};

const StageCard: React.FC<StageCardProps> = ({
  stage,
  expanded = false,
  onToggle,
}) => {
  const statusConfig = getStageStatusConfig(stage.status);
  
  const stageInteractions = [...(stage.llm_interactions || []), ...(stage.mcp_communications || [])].sort((a, b) => a.timestamp_us - b.timestamp_us);
  const hasInteractions = stageInteractions.length > 0;
  const hasOutput = stage.stage_output !== null && stage.stage_output !== undefined;
  const hasTokenData =
    [stage.stage_input_tokens, stage.stage_output_tokens, stage.stage_total_tokens]
      .some((v) => v !== null && v !== undefined);
  const hasError =
    stage.error_message != null &&
    String(stage.error_message).trim().length > 0;

  return (
    <Card 
      sx={{ 
        mb: 2,
        border: '1px solid',
        borderColor: statusConfig.color === 'default' ? 'divider' : `${statusConfig.color}.main`,
        backgroundColor: expanded ? statusConfig.bgColor : 'background.paper',
        opacity: stage.status === 'pending' ? 0.7 : 1,
      }}
    >
      <CardContent sx={{ pb: 1 }}>
        {/* Stage header */}
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
          <Box flex={1}>
            <Box display="flex" alignItems="center" gap={1} mb={1}>
              {statusConfig.icon}
              <Typography variant="h6" component="div">
                Stage {stage.stage_index + 1}: {stage.stage_name}
              </Typography>
              <Chip
                label={statusConfig.label}
                color={statusConfig.color}
                size="small"
                variant="filled"
              />
            </Box>
            <Typography variant="body2" color="text.secondary">
              Agent: {stage.agent}
              {/* iteration_strategy removed in EP-0010 */}
            </Typography>
          </Box>
          
          {onToggle && (hasInteractions || hasOutput || hasError) && (
            <IconButton 
              onClick={onToggle}
              size="small"
              sx={{ ml: 1 }}
            >
              {expanded ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
          )}
        </Box>

        {/* Stage timing */}
        {stage.started_at_us && (
          <Box mb={1}>
            <Typography variant="body2" color="text.secondary">
              <strong>Started:</strong> {formatTimestamp(stage.started_at_us)}
              {stage.completed_at_us && (
                <>
                  <br />
                  <strong>Completed:</strong> {formatTimestamp(stage.completed_at_us)}
                </>
              )}
              {stage.duration_ms && (
                <>
                  <br />
                  <strong>Duration:</strong> {formatDurationMs(stage.duration_ms)}
                </>
              )}
            </Typography>
          </Box>
        )}

        {/* Error message (always visible if present) */}
        {hasError && (
          <Box
            sx={{
              mt: 1,
              p: 1,
              backgroundColor: "error.light",
              borderRadius: 1,
              border: "1px solid",
              borderColor: "error.main"
            }}
          >
            <Typography variant="body2" color="error.dark">
              <strong>Error:</strong> {stage.error_message}
            </Typography>
          </Box>
        )}

        {/* Success indicator */}
        {stage.status === 'completed' && !hasError && (
          <Box
            sx={{
              mt: 1,
              p: 1,
              backgroundColor: "success.light",
              borderRadius: 1,
              border: "1px solid",
              borderColor: "success.main"
            }}
          >
            <Typography variant="body2" color="success.dark">
              <CheckCircle sx={{ fontSize: 16, mr: 0.5, verticalAlign: 'middle' }} />
              Stage completed successfully
            </Typography>
          </Box>
        )}

        {/* Quick stats */}
        {!expanded && (hasInteractions || hasOutput || hasTokenData) && (
          <Box display="flex" gap={1} mt={1} flexWrap="wrap">
            {hasInteractions && (
              <Chip
                icon={<TimelineIcon />}
                label={`${stageInteractions.length} interactions`}
                size="small"
                variant="outlined"
              />
            )}
            {hasOutput && (
              <Chip
                icon={<Info />}
                label="Has output"
                size="small"
                variant="outlined"
                color="primary"
              />
            )}
            {/* EP-0009: Stage token usage chip in collapsed view */}
            {hasTokenData && (
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
      </CardContent>

      {/* Expandable details */}
      <Collapse in={expanded}>
        <Divider />
        <CardContent sx={{ pt: 2 }}>
          {/* Stage output */}
          {hasOutput && (
            <Box mb={2}>
              <Typography variant="subtitle2" gutterBottom>
                Stage Output
              </Typography>
              <Box
                sx={{ 
                  p: 1,
                  backgroundColor: "grey.50",
                  borderRadius: 1,
                  maxHeight: 200, 
                  overflow: 'auto' 
                }}
              >
                <pre style={{ 
                  margin: 0, 
                  fontSize: '0.75rem', 
                  fontFamily: 'monospace',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}>
                  {typeof stage.stage_output === 'string' 
                    ? stage.stage_output 
                    : JSON.stringify(stage.stage_output, null, 2)
                  }
                </pre>
              </Box>
            </Box>
          )}

          {/* Related interactions */}
          {hasInteractions && (
            <Box>
              <Box display="flex" alignItems="center" gap={1} mb={1} flexWrap="wrap">
                <Typography variant="subtitle2">
                  Related Interactions
                </Typography>
                
                {/* Interaction count badges similar to session summary */}
                {stage.total_interactions > 0 && (
                  <Box display="flex" gap={0.5} alignItems="center">
                    {/* Total interactions badge */}
                    <Box sx={{ 
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.25,
                      px: 0.75,
                      py: 0.25,
                      backgroundColor: 'grey.100',
                      borderRadius: '12px',
                      border: '1px solid',
                      borderColor: 'grey.300'
                    }}>
                      <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.7rem' }}>
                        {stage.total_interactions}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
                        total
                      </Typography>
                    </Box>
                    
                    {/* LLM interactions badge */}
                    {stage.llm_interaction_count > 0 && (
                      <Box sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.25,
                        px: 0.75,
                        py: 0.25,
                        backgroundColor: 'primary.50',
                        borderRadius: '12px',
                        border: '1px solid',
                        borderColor: 'primary.200'
                      }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'primary.main', fontSize: '0.7rem' }}>
                          🧠 {stage.llm_interaction_count}
                        </Typography>
                        <Typography variant="caption" color="primary.main" sx={{ fontSize: '0.65rem' }}>
                          LLM
                        </Typography>
                      </Box>
                    )}
                    
                    {/* MCP interactions badge */}
                    {stage.mcp_communication_count > 0 && (
                      <Box sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.25,
                        px: 0.75,
                        py: 0.25,
                        backgroundColor: 'secondary.50',
                        borderRadius: '12px',
                        border: '1px solid',
                        borderColor: 'secondary.200'
                      }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'secondary.main', fontSize: '0.7rem' }}>
                          🔧 {stage.mcp_communication_count}
                        </Typography>
                        <Typography variant="caption" color="secondary.main" sx={{ fontSize: '0.65rem' }}>
                          MCP
                        </Typography>
                      </Box>
                    )}
                    
                    {/* EP-0009: Stage token usage display */}
                    {hasTokenData && (
                      <Box sx={(theme) => ({ 
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.25,
                        px: 0.75,
                        py: 0.25,
                        backgroundColor: alpha(theme.palette.success.main, 0.08),
                        borderRadius: '12px',
                        border: '1px solid',
                        borderColor: alpha(theme.palette.success.main, 0.3)
                      })}>
                        <Typography variant="caption" sx={(theme) => ({ fontWeight: 600, color: theme.palette.success.main, fontSize: '0.65rem' })}>
                          🪙
                        </Typography>
                        <TokenUsageDisplay
                          tokenData={{
                            input_tokens: stage.stage_input_tokens,
                            output_tokens: stage.stage_output_tokens,
                            total_tokens: stage.stage_total_tokens
                          }}
                          variant="inline"
                          size="small"
                        />
                      </Box>
                    )}
                  </Box>
                )}
              </Box>
              <List dense sx={{ pt: 0 }}>
                {[...stageInteractions]
                  .sort((a: TimelineItem, b: TimelineItem) => a.timestamp_us - b.timestamp_us)
                  .map((interaction: TimelineItem, index: number) => (
                    <ListItem 
                      key={interaction.event_id || index}
                      sx={{ 
                        pl: 0,
                        mb: 1,
                        backgroundColor: 'background.paper',
                        borderRadius: 1,
                        border: '1px solid',
                        borderColor: 'divider',
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 36 }}>
                        {getInteractionIcon(interaction.type)}
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Box display="flex" justifyContent="space-between" alignItems="center">
                            <Typography variant="body2">
                              {interaction.step_description}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {formatTimestamp(interaction.timestamp_us)}
                            </Typography>
                          </Box>
                        }
                        secondary={
                          interaction.duration_ms && (
                            <Typography variant="caption" color="text.secondary">
                              Duration: {formatDurationMs(interaction.duration_ms)}
                            </Typography>
                          )
                        }
                      />
                    </ListItem>
                  ))}
              </List>
            </Box>
          )}

          {/* No additional data */}
          {!hasInteractions && !hasOutput && (
            <Typography variant="body2" color="text.secondary" fontStyle="italic">
              No additional data available for this stage
            </Typography>
          )}
        </CardContent>
      </Collapse>

      {/* Card actions */}
      {onToggle && (hasInteractions || hasOutput || hasError) && (
        <CardActions sx={{ pt: 0 }}>
          <Button 
            size="small" 
            onClick={onToggle}
            endIcon={expanded ? <ExpandLess /> : <ExpandMore />}
          >
            {expanded ? 'Hide Details' : 'Show Details'}
          </Button>
        </CardActions>
      )}
    </Card>
  );
};

export default StageCard;