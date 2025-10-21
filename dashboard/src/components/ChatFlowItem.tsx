import { memo } from 'react';
import { Box, Typography, Divider, Chip } from '@mui/material';
import { Flag } from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import ToolCallBox from './ToolCallBox';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import { 
  hasMarkdownSyntax, 
  finalAnswerMarkdownComponents, 
  thoughtMarkdownComponents 
} from '../utils/markdownComponents.tsx';

interface ChatFlowItemProps {
  item: ChatFlowItemData;
}

/**
 * ChatFlowItem Component
 * Renders different types of chat flow items in a compact transcript style
 * Memoized to prevent unnecessary re-renders
 */
function ChatFlowItem({ item }: ChatFlowItemProps) {
  // Render stage start separator
  if (item.type === 'stage_start') {
    return (
      <Box sx={{ my: 2.5 }}>
        <Divider sx={{ mb: 1 }}>
          <Chip
            icon={<Flag />}
            label={`Stage: ${item.stageName}`}
            color="primary"
            variant="outlined"
            size="small"
            sx={{
              fontSize: '0.8rem',
              fontWeight: 600
            }}
          />
        </Divider>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            display: 'block',
            textAlign: 'center',
            fontStyle: 'italic',
            fontSize: '0.75rem'
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

  return null;
}

// Export memoized component with custom comparison to prevent unnecessary re-renders
export default memo(ChatFlowItem, (prevProps, nextProps) => {
  // Only re-render if content, timestamp, or type changes
  return prevProps.item.content === nextProps.item.content &&
         prevProps.item.timestamp_us === nextProps.item.timestamp_us &&
         prevProps.item.type === nextProps.item.type;
});

