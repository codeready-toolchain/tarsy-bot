/**
 * Shared markdown rendering utilities
 * Used by ChatFlowItem and ConversationTimeline for consistent markdown rendering
 */

import { Box, Typography } from '@mui/material';

/**
 * Helper function to detect if text contains markdown syntax
 * Used for hybrid rendering approach - only parse markdown when needed
 */
export const hasMarkdownSyntax = (text: string): boolean => {
  // Check for common markdown patterns: bold, italic, code, lists, links
  return /[*_`[\]#-]/.test(text);
};

/**
 * Memoized markdown components for final answer rendering
 * Defined outside component to prevent recreation on every render
 */
export const finalAnswerMarkdownComponents = {
  h1: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1, mt: 1.5, fontSize: '1.1rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  },
  h2: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 0.75, mt: 1.25, fontSize: '1rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  },
  h3: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5, mt: 1, fontSize: '0.95rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  },
  p: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography variant="body2" sx={{ mb: 1, lineHeight: 1.7, fontSize: '0.95rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  },
  ul: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="ul" sx={{ mb: 1, pl: 2.5 }} {...safeProps}>
        {children}
      </Box>
    );
  },
  ol: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="ol" sx={{ mb: 1, pl: 2.5 }} {...safeProps}>
        {children}
      </Box>
    );
  },
  li: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography component="li" variant="body2" sx={{ mb: 0.5, lineHeight: 1.6, fontSize: '0.95rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  },
  code: (props: any) => {
    const { node: _node, inline: _inline, children, ...safeProps } = props;
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
  strong: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="strong" sx={{ fontWeight: 700 }} {...safeProps}>
        {children}
      </Box>
    );
  }
};

/**
 * Lightweight markdown components for thoughts and summarizations
 * Similar to finalAnswerMarkdownComponents but simpler styling
 */
export const thoughtMarkdownComponents = {
  p: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography variant="body1" sx={{ mb: 0.5, lineHeight: 1.7, fontSize: '1rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  },
  strong: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="strong" sx={{ fontWeight: 700 }} {...safeProps}>
        {children}
      </Box>
    );
  },
  em: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="em" sx={{ fontStyle: 'italic' }} {...safeProps}>
        {children}
      </Box>
    );
  },
  code: (props: any) => {
    const { node: _node, inline: _inline, children, ...safeProps } = props;
    return (
      <Box
        component="code"
        sx={{
          bgcolor: 'grey.100',
          px: 0.5,
          py: 0.25,
          borderRadius: 0.5,
          fontFamily: 'monospace',
          fontSize: '0.9em'
        }}
        {...safeProps}
      >
        {children}
      </Box>
    );
  },
  ul: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="ul" sx={{ mb: 0.5, pl: 2.5 }} {...safeProps}>
        {children}
      </Box>
    );
  },
  ol: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Box component="ol" sx={{ mb: 0.5, pl: 2.5 }} {...safeProps}>
        {children}
      </Box>
    );
  },
  li: (props: any) => {
    const { node: _node, children, ...safeProps } = props;
    return (
      <Typography component="li" variant="body1" sx={{ mb: 0.3, lineHeight: 1.6, fontSize: '1rem' }} {...safeProps}>
        {children}
      </Typography>
    );
  }
};

