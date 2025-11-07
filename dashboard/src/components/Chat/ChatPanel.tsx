import { useState, useEffect } from 'react';
import { Box, Paper, IconButton, Collapse, Typography, Alert, CircularProgress, alpha } from '@mui/material';
import { AccountCircle, ExpandMore } from '@mui/icons-material';
import ChatInput from './ChatInput';
import type { Chat } from '../../types';

interface ChatPanelProps {
  chat: Chat | null;
  isAvailable: boolean;
  onCreateChat: () => Promise<void>;
  onSendMessage: (content: string) => Promise<void>;
  onCancelExecution?: () => Promise<void>;
  loading?: boolean;
  error?: string | null;
  sendingMessage?: boolean; // Track when a message is actively being sent
  chatStageInProgress?: boolean; // Track when AI is actively processing the chat
  canCancel?: boolean;
  canceling?: boolean;
  forceExpand?: boolean; // External trigger to expand the chat panel
  onCollapseAnalysis?: () => void; // Callback to collapse Final Analysis when chat is expanded
}

export default function ChatPanel({
  chat,
  isAvailable,
  onCreateChat,
  onSendMessage,
  onCancelExecution,
  loading,
  error,
  sendingMessage = false,
  chatStageInProgress = false,
  canCancel = false,
  canceling = false,
  forceExpand = false,
  onCollapseAnalysis
}: ChatPanelProps) {
  const [expanded, setExpanded] = useState(false); // Start collapsed
  const [sendError, setSendError] = useState<string | null>(null);
  const [isCreatingChat, setIsCreatingChat] = useState(false);

  // Handle external expansion trigger (e.g., from "Jump to Chat" button)
  useEffect(() => {
    if (forceExpand && !expanded) {
      void handleExpand();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceExpand]);

  // Handle expansion with chat creation
  const handleExpand = async () => {
    if (expanded) {
      // Just collapse chat
      setExpanded(false);
      return;
    }

    // Collapse Final Analysis when expanding chat
    onCollapseAnalysis?.();

    // Expanding chat - wait a bit for Final Analysis to start collapsing
    await new Promise(resolve => setTimeout(resolve, 150));

    // Now expand chat (create if needed)
    if (!chat && isAvailable && !isCreatingChat) {
      setIsCreatingChat(true);
      try {
        await onCreateChat();
        setExpanded(true);
        // Scroll to bottom after expansion
        setTimeout(() => {
          window.scrollTo({ 
            top: document.documentElement.scrollHeight, 
            behavior: 'smooth' 
          });
        }, 500);
      } catch (err) {
        // Error handled below, don't expand
        setSendError('Failed to create chat');
      } finally {
        setIsCreatingChat(false);
      }
    } else if (chat) {
      // Chat already exists, just expand
      setExpanded(true);
      // Scroll to bottom after expansion
      setTimeout(() => {
        window.scrollTo({ 
          top: document.documentElement.scrollHeight, 
          behavior: 'smooth' 
        });
      }, 500);
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
          bgcolor: expanded 
            ? alpha(theme.palette.primary.main, 0.06) 
            : alpha(theme.palette.primary.main, 0.03),
          transition: 'all 0.3s ease-in-out',
          borderBottom: expanded ? `1px solid ${theme.palette.divider}` : 'none',
          '&:hover': {
            bgcolor: alpha(theme.palette.primary.main, 0.08),
          }
        })}
      >
        {/* Chat Icon - Simple circle like user messages */}
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: '50%',
            bgcolor: 'primary.main',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mr: 2,
            flexShrink: 0,
          }}
        >
          {isCreatingChat ? (
            <CircularProgress size={24} sx={{ color: 'white' }} />
          ) : (
            <AccountCircle sx={{ fontSize: 40, color: 'white' }} />
          )}
        </Box>
        
        {/* Text Content */}
        <Box sx={{ flex: 1 }}>
          <Typography 
            variant="h6" 
            sx={{ 
              fontWeight: 600,
              mb: 0.3,
              color: 'text.primary',
              fontSize: '1rem'
            }}
          >
            {chat ? 'Follow-up Chat' : 'Have follow-up questions?'}
          </Typography>
          <Typography 
            variant="body2" 
            sx={{ 
              color: 'text.secondary',
              fontSize: '0.85rem'
            }}
          >
            {isCreatingChat 
              ? 'Creating chat...'
              : expanded 
                ? 'Ask questions about this analysis' 
                : 'Click to expand and continue the conversation'}
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
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)'
          }}
        >
          <ExpandMore />
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
      
      {/* Chat Input - Only shown when chat exists and is expanded */}
      {/* Note: Chat messages are rendered in ConversationTimeline above, not here */}
      <Collapse in={expanded && chat !== null} timeout={400}>
        <Box sx={{ 
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
          
          {/* Simple static indicator when processing - no animation */}
          {(sendingMessage || chatStageInProgress) && (
            <Box 
              sx={(theme) => ({ 
                height: 3,
                width: '100%',
                bgcolor: alpha(theme.palette.primary.main, 0.15),
              })}
            />
          )}
          
          {chat && (
            <ChatInput 
              onSendMessage={handleSendMessage}
              onCancelExecution={onCancelExecution}
              disabled={loading || sendingMessage || chatStageInProgress}
              sendingMessage={sendingMessage || chatStageInProgress}
              canCancel={canCancel}
              canceling={canceling}
            />
          )}
        </Box>
      </Collapse>
    </Paper>
  );
}

