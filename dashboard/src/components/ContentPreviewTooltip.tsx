/**
 * ContentPreviewTooltip Component
 * Displays full content in a tooltip when hovering over truncated text
 * Supports markdown rendering for different content types
 */

import { Tooltip, Paper } from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { 
  thoughtMarkdownComponents, 
  finalAnswerMarkdownComponents 
} from '../utils/markdownComponents';

interface ContentPreviewTooltipProps {
  /** Full content to display in tooltip */
  content: string;
  /** Type of content (determines markdown rendering style) */
  type: 'thought' | 'final_answer' | 'summarization' | 'native_thinking';
  /** Child element that triggers the tooltip */
  children: React.ReactElement;
}

/**
 * Wraps truncated content with hover tooltip showing full content
 * Features:
 * - 300ms enter delay to avoid accidental triggers
 * - Max width 600px, max height 400px with scroll
 * - Renders full markdown using appropriate components
 * - Positioned top-start to avoid cursor interference
 */
export default function ContentPreviewTooltip({ 
  content, 
  type, 
  children 
}: ContentPreviewTooltipProps) {
  // Select appropriate markdown components based on content type
  const markdownComponents = type === 'final_answer' 
    ? finalAnswerMarkdownComponents 
    : thoughtMarkdownComponents;
  
  return (
    <Tooltip
      title={
        <Paper 
          elevation={3} 
          sx={{ 
            p: 2, 
            maxWidth: 600, 
            maxHeight: 400, 
            overflow: 'auto',
            bgcolor: 'background.paper'
          }}
        >
          <ReactMarkdown components={markdownComponents}>
            {content}
          </ReactMarkdown>
        </Paper>
      }
      enterDelay={300}
      placement="top-start"
      PopperProps={{
        sx: {
          '& .MuiTooltip-tooltip': {
            bgcolor: 'transparent',
            maxWidth: 'none',
            p: 0
          }
        }
      }}
    >
      {children}
    </Tooltip>
  );
}
