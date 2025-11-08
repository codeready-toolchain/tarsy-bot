import { memo } from 'react';
import { Box, Typography } from '@mui/material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import TypewriterText from './TypewriterText';
import { 
  hasMarkdownSyntax, 
  finalAnswerMarkdownComponents, 
  thoughtMarkdownComponents 
} from '../utils/markdownComponents';

/**
 * Shared streaming item interface
 * Used by both ConversationTimeline and ChatMessageList
 */
export interface StreamingItem {
  type: 'thought' | 'final_answer' | 'summarization' | 'tool_call' | 'user_message';
  content?: string;
  stage_execution_id?: string;
  mcp_event_id?: string;
  waitingForDb?: boolean;
  // Tool call specific fields
  toolName?: string;
  messageId?: string;
}

interface StreamingContentRendererProps {
  item: StreamingItem;
}

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
  // Render thought
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
        <TypewriterText text={item.content || ''} speed={15}>
          {(displayText) => (
            hasMarkdown ? (
              <Box sx={{ flex: 1, minWidth: 0 }}>
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
                  color: 'text.primary'
                }}
              >
                {displayText}
              </Typography>
            )
          )}
        </TypewriterText>
      </Box>
    );
  }
  
  // Render summarization
  if (item.type === 'summarization') {
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
            Tool Result Summary
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
            <TypewriterText text={item.content || ''} speed={15}>
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
  
  // Render final answer
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
              color: '#2e7d32',
              mt: 0.25
            }}
          >
            Final Answer
          </Typography>
        </Box>
        <Box sx={{ pl: 3.5 }}>
          <TypewriterText text={item.content || ''} speed={15}>
            {(displayText) => (
              <ReactMarkdown
                urlTransform={defaultUrlTransform}
                components={finalAnswerMarkdownComponents}
              >
                {displayText}
              </ReactMarkdown>
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

