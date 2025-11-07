import { Box, Paper, Typography } from '@mui/material';
import { Person } from '@mui/icons-material';
import type { ChatUserMessage } from '../../types';
import { formatTimestamp } from '../../utils/timestamp';

interface ChatUserMessageCardProps {
  message: ChatUserMessage;
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

