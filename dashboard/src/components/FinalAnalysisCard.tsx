import { useState, useEffect, forwardRef } from 'react';
import { 
  Paper, 
  Typography, 
  Box, 
  Button, 
  Alert, 
  AlertTitle,
  Snackbar,
  Collapse,
  IconButton
} from '@mui/material';
import { 
  Psychology, 
  ContentCopy, 
  ExpandMore,
  AutoAwesome 
} from '@mui/icons-material';
import { alpha } from '@mui/material/styles';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import type { FinalAnalysisCardProps } from '../types';
import CopyButton from './CopyButton';
import { isTerminalSessionStatus, SESSION_STATUS } from '../utils/statusConstants';

/**
 * Generate a fake analysis message for terminal sessions without analysis
 */
function generateFakeAnalysis(status: string, errorMessage?: string | null): string {
  switch (status) {
    case SESSION_STATUS.CANCELLED:
      return `# Session Cancelled

This analysis session was cancelled before completion. No final analysis is available.

**Status:** Session was terminated by user request or system intervention.

If you need to investigate this alert, please submit a new analysis session.`;

    case SESSION_STATUS.FAILED:
      return `# Session Failed

This analysis session failed before completion. No final analysis could be generated.

**Error Details:**
${errorMessage ? `\`\`\`\n${errorMessage}\n\`\`\`` : '_No error details available_'}

Please review the session logs or submit a new analysis session.`;

    case SESSION_STATUS.COMPLETED:
      return `# Analysis Completed

This session completed successfully, but no final analysis was generated.

**Note:** This may indicate an issue with the analysis generation process. Please check the session stages for more details.`;

    default:
      return `# No Analysis Available

This session has reached a terminal state (${status}), but no final analysis is available.

Please review the session details or contact support if this is unexpected.`;
  }
}

/**
 * FinalAnalysisCard component - Phase 3
 * Renders AI analysis markdown content with expand/collapse functionality and copy-to-clipboard feature
 * Includes optional executive summary at the top (always visible)
 * Optimized for live updates
 */
const FinalAnalysisCard = forwardRef<HTMLDivElement, FinalAnalysisCardProps>(({ analysis, summary, sessionStatus, errorMessage, collapseCounter = 0, expandCounter = 0 }, ref) => {
  const [analysisExpanded, setAnalysisExpanded] = useState<boolean>(false);
  const [copySuccess, setCopySuccess] = useState<boolean>(false);
  const [prevAnalysis, setPrevAnalysis] = useState<string | null>(null);
  const [isNewlyUpdated, setIsNewlyUpdated] = useState<boolean>(false);

  // Auto-collapse when collapseCounter changes (e.g., when Jump to Chat is clicked)
  useEffect(() => {
    if (collapseCounter > 0) {
      setAnalysisExpanded(false);
    }
  }, [collapseCounter]);

  // Auto-expand when expandCounter changes (e.g., when Jump to Final Analysis is clicked)
  useEffect(() => {
    if (expandCounter > 0) {
      setAnalysisExpanded(true);
    }
  }, [expandCounter]);

  // Auto-expand when analysis first becomes available or changes significantly
  // Only show "Updated" indicator during active processing, not for historical sessions
  useEffect(() => {
    if (analysis && analysis !== prevAnalysis) {
      // Check if session is actively being processed
      const isActiveSession = sessionStatus === SESSION_STATUS.IN_PROGRESS || sessionStatus === SESSION_STATUS.PENDING;
      
      // If this is the first time analysis appears, or if it's significantly different
      const isFirstTime = !prevAnalysis && analysis;
      const isSignificantChange = prevAnalysis && analysis && 
        Math.abs(analysis.length - prevAnalysis.length) > 100;
      
      if (isFirstTime) {
        setAnalysisExpanded(true);
        // Only show "Updated" indicator if session is actively processing
        if (isActiveSession) {
          setIsNewlyUpdated(true);
        }
      } else if (isSignificantChange) {
        // Only show "Updated" indicator if session is actively processing
        if (isActiveSession) {
          setIsNewlyUpdated(true);
        }
      }
      
      setPrevAnalysis(analysis);
      
      // Clear the "newly updated" indicator after a few seconds
      if ((isFirstTime || isSignificantChange) && isActiveSession) {
        const timer = setTimeout(() => {
          setIsNewlyUpdated(false);
        }, 3000);
        
        return () => clearTimeout(timer);
      }
    }
  }, [analysis, prevAnalysis, sessionStatus]);

  // Handle copy to clipboard
  const handleCopyAnalysis = async (textToCopy: string) => {
    if (!textToCopy) return;
    
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopySuccess(true);
    } catch (error) {
      console.error('Failed to copy analysis:', error);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = textToCopy;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopySuccess(true);
    }
  };

  // Handle snackbar close
  const handleSnackbarClose = () => {
    setCopySuccess(false);
  };

  // Determine the actual analysis to display
  // For terminal sessions without analysis, generate a fake one
  const displayAnalysis = analysis || 
    (isTerminalSessionStatus(sessionStatus) ? generateFakeAnalysis(sessionStatus, errorMessage) : null);
  
  // If session is still active and no analysis yet, hide the card
  if (!displayAnalysis) {
    return null;
  }

  // Check if this is a fake analysis (for styling purposes)
  const isFakeAnalysis = !analysis && isTerminalSessionStatus(sessionStatus);

  return (
    <>
      <Paper ref={ref} sx={{ p: 3 }}>
        {/* Collapsible Header */}
        <Box 
          sx={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center', 
            mb: analysisExpanded ? 2 : 0,
            cursor: 'pointer',
            '&:hover': {
              opacity: 0.8
            }
          }}
          onClick={() => setAnalysisExpanded(!analysisExpanded)}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Box
              sx={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                bgcolor: (theme) => alpha(theme.palette.primary.main, 0.15),
                border: '2px solid',
                borderColor: 'primary.main',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Psychology sx={{ fontSize: 24, color: 'primary.main' }} />
            </Box>
            <Typography variant="h6">
              Final AI Analysis
            </Typography>
            {isNewlyUpdated && (
              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  bgcolor: 'success.main',
                  color: 'white',
                  px: 1,
                  py: 0.25,
                  borderRadius: 1,
                  fontSize: '0.75rem',
                  fontWeight: 'medium',
                  animation: 'pulse 2s ease-in-out infinite',
                  '@keyframes pulse': {
                    '0%': {
                      opacity: 1,
                    },
                    '50%': {
                      opacity: 0.7,
                    },
                    '100%': {
                      opacity: 1,
                    },
                  }
                }}
              >
                ✨ Updated
              </Box>
            )}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Button
              startIcon={<ContentCopy />}
              variant="outlined"
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                handleCopyAnalysis(displayAnalysis);
              }}
            >
              Copy {isFakeAnalysis ? 'Message' : 'Analysis'}
            </Button>
            <IconButton 
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                setAnalysisExpanded(!analysisExpanded);
              }}
              sx={{ 
                transition: 'transform 0.4s',
                transform: analysisExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
              }}
            >
              <ExpandMore />
            </IconButton>
          </Box>
        </Box>

        {/* AI-Generated Content Warning - always visible when we have real analysis */}
        {!isFakeAnalysis && (summary || displayAnalysis) && (
          <Alert 
            severity="info" 
            icon={<AutoAwesome />}
            sx={{ 
              mt: 2,
              bgcolor: (theme) => alpha(theme.palette.info.main, 0.04),
              border: '1px solid',
              borderColor: (theme) => alpha(theme.palette.info.main, 0.2),
              '& .MuiAlert-icon': {
                color: 'info.main'
              }
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                AI-Generated Content
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Always review AI generated content prior to use.
              </Typography>
            </Box>
          </Alert>
        )}

        {/* Executive Summary - Always visible when available */}
        {summary && (
          <Box sx={{ mt: 2 }}>
            <Box sx={{
              bgcolor: (theme) => alpha(theme.palette.success.main, 0.04),
              border: '1px solid',
              borderColor: (theme) => alpha(theme.palette.success.main, 0.25),
              borderRadius: 2,
              p: 2.5,
              position: 'relative',
              overflow: 'hidden',
              // Subtle gradient accent on the left edge
              '&::before': {
                content: '""',
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: 4,
                bgcolor: 'success.main',
                borderRadius: '4px 0 0 4px'
              }
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <AutoAwesome sx={{ color: 'success.main', fontSize: 20 }} />
                <Typography 
                  variant="subtitle2" 
                  sx={{ 
                    fontWeight: 700,
                    color: 'success.main',
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                    fontSize: '0.8rem'
                  }}
                >
                  Executive Summary
                </Typography>
              </Box>
              <Box sx={{
                // Ensure markdown content renders inline properly
                '& p': {
                  margin: 0,
                  marginBottom: 1,
                  lineHeight: 1.7,
                  fontSize: '0.95rem',
                  color: 'text.primary',
                  '&:last-child': { marginBottom: 0 }
                },
                '& strong': {
                  fontWeight: 'bold'
                },
                '& em': {
                  fontStyle: 'italic'
                },
                // Inline code styling - using native CSS for proper inline behavior
                '& code': {
                  fontFamily: '"JetBrains Mono", "Fira Code", "SF Mono", Consolas, monospace',
                  fontSize: '0.875em',
                  backgroundColor: (theme) => alpha(theme.palette.grey[900], 0.08),
                  color: 'error.main',
                  padding: '1px 6px',
                  borderRadius: '4px',
                  border: '1px solid',
                  borderColor: (theme) => alpha(theme.palette.grey[900], 0.12),
                  whiteSpace: 'nowrap',
                  verticalAlign: 'baseline'
                },
                // Block code
                '& pre': {
                  display: 'block',
                  fontFamily: '"JetBrains Mono", "Fira Code", "SF Mono", Consolas, monospace',
                  fontSize: '0.875em',
                  backgroundColor: (theme) => alpha(theme.palette.grey[900], 0.06),
                  padding: 1.5,
                  borderRadius: 1,
                  overflowX: 'auto',
                  margin: '8px 0',
                  '& code': {
                    backgroundColor: 'transparent',
                    border: 'none',
                    padding: 0,
                    whiteSpace: 'pre'
                  }
                }
              }}>
                <ReactMarkdown>
                  {summary}
                </ReactMarkdown>
              </Box>
            </Box>
          </Box>
        )}

        {/* Collapsible Content - Full Detailed Analysis */}
        <Collapse in={analysisExpanded} timeout={400}>
          {/* Section header divider when summary exists */}
          {summary && displayAnalysis && (
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 2, 
              mt: 3,
              mb: 2,
              color: 'text.secondary'
            }}>
              <Box sx={{ flex: 1, height: '1px', bgcolor: 'divider' }} />
              <Typography 
                variant="caption" 
                sx={{ 
                  fontSize: '0.75rem',
                  textTransform: 'uppercase',
                  letterSpacing: 1,
                  fontWeight: 600,
                  color: 'text.disabled'
                }}
              >
                Full Detailed Analysis
              </Typography>
              <Box sx={{ flex: 1, height: '1px', bgcolor: 'divider' }} />
            </Box>
          )}
          
          {/* Status indicator for fake analysis */}
          {isFakeAnalysis && (
            <Alert 
              severity="warning" 
              sx={{ mb: 2 }}
            >
              <Typography variant="body2">
                This session did not complete successfully.
              </Typography>
            </Alert>
          )}

          {/* Analysis Content */}
          <Box sx={{ position: 'relative' }}>
            <Paper 
              variant="outlined" 
              sx={{ 
                p: 3, 
                bgcolor: 'grey.50'
              }}
            >
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
                {displayAnalysis}
              </ReactMarkdown>
            </Paper>
          </Box>

          {/* Error message for failed sessions with real analysis (not fake) */}
          {sessionStatus === SESSION_STATUS.FAILED && errorMessage && !isFakeAnalysis && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <AlertTitle>Session completed with errors</AlertTitle>
              <Typography variant="body2">
                {errorMessage}
              </Typography>
            </Alert>
          )}
        </Collapse>
      </Paper>

      {/* Copy success snackbar */}
      <Snackbar
        open={copySuccess}
        autoHideDuration={3000}
        onClose={handleSnackbarClose}
        message="Analysis copied to clipboard"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </>
  );
});

FinalAnalysisCard.displayName = 'FinalAnalysisCard';

export default FinalAnalysisCard; 