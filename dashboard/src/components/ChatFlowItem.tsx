import { memo } from 'react';
import { Box, Typography, Divider, Chip, alpha, IconButton, Alert, Collapse } from '@mui/material';
import { Flag, AccountCircle, ExpandMore, ExpandLess } from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import ToolCallBox from './ToolCallBox';
import NativeToolsBox from './NativeToolsBox';
import EmojiIcon from './EmojiIcon';
import CollapsibleItemHeader from './CollapsibleItemHeader';
import CollapseButton from './CollapseButton';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import { formatDurationMs } from '../utils/timestamp';
import { 
  hasMarkdownSyntax, 
  thoughtMarkdownComponents 
} from '../utils/markdownComponents';
import { FADE_COLLAPSE_ANIMATION } from '../constants/chatFlowAnimations';
import { CHAT_FLOW_ITEM_TYPES } from '../constants/chatFlowItemTypes';
import { STAGE_STATUS } from '../utils/statusConstants';

interface ChatFlowItemProps {
  item: ChatFlowItemData;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  // Auto-collapse props
  isAutoCollapsed?: boolean;
  onToggleAutoCollapse?: () => void;
  expandAll?: boolean;
  // Whether this item type is collapsible at all (determines if clickable)
  isCollapsible?: boolean;
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
  isCollapsible = true
}: ChatFlowItemProps) {
  // Determine if we should show collapsed state (header only)
  // Only collapse if the item is actually collapsible
  const shouldShowCollapsed = isCollapsible && isAutoCollapsed && !expandAll;

  // Auto-collapsed visual dimming (header + leading icon)
  // Only apply dimming when item is collapsible and should be collapsed
  const collapsedHeaderOpacity = shouldShowCollapsed ? 0.65 : 1;
  const collapsedLeadingIconOpacity = shouldShowCollapsed ? 0.6 : 1;

  /**
   * Shared rendering logic for final result items (FINAL_ANSWER and FORCED_CONCLUSION)
   * Both types share the same structure and styling, differing only in header text and tooltip type
   */
  const renderFinalResult = (
    headerText: string,
    tooltipType: 'final_answer' | 'forced_conclusion'
  ) => {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box 
        sx={{ 
          mb: 2, 
          mt: 3,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && FADE_COLLAPSE_ANIMATION)
        }}
      >
        <EmojiIcon
          emoji="🎯"
          opacity={collapsedLeadingIconOpacity}
          showTooltip={shouldShowCollapsed}
          tooltipContent={item.content || ''}
          tooltipType={tooltipType}
        />
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <CollapsibleItemHeader
            headerText={headerText}
            headerColor="#2e7d32"
            headerTextTransform="uppercase"
            shouldShowCollapsed={shouldShowCollapsed}
            collapsedHeaderOpacity={collapsedHeaderOpacity}
            onToggle={isCollapsible && onToggleAutoCollapse ? onToggleAutoCollapse : undefined}
          />
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              {hasMarkdown ? (
                <Box sx={{ color: 'text.primary' }}>
                  <ReactMarkdown
                    urlTransform={defaultUrlTransform}
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
              {isCollapsible && onToggleAutoCollapse && <CollapseButton onClick={onToggleAutoCollapse} />}
            </Box>
          </Collapse>
        </Box>
      </Box>
    );
  };
  
  // Render stage start separator with collapse/expand control
  if (item.type === CHAT_FLOW_ITEM_TYPES.STAGE_START) {
    const isErrorStatus = item.stageStatus === STAGE_STATUS.FAILED || item.stageStatus === STAGE_STATUS.TIMED_OUT || item.stageStatus === STAGE_STATUS.CANCELLED;
    const hasError = isErrorStatus && item.stageErrorMessage;
    
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
                backgroundColor: alpha(isErrorStatus ? '#d32f2f' : '#1976d2', 0.08),
                '& .MuiChip-root': {
                  backgroundColor: alpha(isErrorStatus ? '#d32f2f' : '#1976d2', 0.12),
                  borderColor: isErrorStatus ? '#d32f2f' : '#1976d2',
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
              color={isErrorStatus ? 'error' : 'primary'}
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
                  backgroundColor: isCollapsed ? alpha('#666', 0.1) : alpha(isErrorStatus ? '#d32f2f' : '#1976d2', 0.1),
                  border: '1px solid',
                  borderColor: isCollapsed ? alpha('#666', 0.2) : alpha(isErrorStatus ? '#d32f2f' : '#1976d2', 0.2),
                  color: isCollapsed ? '#666' : 'inherit',
                  '&:hover': {
                    backgroundColor: isCollapsed ? '#666' : (isErrorStatus ? '#d32f2f' : '#1976d2'),
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
        
        {/* Show error message for failed/timed_out/cancelled stages (not collapsed) */}
        {hasError && !isCollapsed && (
          <Alert severity="error" sx={{ mt: 2, mx: 2 }}>
            <Typography variant="body2">
              <strong>
                {item.stageStatus === STAGE_STATUS.TIMED_OUT ? 'Stage Timed Out' : 
                 item.stageStatus === STAGE_STATUS.CANCELLED ? 'Stage Cancelled' : 
                 'Stage Failed'}:
              </strong> {item.stageErrorMessage}
            </Typography>
          </Alert>
        )}
      </Box>
    );
  }

  // Render thought - with hybrid markdown support (only parse markdown when detected)
  if (item.type === CHAT_FLOW_ITEM_TYPES.THOUGHT) {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    const interactionDurationLabel =
      item.interaction_duration_ms != null && item.interaction_duration_ms > 0
        ? formatDurationMs(item.interaction_duration_ms)
        : null;
    
    return (
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && FADE_COLLAPSE_ANIMATION)
        }}
      >
        <EmojiIcon
          emoji="💭"
          opacity={collapsedLeadingIconOpacity}
          showTooltip={shouldShowCollapsed}
          tooltipContent={item.content || ''}
          tooltipType="thought"
        />
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <CollapsibleItemHeader
            headerText={interactionDurationLabel ? `Thought for ${interactionDurationLabel}` : 'Thought'}
            headerColor="info.main"
            headerTextTransform="none"
            shouldShowCollapsed={shouldShowCollapsed}
            collapsedHeaderOpacity={collapsedHeaderOpacity}
            onToggle={isCollapsible && onToggleAutoCollapse ? onToggleAutoCollapse : undefined}
          />
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              {/* Thinking content box - no fixed height when finalized (adjusts to content) */}
              <Box 
                sx={(theme) => ({ 
                  bgcolor: alpha(theme.palette.grey[300], 0.15),
                  border: '1px solid',
                  borderColor: alpha(theme.palette.grey[400], 0.2),
                  borderRadius: 1,
                  p: 1.5
                })}
              >
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
              </Box>
              {isCollapsible && onToggleAutoCollapse && <CollapseButton onClick={onToggleAutoCollapse} />}
            </Box>
          </Collapse>
        </Box>
      </Box>
    );
  }

  // Render native thinking (Gemini 3.0+ native thinking mode)
  if (item.type === CHAT_FLOW_ITEM_TYPES.NATIVE_THINKING) {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    const interactionDurationLabel =
      item.interaction_duration_ms != null && item.interaction_duration_ms > 0
        ? formatDurationMs(item.interaction_duration_ms)
        : null;
    
    return (
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && FADE_COLLAPSE_ANIMATION)
        }}
      >
        <EmojiIcon
          emoji="💭"
          opacity={collapsedLeadingIconOpacity}
          showTooltip={shouldShowCollapsed}
          tooltipContent={item.content || ''}
          tooltipType="native_thinking"
        />
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <CollapsibleItemHeader
            headerText={interactionDurationLabel ? `Thought for ${interactionDurationLabel}` : 'Thought'}
            headerColor="info.main"
            headerTextTransform="none"
            shouldShowCollapsed={shouldShowCollapsed}
            collapsedHeaderOpacity={collapsedHeaderOpacity}
            onToggle={isCollapsible && onToggleAutoCollapse ? onToggleAutoCollapse : undefined}
          />
          
          {/* Collapsible content */}
          <Collapse in={!shouldShowCollapsed} timeout={300}>
            <Box sx={{ mt: 0.5 }}>
              {/* Thinking content box - no fixed height when finalized (adjusts to content) */}
              <Box 
                sx={(theme) => ({ 
                  bgcolor: alpha(theme.palette.grey[300], 0.15),
                  border: '1px solid',
                  borderColor: alpha(theme.palette.grey[400], 0.2),
                  borderRadius: 1,
                  p: 1.5
                })}
              >
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
              </Box>
              {isCollapsible && onToggleAutoCollapse && <CollapseButton onClick={onToggleAutoCollapse} />}
            </Box>
          </Collapse>
        </Box>
      </Box>
    );
  }

  // Render intermediate response (native thinking - intermediate iterations)
  // No header label, just icon and content with light markdown
  if (item.type === CHAT_FLOW_ITEM_TYPES.INTERMEDIATE_RESPONSE) {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start'
        }}
      >
        <EmojiIcon
          emoji="💬"
          opacity={1}
        />
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
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
        </Box>
      </Box>
    );
  }

  // Render final answer - uses same style as intermediate_response for smooth transition
  if (item.type === CHAT_FLOW_ITEM_TYPES.FINAL_ANSWER) {
    return renderFinalResult("FINAL ANSWER", "final_answer");
  }

  // Render forced conclusion - same style as final answer with max iterations indicator
  if (item.type === CHAT_FLOW_ITEM_TYPES.FORCED_CONCLUSION) {
    return renderFinalResult("FINAL ANSWER (⚠️Max Iterations)", "forced_conclusion");
  }

  // Render tool call - indented expandable box
  if (item.type === CHAT_FLOW_ITEM_TYPES.TOOL_CALL) {
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

  if (item.type === CHAT_FLOW_ITEM_TYPES.USER_MESSAGE) {
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
  if (item.type === CHAT_FLOW_ITEM_TYPES.SUMMARIZATION) {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box 
        sx={{ 
          mb: 1.5,
          display: 'flex', 
          gap: 1.5,
          alignItems: 'flex-start',
          // Fade animation when auto-collapsing
          ...(shouldShowCollapsed && FADE_COLLAPSE_ANIMATION)
        }}
      >
        <EmojiIcon
          emoji="📋"
          opacity={collapsedLeadingIconOpacity}
          showTooltip={shouldShowCollapsed}
          tooltipContent={item.content || ''}
          tooltipType="summarization"
        />
        
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <CollapsibleItemHeader
            headerText="TOOL RESULT SUMMARY"
            headerColor="rgba(237, 108, 2, 0.9)"
            headerTextTransform="uppercase"
            shouldShowCollapsed={shouldShowCollapsed}
            collapsedHeaderOpacity={collapsedHeaderOpacity}
            onToggle={isCollapsible && onToggleAutoCollapse ? onToggleAutoCollapse : undefined}
          />
          
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
              {isCollapsible && onToggleAutoCollapse && <CollapseButton onClick={onToggleAutoCollapse} />}
            </Box>
          </Collapse>
        </Box>
      </Box>
    );
  }

  // Render native tool usage indicators
  if (item.type === CHAT_FLOW_ITEM_TYPES.NATIVE_TOOL_USAGE && item.nativeToolsUsage) {
    return <NativeToolsBox usage={item.nativeToolsUsage} />;
  }

  return null;
}

// Export memoized component using default shallow comparison
// This automatically compares all props (content, timestamp, type, toolName, toolArguments,
// toolResult, serverName, success, errorMessage, duration_ms, etc.)
export default memo(ChatFlowItem);
