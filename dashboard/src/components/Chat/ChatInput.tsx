import { useState, type KeyboardEvent } from 'react';
import { Box, TextField, IconButton, CircularProgress, Tooltip } from '@mui/material';
import { Send } from '@mui/icons-material';

interface ChatInputProps {
  onSendMessage: (content: string) => Promise<void>;
  disabled?: boolean;
}

export default function ChatInput({ onSendMessage, disabled }: ChatInputProps) {
  const [content, setContent] = useState('');
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!content.trim() || sending) return;

    setSending(true);
    try {
      await onSendMessage(content.trim());
      setContent('');
    } catch (error) {
      console.error('Failed to send message:', error);
      // Error is handled by parent component
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isDisabled = disabled || sending;
  const canSend = content.trim() && !isDisabled;

  return (
    <Box sx={{ 
      p: { xs: 1, sm: 2 }, 
      borderTop: 1, 
      borderColor: 'divider', 
      display: 'flex', 
      gap: 1 
    }}>
      <TextField
        fullWidth
        multiline
        maxRows={4}
        placeholder="Type your question... (Shift+Enter for new line)"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isDisabled}
        size="small"
        sx={{
          '& .MuiOutlinedInput-root': {
            fontSize: { xs: '0.875rem', sm: '1rem' },
          }
        }}
      />
      <Tooltip title={sending ? 'Sending...' : 'Send message (Enter)'}>
        <span>
          <IconButton
            color="primary"
            onClick={handleSend}
            disabled={!canSend}
            sx={{
              transition: 'all 0.2s',
              '&:hover': {
                transform: 'scale(1.1)',
              }
            }}
          >
            {sending ? <CircularProgress size={24} /> : <Send />}
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );
}

