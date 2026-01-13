import { memo, useEffect, useRef } from 'react';
import { Box, Typography, alpha } from '@mui/material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import TypewriterText from './TypewriterText';
import { 
  hasMarkdownSyntax, 
  thoughtMarkdownComponents 
} from '../utils/markdownComponents';
import { 
  STREAMING_CONTENT_TYPES, 
  type StreamingContentType 
} from '../utils/eventTypes';

/**
 * Shared streaming item interface
 * Used by both ConversationTimeline and ChatMessageList
 * 
 * Types:
 * - LLM streaming content types (thought, final_answer, summarization, native_thinking) 
 * - UI-specific types (tool_call, user_message)
 */
export interface StreamingItem {
  type: StreamingContentType | 'tool_call' | 'user_message';
  content?: string;
  stage_execution_id?: string;
  mcp_event_id?: string;
  waitingForDb?: boolean;
  // Tool call specific fields
  toolName?: string;
  messageId?: string;
  // LLM interaction ID for deduplication of thought/final_answer/native_thinking streams
  llm_interaction_id?: string;
  // Parallel execution metadata
  parent_stage_execution_id?: string;
  parallel_index?: number;
  agent_name?: string;
}

interface StreamingContentRendererProps {
  item: StreamingItem;
}

/**
 * ThinkingBlock - Shared component for thought and native_thinking rendering
 * 
 * @param content - The thinking content to display
 * @param textColor - MUI theme color path (e.g., 'text.primary' or 'text.secondary')
 * @param isItalic - Whether to render text in italic style
 */
interface ThinkingBlockProps {
  content: string;
  textColor: string;
  isItalic?: boolean;
}

const ThinkingBlock = memo(({ content, textColor, isItalic = false }: ThinkingBlockProps) => {
  const hasMarkdown = hasMarkdownSyntax(content);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  
  // Auto-scroll to bottom when content changes during streaming
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [content]);
  
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
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            textTransform: 'none',
            letterSpacing: 0.5,
            fontSize: '0.75rem',
            color: 'info.main',
            display: 'block',
            mb: 0.5
          }}
        >
          Thinking...
        </Typography>
        {/* Thinking content box with light grey background - fixed height during streaming */}
        <Box 
          ref={scrollContainerRef}
          sx={(theme) => ({ 
            bgcolor: alpha(theme.palette.grey[300], 0.15),
            border: '1px solid',
            borderColor: alpha(theme.palette.grey[400], 0.2),
            borderRadius: 1,
            p: 1.5,
            height: '150px', // Fixed height to prevent UI jumping during streaming
            overflowY: 'auto',
            '&::-webkit-scrollbar': {
              width: '8px',
            },
            '&::-webkit-scrollbar-track': {
              bgcolor: 'transparent',
            },
            '&::-webkit-scrollbar-thumb': {
              bgcolor: alpha(theme.palette.grey[500], 0.3),
              borderRadius: '4px',
              '&:hover': {
                bgcolor: alpha(theme.palette.grey[500], 0.5),
              }
            }
          })}
        >
          <TypewriterText text={content} speed={3}>
            {(displayText) => (
              hasMarkdown ? (
                <Box sx={isItalic ? { 
                  '& p, & li': { 
                    color: textColor,
                    fontStyle: 'italic'
                  }
                } : undefined}>
                  <ReactMarkdown
                    components={thoughtMarkdownComponents}
                    skipHtml
                  >
                    {displayText}
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
                    color: textColor,
                    fontStyle: isItalic ? 'italic' : 'normal'
                  }}
                >
                  {displayText}
                </Typography>
              )
            )}
          </TypewriterText>
        </Box>
      </Box>
    </Box>
  );
});

ThinkingBlock.displayName = 'ThinkingBlock';

/**
 * StreamingContentRenderer Component
 * 
 * Shared renderer for streaming LLM content with typewriter effect.
 * Used by both ConversationTimeline (session investigation) and ChatMessageList (chat responses).
 * 
 * Renders:
 * - Thoughts (with hybrid markdown support)
 * - Final Answers (full markdown)
 * - Summarizations (with hybrid markdown support)
 * 
 * Features:
 * - Smooth typewriter animation (15ms/char)
 * - Markdown rendering without flickering
 * - Consistent styling across views
 */
const StreamingContentRenderer = memo(({ item }: StreamingContentRendererProps) => {
  // Render thought (ReAct pattern)
  if (item.type === STREAMING_CONTENT_TYPES.THOUGHT) {
    return <ThinkingBlock content={item.content || ''} textColor="text.primary" />;
  }

  // Render native thinking (Gemini 3.0+ native thinking mode)
  if (item.type === STREAMING_CONTENT_TYPES.NATIVE_THINKING) {
    return <ThinkingBlock content={item.content || ''} textColor="text.secondary" isItalic />;
  }

  // Render intermediate response (native thinking - intermediate iterations)
  if (item.type === STREAMING_CONTENT_TYPES.INTERMEDIATE_RESPONSE) {
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
          💬
        </Typography>
        <TypewriterText text={item.content || ''} speed={3}>
          {(displayText) => (
            <Box sx={{ flex: 1, minWidth: 0 }}>
              {hasMarkdown ? (
                <ReactMarkdown
                  components={thoughtMarkdownComponents}
                  skipHtml
                >
                  {displayText}
                </ReactMarkdown>
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
                  {displayText}
                </Typography>
              )}
            </Box>
          )}
        </TypewriterText>
      </Box>
    );
  }
  
  // Render summarization (tool result summary)
  if (item.type === STREAMING_CONTENT_TYPES.SUMMARIZATION) {
    // Check if this is the placeholder text
    const isPlaceholder = item.content === 'Summarizing tool results...';
    
    // Check if content has markdown syntax (skip check for placeholder)
    const hasMarkdown = !isPlaceholder && hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 1.5 }}>
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
              color: 'rgba(237, 108, 2, 0.9)',
              mt: 0.25
            }}
          >
            TOOL RESULT SUMMARY
          </Typography>
        </Box>
        <Box 
          sx={{ 
            pl: 3.5,
            ml: 3.5,
            py: 0.5,
            borderLeft: '2px solid rgba(237, 108, 2, 0.2)'
          }}
        >
          {isPlaceholder ? (
            // For placeholder, render immediately without typewriter effect
            <Typography
              variant="body1"
              sx={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.7,
                fontSize: '1rem',
                color: 'text.disabled',
                fontStyle: 'italic',
                animation: 'pulse 1.5s ease-in-out infinite',
                '@keyframes pulse': {
                  '0%, 100%': { opacity: 0.3 },
                  '50%': { opacity: 1 }
                }
              }}
            >
              {item.content}
            </Typography>
          ) : (
            <TypewriterText text={item.content || ''} speed={3}>
              {(displayText) => (
                hasMarkdown ? (
                  <Box sx={{ 
                    '& p': { color: 'text.secondary' },
                    '& li': { color: 'text.secondary' }
                  }}>
                    <ReactMarkdown
                      components={thoughtMarkdownComponents}
                      skipHtml
                    >
                      {displayText}
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
                    {displayText}
                  </Typography>
                )
              )}
            </TypewriterText>
          )}
        </Box>
      </Box>
    );
  }
  
  // Render final answer - uses same style as intermediate_response for smooth transition
  if (item.type === STREAMING_CONTENT_TYPES.FINAL_ANSWER) {
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 2, mt: 3 }}>
        <Box sx={{ display: 'flex', gap: 1.5, mb: 0.5 }}>
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
              color: '#2e7d32',
              mt: 0.25
            }}
          >
            FINAL ANSWER
          </Typography>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0, ml: 4 }}>
          <TypewriterText text={item.content || ''} speed={3}>
            {(displayText) => (
              hasMarkdown ? (
                <Box sx={{ color: 'text.primary' }}>
                  <ReactMarkdown
                    urlTransform={defaultUrlTransform}
                    components={thoughtMarkdownComponents}
                  >
                    {displayText}
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
                  {displayText}
                </Typography>
              )
            )}
          </TypewriterText>
        </Box>
      </Box>
    );
  }
  
  // Unsupported type - return null
  return null;
});

StreamingContentRenderer.displayName = 'StreamingContentRenderer';

export default StreamingContentRenderer;

