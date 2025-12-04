import { memo } from 'react';
import { Box, Typography, Divider, Chip, alpha, IconButton } from '@mui/material';
import { Flag, AccountCircle, ExpandMore, ExpandLess } from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import ToolCallBox from './ToolCallBox';
import NativeToolsBox from './NativeToolsBox';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import { 
  hasMarkdownSyntax, 
  finalAnswerMarkdownComponents, 
  thoughtMarkdownComponents 
} from '../utils/markdownComponents';

interface ChatFlowItemProps {
  item: ChatFlowItemData;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

/**
 * ChatFlowItem Component
 * Renders different types of chat flow items in a compact transcript style
 * Memoized to prevent unnecessary re-renders
 */
function ChatFlowItem({ item, isCollapsed = false, onToggleCollapse }: ChatFlowItemProps) {
  // Render stage start separator with collapse/expand control
  if (item.type === 'stage_start') {
    return (
      <Box sx={{ my: 2.5 }}>
        <Divider sx={{ mb: 1, opacity: isCollapsed ? 0.6 : 1, transition: 'opacity 0.2s ease-in-out' }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              cursor: onToggleCollapse ? 'pointer' : 'default',
              borderRadius: 1,
              px: 1,
              py: 0.5,
              transition: 'all 0.2s ease-in-out',
              '&:hover': onToggleCollapse ? {
                backgroundColor: alpha('#1976d2', 0.08),
                '& .MuiChip-root': {
                  backgroundColor: alpha('#1976d2', 0.12),
                  borderColor: '#1976d2',
                }
              } : {}
            }}
            onClick={onToggleCollapse}
            role={onToggleCollapse ? 'button' : undefined}
            tabIndex={onToggleCollapse ? 0 : undefined}
            onKeyDown={onToggleCollapse ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onToggleCollapse();
              }
            } : undefined}
            aria-label={onToggleCollapse ? (isCollapsed ? 'Expand stage' : 'Collapse stage') : undefined}
          >
            <Chip
              icon={<Flag />}
              label={`Stage: ${item.stageName}`}
              color="primary"
              variant="outlined"
              size="small"
              sx={{
                fontSize: '0.8rem',
                fontWeight: 600,
                transition: 'all 0.2s ease-in-out',
                opacity: isCollapsed ? 0.8 : 1
              }}
            />
            {onToggleCollapse && (
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation(); // Prevent double-triggering
                  onToggleCollapse();
                }}
                sx={{
                  padding: 0.75,
                  backgroundColor: isCollapsed ? alpha('#666', 0.1) : alpha('#1976d2', 0.1),
                  border: '1px solid',
                  borderColor: isCollapsed ? alpha('#666', 0.2) : alpha('#1976d2', 0.2),
                  color: isCollapsed ? '#666' : 'inherit',
                  '&:hover': {
                    backgroundColor: isCollapsed ? '#666' : '#1976d2',
                    color: 'white',
                    transform: 'scale(1.1)'
                  },
                  transition: 'all 0.2s ease-in-out'
                }}
                aria-label={isCollapsed ? 'Expand stage' : 'Collapse stage'}
              >
                {isCollapsed ? <ExpandMore fontSize="small" /> : <ExpandLess fontSize="small" />}
              </IconButton>
            )}
          </Box>
        </Divider>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            display: 'block',
            textAlign: 'center',
            fontStyle: 'italic',
            fontSize: '0.75rem',
            opacity: isCollapsed ? 0.7 : 1,
            transition: 'opacity 0.2s ease-in-out'
          }}
        >
          Agent: {item.stageAgent}
        </Typography>
      </Box>
    );
  }

  // Render thought - with hybrid markdown support (only parse markdown when detected)
  if (item.type === 'thought') {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 1.5, display: 'flex', gap: 1.5 }}>
        <Typography
          variant="body2"
          sx={{
            fontSize: '1.1rem',
            lineHeight: 1,
            flexShrink: 0,
            mt: 0.25
          }}
        >
          💭
        </Typography>
        {hasMarkdown ? (
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <ReactMarkdown
              components={thoughtMarkdownComponents}
              skipHtml
            >
              {item.content}
            </ReactMarkdown>
          </Box>
        ) : (
          <Typography
            variant="body1"
            sx={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: 1.7,
              fontSize: '1rem',
              color: 'text.primary'
            }}
          >
            {item.content}
          </Typography>
        )}
      </Box>
    );
  }

  // Render native thinking (Gemini 3.0+ native thinking mode)
  // Distinct from ReAct thoughts - this is the model's internal reasoning process
  if (item.type === 'native_thinking') {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 1.5, display: 'flex', gap: 1.5 }}>
        <Typography
          variant="body2"
          sx={{
            fontSize: '1.1rem',
            lineHeight: 1,
            flexShrink: 0,
            mt: 0.25
          }}
        >
          🧠
        </Typography>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              fontSize: '0.65rem',
              color: 'info.main',
              display: 'block',
              mb: 0.5
            }}
          >
            Native Thinking
          </Typography>
          {hasMarkdown ? (
            <Box sx={{ 
              '& p, & li': { 
                color: 'text.secondary',
                fontStyle: 'italic'
              }
            }}>
              <ReactMarkdown
                components={thoughtMarkdownComponents}
                skipHtml
              >
                {item.content}
              </ReactMarkdown>
            </Box>
          ) : (
            <Typography
              variant="body1"
              sx={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.7,
                fontSize: '1rem',
                color: 'text.secondary',
                fontStyle: 'italic'
              }}
            >
              {item.content}
            </Typography>
          )}
        </Box>
      </Box>
    );
  }

  // Render final answer - emphasized text with emoji and markdown support
  if (item.type === 'final_answer') {
    return (
      <Box sx={{ mb: 2, mt: 3 }}>
        <Box sx={{ display: 'flex', gap: 1.5, mb: 1 }}>
          <Typography
            variant="body2"
            sx={{
              fontSize: '1.1rem',
              lineHeight: 1,
              flexShrink: 0
            }}
          >
            🎯
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              fontSize: '0.75rem',
              color: '#2e7d32', // Muted green instead of bright success color
              mt: 0.25
            }}
          >
            Final Answer
          </Typography>
        </Box>
        <Box sx={{ pl: 3.5 }}>
          <ReactMarkdown
            urlTransform={defaultUrlTransform}
            components={finalAnswerMarkdownComponents}
          >
            {item.content || ''}
          </ReactMarkdown>
        </Box>
      </Box>
    );
  }

  // Render tool call - indented expandable box
  if (item.type === 'tool_call') {
    return (
      <ToolCallBox
        toolName={item.toolName || 'unknown'}
        toolArguments={item.toolArguments || {}}
        toolResult={item.toolResult}
        serverName={item.serverName || 'unknown'}
        success={item.success !== false}
        errorMessage={item.errorMessage}
        duration_ms={item.duration_ms}
      />
    );
  }

  if (item.type === 'user_message') {
    return (
      <Box sx={{ mb: 1.5, position: 'relative' }}>
        {/* User avatar icon - positioned absolutely */}
        <Box
          sx={{
            position: 'absolute',
            left: 0,
            top: 8,
            width: 28,
            height: 28,
            borderRadius: '50%',
            bgcolor: 'primary.main',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1
          }}
        >
          <AccountCircle sx={{ fontSize: 28, color: 'white' }} />
        </Box>

        {/* Message content box - aligned with tool call boxes */}
        <Box
          sx={(theme) => ({
            ml: 4,
            my: 1,
            mr: 1,
            p: 1.5,
            borderRadius: 1.5,
            bgcolor: 'grey.50',
            border: '1px solid',
            borderColor: alpha(theme.palette.grey[300], 0.4),
          })}
        >
          {/* Author name inside the box */}
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              fontSize: '0.7rem',
              color: 'primary.main',
              mb: 0.75,
              display: 'block',
              textTransform: 'uppercase',
              letterSpacing: 0.3
            }}
          >
            {item.author}
          </Typography>

          <Typography
            variant="body1"
            sx={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: 1.6,
              fontSize: '0.95rem',
              color: 'text.primary'
            }}
          >
            {item.content}
          </Typography>
        </Box>
      </Box>
    );
  }

  // Render summarization - with hybrid markdown support (maintains amber styling)
  if (item.type === 'summarization') {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 1.5 }}>
        {/* Header with amber styling */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 0.5 }}>
          <Typography
            variant="body2"
            sx={{
              fontSize: '1.1rem',
              lineHeight: 1,
              flexShrink: 0
            }}
          >
            📋
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              fontSize: '0.75rem',
              color: 'rgba(237, 108, 2, 0.9)', // Subtle amber/orange
              mt: 0.25
            }}
          >
            Tool Result Summary
          </Typography>
        </Box>
        {/* Content with subtle left border and dimmed text */}
        <Box 
          sx={{ 
            pl: 3.5,
            ml: 3.5,
            py: 0.5,
            borderLeft: '2px solid rgba(237, 108, 2, 0.2)' // Subtle amber left border
          }}
        >
          {hasMarkdown ? (
            <Box sx={{ 
              '& p': { color: 'text.secondary' }, // Apply dimmed color to markdown paragraphs
              '& li': { color: 'text.secondary' }  // Apply dimmed color to list items
            }}>
              <ReactMarkdown
                components={thoughtMarkdownComponents}
                skipHtml
              >
                {item.content || ''}
              </ReactMarkdown>
            </Box>
          ) : (
            <Typography
              variant="body1"
              sx={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.7,
                fontSize: '1rem',
                color: 'text.secondary' // Slightly dimmed to differentiate from thoughts
              }}
            >
              {item.content || ''}
            </Typography>
          )}
        </Box>
      </Box>
    );
  }

  // Render native tool usage indicators
  if (item.type === 'native_tool_usage' && item.nativeToolsUsage) {
    return <NativeToolsBox usage={item.nativeToolsUsage} />;
  }

  return null;
}

// Export memoized component using default shallow comparison
// This automatically compares all props (content, timestamp, type, toolName, toolArguments,
// toolResult, serverName, success, errorMessage, duration_ms, etc.)
export default memo(ChatFlowItem);

