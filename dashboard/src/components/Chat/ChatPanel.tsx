import { useState } from 'react';
import { Box, Paper, IconButton, Collapse, Typography, Alert, CircularProgress, alpha } from '@mui/material';
import { Chat as ChatIcon, Close, ExpandMore } from '@mui/icons-material';
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
  onExpandChange?: (expanded: boolean) => void; // Notify parent when expanded state changes
}

export default function ChatPanel({
  sessionId,
  chat,
  isAvailable,
  onCreateChat,
  onSendMessage,
  loading,
  error,
  onExpandChange
}: ChatPanelProps) {
  const [expanded, setExpanded] = useState(false); // Start collapsed
  const [closed, setClosed] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [isCreatingChat, setIsCreatingChat] = useState(false);

  if (closed) {
    return null;
  }

  // Handle expansion with chat creation
  const handleExpand = async () => {
    if (expanded) {
      // Just collapse
      setExpanded(false);
      onExpandChange?.(false);
      return;
    }

    // Expanding - create chat if needed
    if (!chat && isAvailable && !isCreatingChat) {
      setIsCreatingChat(true);
      try {
        await onCreateChat();
        setExpanded(true);
        onExpandChange?.(true);
      } catch (err) {
        // Error handled below, don't expand
        setSendError('Failed to create chat');
      } finally {
        setIsCreatingChat(false);
      }
    } else if (chat) {
      // Chat already exists, just expand
      setExpanded(true);
      onExpandChange?.(true);
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

  // Unified collapsible panel (works for both states: before and after chat creation)
  return (
    <Paper 
      elevation={expanded ? 3 : 1}
      sx={(theme) => ({ 
        mt: 3,
        overflow: 'hidden',
        transition: 'all 0.3s ease-in-out',
        border: `2px solid ${expanded ? theme.palette.primary.main : 'transparent'}`,
        '&:hover': {
          borderColor: !expanded ? alpha(theme.palette.primary.main, 0.3) : theme.palette.primary.main,
        }
      })}
    >
      {/* Collapsible Header - Clickable to expand/collapse */}
      <Box
        onClick={handleExpand}
        sx={(theme) => ({
          p: 2.5,
          display: 'flex',
          alignItems: 'center',
          cursor: 'pointer',
          background: expanded 
            ? `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.08)} 0%, ${alpha(theme.palette.primary.light, 0.12)} 100%)`
            : `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.03)} 0%, ${alpha(theme.palette.primary.light, 0.06)} 100%)`,
          transition: 'all 0.3s ease-in-out',
          borderBottom: expanded ? `1px solid ${theme.palette.divider}` : 'none',
          '&:hover': {
            background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.12)} 0%, ${alpha(theme.palette.primary.light, 0.16)} 100%)`,
          }
        })}
      >
        {/* Chat Icon */}
        <Box
          sx={(theme) => ({
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 48,
            height: 48,
            borderRadius: '12px',
            background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.primary.dark} 100%)`,
            mr: 2,
            transition: 'transform 0.3s ease-in-out',
            transform: expanded ? 'scale(1.05)' : 'scale(1)',
          })}
        >
          {isCreatingChat ? (
            <CircularProgress size={24} sx={{ color: 'white' }} />
          ) : (
            <ChatIcon sx={{ fontSize: 28, color: 'white' }} />
          )}
        </Box>
        
        {/* Text Content */}
        <Box sx={{ flex: 1 }}>
          <Typography 
            variant="h6" 
            sx={{ 
              fontWeight: 600,
              mb: 0.5,
              color: 'text.primary'
            }}
          >
            {chat ? 'Follow-up Chat' : 'Have follow-up questions?'}
          </Typography>
          <Typography 
            variant="body2" 
            sx={{ 
              color: 'text.secondary',
              fontSize: '0.9rem'
            }}
          >
            {isCreatingChat 
              ? 'Creating chat...'
              : expanded 
                ? 'Ask questions about this analysis' 
                : 'Click to expand and continue the investigation'}
          </Typography>
        </Box>
        
        {/* Expand/Collapse Icon */}
        <IconButton 
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            handleExpand();
          }}
          disabled={isCreatingChat}
          sx={{ 
            transition: 'transform 0.3s ease-in-out',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            mr: 1
          }}
        >
          <ExpandMore />
        </IconButton>
        
        {/* Close Button */}
        <IconButton 
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            setClosed(true);
          }}
        >
          <Close />
        </IconButton>
      </Box>

      {/* Error Display (shown when collapsed if there's an error) */}
      {!expanded && (error || sendError) && (
        <Alert severity="error" sx={{ m: 2 }}>
          <Typography variant="body2">
            {error || sendError}
          </Typography>
        </Alert>
      )}
      
      {/* Chat Content - Only shown when chat exists and is expanded */}
      <Collapse in={expanded && chat !== null} timeout={400}>
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
          {chat && (
            <>
              <ChatMessageList sessionId={sessionId} chatId={chat.chat_id} />
              <ChatInput onSendMessage={handleSendMessage} disabled={loading} />
            </>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
}

