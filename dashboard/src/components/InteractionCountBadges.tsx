import { Box, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import TokenUsageDisplay from './TokenUsageDisplay';
import type { StageExecution } from '../types';

interface InteractionCountBadgesProps {
  stage: StageExecution;
}

/**
 * Shared component for displaying LLM/MCP interaction count badges
 * Extracted to reduce duplication between timeline components
 */
function InteractionCountBadges({ stage }: InteractionCountBadgesProps) {
  const hasTokens =
    stage.stage_total_tokens != null ||
    stage.stage_input_tokens != null ||
    stage.stage_output_tokens != null;
  if (stage.llm_interaction_count === 0 &&
      stage.mcp_communication_count === 0 &&
      !hasTokens) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', gap: 0.5 }}>
      {stage.llm_interaction_count > 0 && (
        <Box sx={(theme) => ({ 
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          px: 0.75,
          py: 0.25,
          backgroundColor: alpha(theme.palette.primary.main, 0.08),
          borderRadius: '12px',
          border: '1px solid',
          borderColor: alpha(theme.palette.primary.main, 0.28)
        })}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'primary.main', fontSize: '0.7rem' }}>
            🧠 {stage.llm_interaction_count}
          </Typography>
          <Typography variant="caption" color="primary.main" sx={{ fontSize: '0.65rem' }}>
            LLM
          </Typography>
        </Box>
      )}
      
      {stage.mcp_communication_count > 0 && (
        <Box sx={(theme) => ({ 
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          px: 0.75,
          py: 0.25,
          backgroundColor: alpha(theme.palette.secondary.main, 0.08),
          borderRadius: '12px',
          border: '1px solid',
          borderColor: alpha(theme.palette.secondary.main, 0.28)
        })}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'secondary.main', fontSize: '0.7rem' }}>
            🔧 {stage.mcp_communication_count}
          </Typography>
          <Typography variant="caption" color="secondary.main" sx={{ fontSize: '0.65rem' }}>
            MCP
          </Typography>
        </Box>
      )}
      
      {/* Token usage display */}
      {hasTokens && (
        <Box sx={(theme) => ({ 
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          px: 0.75,
          py: 0.25,
          backgroundColor: alpha(theme.palette.success.main, 0.08),
          borderRadius: '12px',
          border: '1px solid',
          borderColor: alpha(theme.palette.success.main, 0.28)
        })}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'success.main', fontSize: '0.65rem' }}>
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
  );
}

export default InteractionCountBadges;
