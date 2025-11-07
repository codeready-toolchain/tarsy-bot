import { Box, Paper, Typography } from '@mui/material';
import { Person } from '@mui/icons-material';
import type { ChatUserMessage } from '../../types';

interface ChatUserMessageCardProps {
  message: ChatUserMessage;
}

function formatTimestamp(timestampUs: number): string {
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

export default function ChatUserMessageCard({ message }: ChatUserMessageCardProps) {
  return (
    <Box sx={{ mb: 2, display: 'flex', justifyContent: 'flex-end' }}>
      <Paper
        sx={{
          p: 2,
          maxWidth: '70%',
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          <Person sx={{ fontSize: 16, mr: 0.5 }} />
          <Typography variant="caption">
            {message.author} • {formatTimestamp(message.created_at_us)}
          </Typography>
        </Box>
        <Typography variant="body1">{message.content}</Typography>
      </Paper>
    </Box>
  );
}

