import { Box, Collapse, Typography } from '@mui/material';
import { ExpandMore, ExpandLess } from '@mui/icons-material';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import type { Components, UrlTransform } from 'react-markdown';

interface CollapsibleContentBlockProps {
  content: string;
  shouldCollapse: boolean;
  shouldClampPreview: boolean;
  isClickable: boolean;
  isAutoCollapsing: boolean;
  contentRef: React.RefObject<HTMLDivElement | null>;
  onToggle: () => void;
  hasMarkdown: boolean;
  markdownComponents: Components;
  contentSx?: Record<string, unknown>;
  wrapperSx?: Record<string, unknown>;
  showExpandIndicator?: boolean;
  header?: React.ReactNode;
  urlTransform?: UrlTransform;
}

/**
 * Reusable component for collapsible content with smooth animations.
 * Handles:
 * - Collapse/expand animations
 * - Line clamping for preview
 * - Expand/collapse indicator
 */
export default function CollapsibleContentBlock({
  content,
  shouldCollapse,
  shouldClampPreview,
  isClickable,
  isAutoCollapsing,
  contentRef,
  onToggle,
  hasMarkdown,
  markdownComponents,
  contentSx = {},
  wrapperSx = {},
  showExpandIndicator = true,
  header,
  urlTransform = defaultUrlTransform,
}: CollapsibleContentBlockProps) {
  return (
    <Box
      sx={{
        cursor: isClickable ? 'pointer' : 'default',
        transition: 'background-color 0.2s ease',
        borderRadius: 1,
        px: isClickable ? 1 : 0,
        '&:hover': isClickable ? { bgcolor: 'action.hover' } : {},
        // Auto-collapse fade animation
        ...(isAutoCollapsing && {
          animation: 'fadeCollapse 0.6s ease-out',
          '@keyframes fadeCollapse': {
            '0%': { opacity: 1 },
            '50%': { opacity: 0.3 },
            '100%': { opacity: 1 },
          },
        }),
        ...wrapperSx,
      }}
      onClick={isClickable ? onToggle : undefined}
    >
      {header}
      
      <Collapse in={!shouldCollapse} timeout={300} collapsedSize="3.4rem">
        <Box
          ref={contentRef}
          sx={{
            // Apply line-clamp only when collapsed AND not animating
            ...(shouldClampPreview && {
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }),
          }}
        >
          {hasMarkdown ? (
            <Box sx={contentSx}>
              <ReactMarkdown
                urlTransform={urlTransform}
                components={markdownComponents}
                remarkPlugins={[remarkBreaks]}
                skipHtml
              >
                {content}
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
                ...contentSx,
              }}
            >
              {content}
            </Typography>
          )}
        </Box>
      </Collapse>

      {isClickable && showExpandIndicator && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            mt: 0.5,
            opacity: 0.6,
          }}
        >
          {shouldCollapse ? (
            <>
              <ExpandMore fontSize="small" />
              <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                See more
              </Typography>
            </>
          ) : (
            <ExpandLess fontSize="small" />
          )}
        </Box>
      )}
    </Box>
  );
}
