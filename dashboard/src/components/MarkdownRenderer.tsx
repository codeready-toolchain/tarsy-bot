import React from 'react';
import { Box, Paper, Typography } from '@mui/material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import CopyButton from './CopyButton';

interface MarkdownRendererProps {
  content: string;
  showCopyButton?: boolean;
  copyTooltip?: string;
}

/**
 * MarkdownRenderer - Reusable component for rendering markdown with consistent styling
 * Used across FinalAnalysisCard, ScoreDetailView, and other components that need formatted markdown
 */
const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  showCopyButton = true,
  copyTooltip = 'Copy content'
}) => {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 3,
        bgcolor: 'grey.100'
      }}
    >
      {/* Copy button header */}
      {showCopyButton && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
          <CopyButton
            text={content}
            variant="icon"
            size="small"
            tooltip={copyTooltip}
          />
        </Box>
      )}

      <ReactMarkdown
        urlTransform={defaultUrlTransform}
        components={{
          // Custom styling for markdown elements
          h1: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Typography variant="h5" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold' }} {...safeProps}>
                {children}
              </Typography>
            );
          },
          h2: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 2 }} {...safeProps}>
                {children}
              </Typography>
            );
          },
          h3: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Typography variant="subtitle1" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 1.5 }} {...safeProps}>
                {children}
              </Typography>
            );
          },
          p: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Typography
                variant="body1"
                sx={{
                  lineHeight: 1.6,
                  fontSize: '0.95rem',
                  mb: 1
                }}
                {...safeProps}
              >
                {children}
              </Typography>
            );
          },
          ul: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Box component="ul" sx={{ pl: 2, mb: 1 }} {...safeProps}>
                {children}
              </Box>
            );
          },
          li: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Typography component="li" variant="body1" sx={{ fontSize: '0.95rem', lineHeight: 1.6, mb: 0.5 }} {...safeProps}>
                {children}
              </Typography>
            );
          },
          code: (props: any) => {
            const { node, inline, children, className, ...safeProps } = props;
            const isCodeBlock = className?.includes('language-');
            const codeContent = String(children).replace(/\n$/, '');

            if (isCodeBlock) {
              // Multi-line code block with copy button
              return (
                <Box sx={{
                  position: 'relative',
                  mb: 2,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  bgcolor: 'grey.50',
                  overflow: 'hidden'
                }}>
                  {/* Code block header */}
                  <Box sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    px: 2,
                    py: 1,
                    bgcolor: 'grey.100',
                    borderBottom: '1px solid',
                    borderBottomColor: 'divider'
                  }}>
                    <Typography variant="caption" sx={{
                      fontFamily: 'monospace',
                      color: 'text.secondary',
                      fontWeight: 'medium'
                    }}>
                      {className?.replace('language-', '') || 'code'}
                    </Typography>
                    <CopyButton
                      text={codeContent}
                      variant="icon"
                      size="small"
                      tooltip="Copy code"
                    />
                  </Box>

                  {/* Code content */}
                  <Typography
                    component="pre"
                    className={className}
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      padding: 2,
                      margin: 0,
                      whiteSpace: 'pre',
                      overflow: 'auto',
                      lineHeight: 1.4,
                      color: 'text.primary'
                    }}
                    {...safeProps}
                  >
                    {codeContent}
                  </Typography>
                </Box>
              );
            } else {
              // Inline code
              return (
                <Typography
                  component="code"
                  className={className}
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: '0.85rem',
                    backgroundColor: 'rgba(0, 0, 0, 0.08)',
                    color: 'error.main',
                    padding: '2px 6px',
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'rgba(0, 0, 0, 0.12)'
                  }}
                  {...safeProps}
                >
                  {children}
                </Typography>
              );
            }
          },
          strong: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Typography component="strong" sx={{ fontWeight: 'bold' }} {...safeProps}>
                {children}
              </Typography>
            );
          },
          blockquote: (props) => {
            const { node, children, ...safeProps } = props;
            return (
              <Box
                component="blockquote"
                sx={{
                  borderLeft: '4px solid',
                  borderColor: 'primary.main',
                  pl: 2,
                  ml: 0,
                  fontStyle: 'italic',
                  color: 'text.secondary',
                  mb: 1
                }}
                {...safeProps}
              >
                {children}
              </Box>
            );
          }
        }}
      >
        {content}
      </ReactMarkdown>
    </Paper>
  );
};

export default MarkdownRenderer;