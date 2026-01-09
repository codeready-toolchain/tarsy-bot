import { memo } from 'react';
import { Box, Typography, Divider, Chip, alpha, IconButton, Alert, Collapse } from '@mui/material';
import { Flag, AccountCircle, ExpandMore, ExpandLess } from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import ToolCallBox from './ToolCallBox';
import NativeToolsBox from './NativeToolsBox';
import ContentPreviewTooltip from './ContentPreviewTooltip';
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
  // Auto-collapse props
  isAutoCollapsed?: boolean;
  onToggleAutoCollapse?: () => void;
  expandAll?: boolean;
  // Whether this item type is collapsible at all (determines if clickable)
  isCollapsible?: boolean; // eslint-disable-line @typescript-eslint/no-unused-vars
}

/**
 * ChatFlowItem Component
 * Renders different types of chat flow items in a compact transcript style
 * Memoized to prevent unnecessary re-renders
 */
function ChatFlowItem({ 
  item, 
  isCollapsed = false, 
  onToggleCollapse,
  isAutoCollapsed = false,
  onToggleAutoCollapse,
  expandAll = false,
  isCollapsible = false // eslint-disable-line @typescript-eslint/no-unused-vars
}: ChatFlowItemProps) {
  // Determine if we should show collapsed state (header only)
  const shouldShowCollapsed = isAutoCollapsed && !expandAll;
  
  // Render stage start separator with collapse/expand control
  if (item.type === 'stage_start') {
    const isFailed = item.stageStatus === 'failed';
    const hasError = isFailed && item.stageErrorMessage;
    
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
                backgroundColor: alpha(isFailed ? '#d32f2f' : '#1976d2', 0.08),
                '& .MuiChip-root': {
                  backgroundColor: alpha(isFailed ? '#d32f2f' : '#1976d2', 0.12),
                  borderColor: isFailed ? '#d32f2f' : '#1976d2',
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
              color={isFailed ? 'error' : 'primary'}
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
                  backgroundColor: isCollapsed ? alpha('#666', 0.1) : alpha(isFailed ? '#d32f2f' : '#1976d2', 0.1),
                  border: '1px solid',
                  borderColor: isCollapsed ? alpha('#666', 0.2) : alpha(isFailed ? '#d32f2f' : '#1976d2', 0.2),
                  color: isCollapsed ? '#666' : 'inherit',
                  '&:hover': {
                    backgroundColor: isCollapsed ? '#666' : (isFailed ? '#d32f2f' : '#1976d2'),
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
        
        {/* Show error message for failed stages (not collapsed) */}
        {hasError && !isCollapsed && (
          <Alert severity="error" sx={{ mt: 2, mx: 2 }}>
            <Typography variant="body2">
              <strong>Stage Failed:</strong> {item.stageErrorMessage}
            </Typography>
          </Alert>
        )}
      </Box>
    );
  }

  // Render thought - with hybrid markdown support (only parse markdown when detected)
  if (item.type === 'thought') {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && {
            animation: 'fadeCollapse 0.6s ease-out',
            '@keyframes fadeCollapse': {
              '0%': { opacity: 1 },
              '50%': { opacity: 0.3 },
              '100%': { opacity: 1 },
            },
          })
        }}
      >
        {/* Emoji with tooltip when collapsed */}
        {shouldShowCollapsed ? (
          <ContentPreviewTooltip content={item.content || ''} type="thought">
            <Box
              sx={{
                fontSize: '1.1rem',
                lineHeight: '1.5',
                flexShrink: 0,
                cursor: 'help',
                display: 'flex',
                alignItems: 'center',
                height: '1.5rem'
              }}
            >
              💭
            </Box>
          </ContentPreviewTooltip>
        ) : (
          <Box
            sx={{
              fontSize: '1.1rem',
              lineHeight: '1.5',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              height: '1.5rem'
            }}
          >
            💭
          </Box>
        )}
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Header - always visible, changes ">" when collapsed, "^" when expanded */}
          <Box 
            sx={{ 
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              cursor: onToggleAutoCollapse ? 'pointer' : 'default',
              px: shouldShowCollapsed ? 1 : 0,
              py: 0.5,
              mx: shouldShowCollapsed ? -1 : 0,
              borderRadius: 1,
              transition: 'background-color 0.2s ease',
              '&:hover': onToggleAutoCollapse ? {
                bgcolor: 'action.hover'
              } : {}
            }}
            onClick={onToggleAutoCollapse}
          >
            <Typography
              variant="caption"
              sx={{
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
                fontSize: '0.75rem',
                color: 'info.main'
              }}
            >
              THOUGHT {shouldShowCollapsed ? '>' : '^'}
            </Typography>
            {shouldShowCollapsed && (
              <ExpandMore fontSize="small" sx={{ ml: 'auto', opacity: 0.6 }} />
            )}
          </Box>
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              {hasMarkdown ? (
                <Box sx={{ color: 'text.primary' }}>
                  <ReactMarkdown
                    components={thoughtMarkdownComponents}
                    remarkPlugins={[remarkBreaks]}
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
                    color: 'text.primary'
                  }}
                >
                  {item.content}
                </Typography>
              )}
              {/* Collapse button at bottom */}
              {onToggleAutoCollapse && (
                <Box
                  onClick={onToggleAutoCollapse}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    mt: 0.5,
                    cursor: 'pointer',
                    opacity: 0.6,
                    '&:hover': {
                      opacity: 1
                    }
                  }}
                >
                  <ExpandLess fontSize="small" />
                  <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                    Collapse
                  </Typography>
                </Box>
              )}
            </Box>
          </Collapse>
        </Box>
      </Box>
    );
  }

  // Render native thinking (Gemini 3.0+ native thinking mode)
  if (item.type === 'native_thinking') {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && {
            animation: 'fadeCollapse 0.6s ease-out',
            '@keyframes fadeCollapse': {
              '0%': { opacity: 1 },
              '50%': { opacity: 0.3 },
              '100%': { opacity: 1 },
            },
          })
        }}
      >
        {/* Emoji with tooltip when collapsed */}
        {shouldShowCollapsed ? (
          <ContentPreviewTooltip content={item.content || ''} type="native_thinking">
            <Box
              sx={{
                fontSize: '1.1rem',
                lineHeight: '1.5',
                flexShrink: 0,
                cursor: 'help',
                display: 'flex',
                alignItems: 'center',
                height: '1.5rem'
              }}
            >
              🧠
            </Box>
          </ContentPreviewTooltip>
        ) : (
          <Box
            sx={{
              fontSize: '1.1rem',
              lineHeight: '1.5',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              height: '1.5rem'
            }}
          >
            🧠
          </Box>
        )}
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Header - always visible, changes ">" when collapsed, "^" when expanded */}
          <Box 
            sx={{ 
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              cursor: onToggleAutoCollapse ? 'pointer' : 'default',
              px: shouldShowCollapsed ? 1 : 0,
              py: 0.5,
              mx: shouldShowCollapsed ? -1 : 0,
              borderRadius: 1,
              transition: 'background-color 0.2s ease',
              '&:hover': onToggleAutoCollapse ? {
                bgcolor: 'action.hover'
              } : {}
            }}
            onClick={onToggleAutoCollapse}
          >
            <Typography
              variant="caption"
              sx={{
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
                fontSize: '0.75rem',
                color: 'info.main'
              }}
            >
              THINKING {shouldShowCollapsed ? '>' : '^'}
            </Typography>
            {shouldShowCollapsed && (
              <ExpandMore fontSize="small" sx={{ ml: 'auto', opacity: 0.6 }} />
            )}
          </Box>
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              {hasMarkdown ? (
                <Box sx={{
                  '& p, & li': {
                    color: 'text.secondary',
                    fontStyle: 'italic',
                  },
                  color: 'text.secondary',
                  fontStyle: 'italic',
                }}>
                  <ReactMarkdown
                    components={thoughtMarkdownComponents}
                    remarkPlugins={[remarkBreaks]}
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
                    color: 'text.secondary',
                    fontStyle: 'italic'
                  }}
                >
                  {item.content}
                </Typography>
              )}
              {/* Collapse button at bottom */}
              {onToggleAutoCollapse && (
                <Box
                  onClick={onToggleAutoCollapse}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    mt: 0.5,
                    cursor: 'pointer',
                    opacity: 0.6,
                    '&:hover': {
                      opacity: 1
                    }
                  }}
                >
                  <ExpandLess fontSize="small" />
                  <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                    Collapse
                  </Typography>
                </Box>
              )}
            </Box>
          </Collapse>
        </Box>
      </Box>
    );
  }

  // Render final answer - emphasized text with emoji and markdown support
  if (item.type === 'final_answer') {
    return (
      <Box 
        sx={{ 
          mb: 2, 
          mt: 3,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && {
            animation: 'fadeCollapse 0.6s ease-out',
            '@keyframes fadeCollapse': {
              '0%': { opacity: 1 },
              '50%': { opacity: 0.3 },
              '100%': { opacity: 1 },
            },
          })
        }}
      >
        {/* Emoji with tooltip when collapsed */}
        {shouldShowCollapsed ? (
          <ContentPreviewTooltip content={item.content || ''} type="final_answer">
            <Box
              sx={{
                fontSize: '1.1rem',
                lineHeight: '1.5',
                flexShrink: 0,
                cursor: 'help',
                display: 'flex',
                alignItems: 'center',
                height: '1.5rem'
              }}
            >
              🎯
            </Box>
          </ContentPreviewTooltip>
        ) : (
          <Box
            sx={{
              fontSize: '1.1rem',
              lineHeight: '1.5',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              height: '1.5rem'
            }}
          >
            🎯
          </Box>
        )}
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Header - always visible, changes ">" when collapsed, "^" when expanded */}
          <Box 
            sx={{ 
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              cursor: onToggleAutoCollapse ? 'pointer' : 'default',
              px: shouldShowCollapsed ? 1 : 0,
              py: 0.5,
              mx: shouldShowCollapsed ? -1 : 0,
              borderRadius: 1,
              transition: 'background-color 0.2s ease',
              '&:hover': onToggleAutoCollapse ? {
                bgcolor: 'action.hover'
              } : {}
            }}
            onClick={onToggleAutoCollapse}
          >
            <Typography
              variant="caption"
              sx={{
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
                fontSize: '0.75rem',
                color: '#2e7d32'
              }}
            >
              FINAL ANSWER {shouldShowCollapsed ? '>' : '^'}
            </Typography>
            {shouldShowCollapsed && (
              <ExpandMore fontSize="small" sx={{ ml: 'auto', opacity: 0.6 }} />
            )}
          </Box>
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              <ReactMarkdown
                urlTransform={defaultUrlTransform}
                components={finalAnswerMarkdownComponents}
                remarkPlugins={[remarkBreaks]}
                skipHtml
              >
                {item.content || ''}
              </ReactMarkdown>
              {/* Collapse button at bottom */}
              {onToggleAutoCollapse && (
                <Box
                  onClick={onToggleAutoCollapse}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    mt: 0.5,
                    cursor: 'pointer',
                    opacity: 0.6,
                    '&:hover': {
                      opacity: 1
                    }
                  }}
                >
                  <ExpandLess fontSize="small" />
                  <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                    Collapse
                  </Typography>
                </Box>
              )}
            </Box>
          </Collapse>
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
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && {
            animation: 'fadeCollapse 0.6s ease-out',
            '@keyframes fadeCollapse': {
              '0%': { opacity: 1 },
              '50%': { opacity: 0.3 },
              '100%': { opacity: 1 },
            },
          })
        }}
      >
        {/* Emoji with tooltip when collapsed */}
        {shouldShowCollapsed ? (
          <ContentPreviewTooltip content={item.content || ''} type="summarization">
            <Box
              sx={{
                fontSize: '1.1rem',
                lineHeight: '1.5',
                flexShrink: 0,
                cursor: 'help',
                display: 'flex',
                alignItems: 'center',
                height: '1.5rem'
              }}
            >
              📋
            </Box>
          </ContentPreviewTooltip>
        ) : (
          <Box
            sx={{
              fontSize: '1.1rem',
              lineHeight: '1.5',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              height: '1.5rem'
            }}
          >
            📋
          </Box>
        )}
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Header - always visible, changes ">" when collapsed, "^" when expanded */}
          <Box 
            sx={{ 
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              cursor: onToggleAutoCollapse ? 'pointer' : 'default',
              px: shouldShowCollapsed ? 1 : 0,
              py: 0.5,
              mx: shouldShowCollapsed ? -1 : 0,
              borderRadius: 1,
              transition: 'background-color 0.2s ease',
              '&:hover': onToggleAutoCollapse ? {
                bgcolor: 'action.hover'
              } : {}
            }}
            onClick={onToggleAutoCollapse}
          >
            <Typography
              variant="caption"
              sx={{
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
                fontSize: '0.75rem',
                color: 'rgba(237, 108, 2, 0.9)'
              }}
            >
              TOOL RESULT SUMMARY {shouldShowCollapsed ? '>' : '^'}
            </Typography>
            {shouldShowCollapsed && (
              <ExpandMore fontSize="small" sx={{ ml: 'auto', opacity: 0.6 }} />
            )}
          </Box>
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              <Box
                sx={{
                  pl: 3.5,
                  ml: 3.5,
                  py: 0.5,
                  borderLeft: '2px solid rgba(237, 108, 2, 0.2)',
                }}
              >
                {hasMarkdown ? (
                  <Box sx={{
                    '& p': { color: 'text.secondary' },
                    '& li': { color: 'text.secondary' },
                    color: 'text.secondary',
                  }}>
                    <ReactMarkdown
                      components={thoughtMarkdownComponents}
                      remarkPlugins={[remarkBreaks]}
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
                      color: 'text.secondary'
                    }}
                  >
                    {item.content}
                  </Typography>
                )}
              </Box>
              {/* Collapse button at bottom */}
              {onToggleAutoCollapse && (
                <Box
                  onClick={onToggleAutoCollapse}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    mt: 0.5,
                    cursor: 'pointer',
                    opacity: 0.6,
                    '&:hover': {
                      opacity: 1
                    }
                  }}
                >
                  <ExpandLess fontSize="small" />
                  <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                    Collapse
                  </Typography>
                </Box>
              )}
            </Box>
          </Collapse>
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
