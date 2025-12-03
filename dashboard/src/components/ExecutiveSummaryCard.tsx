import { forwardRef } from 'react';
import { 
  Paper, 
  Typography, 
  Box
} from '@mui/material';
import { 
  AutoAwesome
} from '@mui/icons-material';
import { alpha } from '@mui/material/styles';
import ReactMarkdown from 'react-markdown';
import type { Session } from '../types';
import CopyButton from './CopyButton';

interface ExecutiveSummaryCardProps {
  summary: string | null;
  sessionStatus: Session['status'];
}

/**
 * ExecutiveSummaryCard component
 * Displays a compact executive summary before the full analysis
 * Always expanded, no collapse functionality
 */
const ExecutiveSummaryCard = forwardRef<HTMLDivElement, ExecutiveSummaryCardProps>(({ summary }, ref) => {
  
  // Don't render anything if no summary
  if (!summary) {
    return null;
  }

  return (
    <Paper
      ref={ref}
      elevation={3}
      sx={{
        mb: 3,
        overflow: 'hidden',
        border: '2px solid',
        borderColor: 'success.main',
        backgroundColor: (theme) => alpha(theme.palette.success.main, 0.03)
      }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 3,
          py: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid',
          borderColor: 'divider',
          backgroundColor: (theme) => alpha(theme.palette.success.main, 0.08)
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <AutoAwesome sx={{ color: 'success.main', fontSize: 28 }} />
          <Typography 
            variant="h6" 
            sx={{ 
              fontWeight: 600,
              color: 'success.main'
            }}
          >
            Executive Summary
          </Typography>
        </Box>
        
        {/* Copy button */}
        <CopyButton
          text={summary}
          variant="icon"
          size="small"
          tooltip="Copy executive summary to clipboard"
        />
      </Box>

      {/* Summary content */}
      <Box sx={{ px: 3, py: 2.5 }}>
        <Paper
          elevation={0}
          sx={{
            p: 2.5,
            backgroundColor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1
          }}
        >
          <ReactMarkdown
            components={{
              p: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography 
                    component="p" 
                    variant="body1" 
                    sx={{ 
                      mb: 1,
                      lineHeight: 1.7,
                      fontSize: '1rem',
                      '&:last-child': { mb: 0 }
                    }}
                    {...safeProps}
                  >
                    {children}
                  </Typography>
                );
              },
              strong: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography component="strong" sx={{ fontWeight: 'bold' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              em: (props) => {
                const { node, children, ...safeProps } = props;
                return (
                  <Typography component="em" sx={{ fontStyle: 'italic' }} {...safeProps}>
                    {children}
                  </Typography>
                );
              },
              code: (props: any) => {
                const { node, children, inline, ...safeProps } = props;
                if (inline) {
                  return (
                    <Typography
                      component="code"
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.9em',
                        backgroundColor: 'grey.100',
                        px: 0.5,
                        py: 0.25,
                        borderRadius: 0.5,
                      }}
                      {...safeProps}
                    >
                      {children}
                    </Typography>
                  );
                }
                return (
                  <Box
                    component="code"
                    sx={{
                      display: 'block',
                      fontFamily: 'monospace',
                      fontSize: '0.9em',
                      backgroundColor: 'grey.100',
                      p: 1,
                      borderRadius: 1,
                      overflowX: 'auto',
                    }}
                    {...safeProps}
                  >
                    {children}
                  </Box>
                );
              }
            }}
          >
            {summary}
          </ReactMarkdown>
        </Paper>
      </Box>
    </Paper>
  );
});

ExecutiveSummaryCard.displayName = 'ExecutiveSummaryCard';

export default ExecutiveSummaryCard;

