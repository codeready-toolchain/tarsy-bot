import { useMemo } from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { Psychology } from '@mui/icons-material';
import StageConversationCard from '../StageConversationCard';
import { parseStageConversation } from '../../utils/conversationParser';
import type { StageExecution } from '../../types';
import { formatTimestamp } from '../../utils/timestamp';

interface ChatAssistantMessageCardProps {
  execution: StageExecution;
}

export default function ChatAssistantMessageCard({ execution }: ChatAssistantMessageCardProps) {
  // Parse the stage execution into conversation format
  const conversationStage = useMemo(() => parseStageConversation(execution), [execution]);

  return (
    <Box sx={{ mb: 2 }}>
      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Psychology sx={{ fontSize: 20, mr: 0.5, color: 'primary.main' }} />
          <Typography variant="caption" color="text.secondary">
            TARSy • {execution.started_at_us ? formatTimestamp(execution.started_at_us) : ''}
          </Typography>
        </Box>
        
        {/* Reuse existing stage conversation rendering */}
        <StageConversationCard stage={conversationStage} stageIndex={0} />
      </Paper>
    </Box>
  );
}

