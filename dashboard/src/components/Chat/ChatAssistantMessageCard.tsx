import { useMemo } from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { Psychology } from '@mui/icons-material';
import StageConversationCard from '../StageConversationCard';
import { parseStageConversation } from '../../utils/conversationParser';
import type { StageExecution } from '../../types';

interface ChatAssistantMessageCardProps {
  execution: StageExecution;
}

function formatTimestamp(timestampUs: number | null): string {
  if (!timestampUs) return '';
  
  const date = new Date(timestampUs / 1000);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
  
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
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
            TARSy • {formatTimestamp(execution.started_at_us)}
          </Typography>
        </Box>
        
        {/* Reuse existing stage conversation rendering */}
        <StageConversationCard stage={conversationStage} stageIndex={0} />
      </Paper>
    </Box>
  );
}

