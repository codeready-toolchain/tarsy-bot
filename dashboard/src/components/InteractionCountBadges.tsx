import { Box, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import type { StageExecution } from '../types';

interface InteractionCountBadgesProps {
  stage: StageExecution;
}

/**
 * Shared component for displaying LLM/MCP interaction count badges
 * Extracted to reduce duplication between timeline components
 */
function InteractionCountBadges({ stage }: InteractionCountBadgesProps) {
  if (stage.llm_interaction_count === 0 && stage.mcp_communication_count === 0) {
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
    </Box>
  );
}

export default InteractionCountBadges;
