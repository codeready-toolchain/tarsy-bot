import { memo } from 'react';
import { Box, Typography, Card, CardContent, Stack, Divider } from '@mui/material';
import TokenUsageDisplay from './TokenUsageDisplay';
import type { TokenUsageData } from './TokenUsageDisplay';
import type { Session, StageExecution, InteractionDetail, LLMInteractionDetail } from '../types';

export interface MultiLevelTokenDisplayProps {
  session?: Session;
  stages?: StageExecution[];
  interactions?: InteractionDetail[];
  showSessionLevel?: boolean;
  showStageLevel?: boolean;
  showInteractionLevel?: boolean;
  variant?: 'card' | 'inline' | 'minimal';
  maxInteractionsToShow?: number;
}

/**
 * MultiLevelTokenDisplay component - EP-0009 Phase 3
 * Displays token usage at all levels simultaneously (session, stage, interaction)
 */
function MultiLevelTokenDisplay({
  session,
  stages = [],
  interactions = [],
  showSessionLevel = true,
  showStageLevel = true,
  showInteractionLevel = false, // Default false for performance
  variant = 'card',
  maxInteractionsToShow = 10
}: MultiLevelTokenDisplayProps) {

  // Extract session-level tokens
  const sessionTokens: TokenUsageData = {
    input_tokens: session?.session_input_tokens,
    output_tokens: session?.session_output_tokens,
    total_tokens: session?.session_total_tokens
  };

  // Type guard to properly narrow LLM interactions
  const isLLM = (i: InteractionDetail): i is LLMInteractionDetail => i.type === 'llm';
  
  // Pre-filter LLM interactions to avoid repeated filtering
  const llmInteractions = interactions.filter(isLLM);

  // Check if we have any token data to display using nullish checks
  const exists = (v: number | null | undefined) => v !== null && v !== undefined;
  const hasSessionTokens = [sessionTokens.total_tokens, sessionTokens.input_tokens, sessionTokens.output_tokens].some(exists);
  const hasStageTokens = stages.some((stage) =>
    [stage.stage_total_tokens, stage.stage_input_tokens, stage.stage_output_tokens].some(exists)
  );
  const hasInteractionTokens = llmInteractions.some((i) =>
    [i.details.total_tokens, i.details.input_tokens, i.details.output_tokens].some(exists)
  );

  // If no token data anywhere, don't render anything
  if (!hasSessionTokens && !hasStageTokens && !hasInteractionTokens) {
    return null;
  }

  const renderContent = () => (
    <Stack spacing={2}>
      {/* Session-level token summary */}
      {showSessionLevel && hasSessionTokens && (
        <Box>
          <TokenUsageDisplay
            tokenData={sessionTokens}
            variant="detailed"
            size="medium"
            showBreakdown={true}
            label="Session Total"
            color="primary"
          />
        </Box>
      )}

      {/* Stage-level token breakdown */}
      {showStageLevel && hasStageTokens && (
        <Box>
          {showSessionLevel && hasSessionTokens && <Divider sx={{ my: 1 }} />}
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: 'text.secondary' }}>
            Stage Breakdown
          </Typography>
          <Stack spacing={1}>
            {stages.map((stage) => {
              const stageTokens: TokenUsageData = {
                input_tokens: stage.stage_input_tokens,
                output_tokens: stage.stage_output_tokens,
                total_tokens: stage.stage_total_tokens
              };

              // Only show stages that have token data
              if (![stageTokens.total_tokens, stageTokens.input_tokens, stageTokens.output_tokens].some(exists)) {
                return null;
              }

              return (
                <Box key={stage.execution_id}>
                  <TokenUsageDisplay
                    tokenData={stageTokens}
                    variant="compact"
                    size="small"
                    showBreakdown={true}
                    label={stage.stage_name}
                    color="secondary"
                  />
                </Box>
              );
            })}
          </Stack>
        </Box>
      )}

      {/* Individual interaction token details */}
      {showInteractionLevel && hasInteractionTokens && (
        <Box>
          {(showSessionLevel && hasSessionTokens) || (showStageLevel && hasStageTokens) ? (
            <Divider sx={{ my: 1 }} />
          ) : null}
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, color: 'text.secondary' }}>
            Individual Interactions
          </Typography>
          <Stack spacing={0.5}>
            {llmInteractions
              .slice(0, maxInteractionsToShow)
              .map((interaction, index) => {
                const details = interaction.details;
                const interactionTokens: TokenUsageData = {
                  input_tokens: details.input_tokens,
                  output_tokens: details.output_tokens,
                  total_tokens: details.total_tokens
                };

                // Only show interactions that have token data
                if (![interactionTokens.total_tokens, interactionTokens.input_tokens, interactionTokens.output_tokens].some(exists)) {
                  return null;
                }

                return (
                  <Box key={interaction.event_id}>
                    <TokenUsageDisplay
                      tokenData={interactionTokens}
                      variant="compact"
                      size="small"
                      showBreakdown={false}
                      label={`Interaction ${index + 1} (${details.model_name})`}
                      color="info"
                    />
                  </Box>
                );
              })}
            
            {/* Show indicator if there are more interactions */}
            {llmInteractions.length > maxInteractionsToShow && (
              <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic', mt: 0.5 }}>
                ... and {llmInteractions.length - maxInteractionsToShow} more interactions
              </Typography>
            )}
          </Stack>
        </Box>
      )}
    </Stack>
  );

  // Render based on variant
  switch (variant) {
    case 'card':
      return (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              Token Usage
              {hasSessionTokens && sessionTokens.total_tokens && sessionTokens.total_tokens > 2000 && (
                <Typography 
                  variant="caption" 
                  sx={{ 
                    bgcolor: 'warning.light', 
                    color: 'warning.contrastText',
                    px: 1, 
                    py: 0.25, 
                    borderRadius: 1,
                    fontWeight: 600,
                    fontSize: '0.7rem'
                  }}
                >
                  HIGH USAGE
                </Typography>
              )}
            </Typography>
            {renderContent()}
          </CardContent>
        </Card>
      );

    case 'inline':
      return (
        <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1, border: 1, borderColor: 'divider' }}>
          {renderContent()}
        </Box>
      );

    case 'minimal':
    default:
      return <Box>{renderContent()}</Box>;
  }
}

export default memo(MultiLevelTokenDisplay);
