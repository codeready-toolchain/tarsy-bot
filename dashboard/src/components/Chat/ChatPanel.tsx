import { useState } from 'react';
import { Box, Paper, Button, IconButton, Collapse, Typography, Alert, CircularProgress } from '@mui/material';
import { Chat as ChatIcon, Close, ExpandLess, ExpandMore } from '@mui/icons-material';
import ChatMessageList from './ChatMessageList';
import ChatInput from './ChatInput';
import type { Chat } from '../../types';

interface ChatPanelProps {
  sessionId: string;
  chat: Chat | null;
  isAvailable: boolean;
  onCreateChat: () => Promise<void>;
  onSendMessage: (content: string) => Promise<void>;
  loading?: boolean;
  error?: string | null;
}

export default function ChatPanel({
  sessionId,
  chat,
  isAvailable,
  onCreateChat,
  onSendMessage,
  loading,
  error
}: ChatPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [closed, setClosed] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  if (closed) {
    return null;
  }

  // Handle create chat with error handling
  const handleCreateChat = async () => {
    try {
      setSendError(null);
      await onCreateChat();
    } catch (err: any) {
      setSendError(err.message || 'Failed to create chat');
    }
  };

  // Handle send message with error handling
  const handleSendMessage = async (content: string) => {
    try {
      setSendError(null);
      await onSendMessage(content);
    } catch (err: any) {
      setSendError(err.message || 'Failed to send message');
    }
  };

  // Not started state
  if (!chat && isAvailable) {
    return (
      <Paper sx={{ p: 3, mt: 3 }}>
        <Box sx={{ textAlign: 'center' }}>
          <ChatIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            Have follow-up questions?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Continue the investigation with AI assistance
          </Typography>
          
          {(error || sendError) && (
            <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>
              <Typography variant="body2">
                {error || sendError}
              </Typography>
            </Alert>
          )}
          
          <Button
            variant="contained"
            startIcon={loading ? <CircularProgress size={20} /> : <ChatIcon />}
            onClick={handleCreateChat}
            disabled={loading}
          >
            {loading ? 'Creating Chat...' : 'Start Follow-up Chat'}
          </Button>
        </Box>
      </Paper>
    );
  }

  // Chat active state
  if (chat) {
    return (
      <Paper sx={{ mt: 3 }}>
        <Box
          sx={{
            p: 2,
            display: 'flex',
            alignItems: 'center',
            borderBottom: expanded ? 1 : 0,
            borderColor: 'divider',
          }}
        >
          <ChatIcon sx={{ mr: 1 }} />
          <Typography variant="h6" sx={{ flex: 1 }}>
            Follow-up Chat
          </Typography>
          <IconButton onClick={() => setExpanded(!expanded)} size="small">
            {expanded ? <ExpandLess /> : <ExpandMore />}
          </IconButton>
          <IconButton onClick={() => setClosed(true)} size="small">
            <Close />
          </IconButton>
        </Box>
        
        <Collapse in={expanded}>
          <Box sx={{ 
            maxHeight: { xs: '400px', sm: '500px', md: '600px' }, 
            display: 'flex', 
            flexDirection: 'column' 
          }}>
            {sendError && (
              <Alert 
                severity="error" 
                sx={{ m: 2, mb: 0 }}
                onClose={() => setSendError(null)}
              >
                <Typography variant="body2">{sendError}</Typography>
              </Alert>
            )}
            <ChatMessageList sessionId={sessionId} chatId={chat.chat_id} />
            <ChatInput onSendMessage={handleSendMessage} disabled={loading} />
          </Box>
        </Collapse>
      </Paper>
    );
  }

  return null;
}

