import { Box, Typography, Divider, Chip } from '@mui/material';
import { Flag } from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import ToolCallBox from './ToolCallBox';
import type { ChatFlowItemData } from '../utils/chatFlowParser';

interface ChatFlowItemProps {
  item: ChatFlowItemData;
}

/**
 * ChatFlowItem Component
 * Renders different types of chat flow items in a compact transcript style
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

  // Render thought - simple text with emoji
  if (item.type === 'thought') {
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
        <Typography
          variant="body1"
          sx={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: 1.7,
            fontSize: '1rem', // Increased from 0.95rem
            color: 'text.primary'
          }}
        >
          {item.content}
        </Typography>
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
            components={{
              h1: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1, mt: 1.5, fontSize: '1.1rem' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              h2: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 0.75, mt: 1.25, fontSize: '1rem' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              h3: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5, mt: 1, fontSize: '0.95rem' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              p: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography variant="body2" sx={{ mb: 1, lineHeight: 1.7, fontSize: '0.95rem' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              ul: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Box component="ul" sx={{ mb: 1, pl: 2.5 }} {...safeProps}>
                    {children}
                  </Box>
                );
              },
              ol: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Box component="ol" sx={{ mb: 1, pl: 2.5 }} {...safeProps}>
                    {children}
                  </Box>
                );
              },
              li: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography component="li" variant="body2" sx={{ mb: 0.5, lineHeight: 1.6, fontSize: '0.95rem' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              code: (props: any) => {
                const { node, inline, children, ...safeProps } = props;
                return (
                  <Box
                    component="code"
                    sx={{
                      bgcolor: 'grey.100',
                      px: 0.75,
                      py: 0.25,
                      borderRadius: 0.5,
                      fontFamily: 'monospace',
                      fontSize: '0.85rem'
                    }}
                    {...safeProps}
                  >
                    {children}
                  </Box>
                );
              },
              strong: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Box component="strong" sx={{ fontWeight: 700 }} {...safeProps}>
                    {children}
                  </Box>
                );
              }
            }}
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

  return null;
}

export default ChatFlowItem;

