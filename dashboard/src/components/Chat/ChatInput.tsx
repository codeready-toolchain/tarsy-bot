import { useState } from 'react';
import { Box, TextField, IconButton, CircularProgress, Tooltip, Typography, alpha } from '@mui/material';
import { Send } from '@mui/icons-material';

interface ChatInputProps {
  onSendMessage: (content: string) => Promise<void>;
  disabled?: boolean;
  sendingMessage?: boolean;
}

export default function ChatInput({ onSendMessage, disabled, sendingMessage = false }: ChatInputProps) {
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

  const isDisabled = disabled || sending || sendingMessage;
  const canSend = content.trim() && !isDisabled;

  return (
    <Box>
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
          minRows={2}
          maxRows={8}
          placeholder="Type your question... (press Enter for new line)"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={isDisabled}
          size="small"
          sx={{
            '& .MuiOutlinedInput-root': {
              fontSize: { xs: '0.875rem', sm: '1rem' },
              transition: 'all 0.3s ease',
              ...(sendingMessage && {
                opacity: 0.7,
                backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.02),
              })
            }
          }}
        />
        <Tooltip title={sending || sendingMessage ? 'Sending...' : 'Send message'}>
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
              {(sending || sendingMessage) ? <CircularProgress size={24} /> : <Send />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>
      
      {/* Subtle status message when processing */}
      {sendingMessage && (
        <Box sx={{ 
          px: { xs: 1, sm: 2 }, 
          pb: 1,
          pt: 0
        }}>
          <Typography 
            variant="caption" 
            sx={{ 
              color: 'primary.main',
              fontSize: '0.75rem',
              fontStyle: 'italic',
              opacity: 0.7
            }}
          >
            Starting AI processing...
          </Typography>
        </Box>
      )}
    </Box>
  );
}

