import { useState, useEffect } from 'react';
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
 * Optimized for live updates
 */
function FinalAnalysisCard({ analysis, sessionStatus, errorMessage, collapseCounter = 0, expandCounter = 0 }: FinalAnalysisCardProps) {
  const [analysisExpanded, setAnalysisExpanded] = useState<boolean>(false);
  const [copySuccess, setCopySuccess] = useState<boolean>(false);
  const [prevAnalysis, setPrevAnalysis] = useState<string | null>(null);
  const [isNewlyUpdated, setIsNewlyUpdated] = useState<boolean>(false);

  // Auto-collapse when collapseCounter changes (e.g., when Jump to Chat is clicked)
  useEffect(() => {
    if (collapseCounter > 0) {
      console.log('📦 Auto-collapsing Final Analysis (Jump to Chat clicked)');
      setAnalysisExpanded(false);
    }
  }, [collapseCounter]);

  // Auto-expand when expandCounter changes (e.g., when Jump to Final Analysis is clicked)
  useEffect(() => {
    if (expandCounter > 0) {
      console.log('📂 Auto-expanding Final Analysis (Jump to Final Analysis clicked)');
      setAnalysisExpanded(true);
    }
  }, [expandCounter]);

  // Auto-expand when analysis first becomes available or changes significantly
  // Only show "Updated" indicator during active processing, not for historical sessions
  useEffect(() => {
    if (analysis && analysis !== prevAnalysis) {
      // Check if session is actively being processed
      const isActiveSession = sessionStatus === 'in_progress' || sessionStatus === 'pending';
      
      // If this is the first time analysis appears, or if it's significantly different
      const isFirstTime = !prevAnalysis && analysis;
      const isSignificantChange = prevAnalysis && analysis && 
        Math.abs(analysis.length - prevAnalysis.length) > 100;
      
      if (isFirstTime) {
        console.log('🎯 Final analysis first received, auto-expanding');
        setAnalysisExpanded(true);
        // Only show "Updated" indicator if session is actively processing
        if (isActiveSession) {
          setIsNewlyUpdated(true);
        }
      } else if (isSignificantChange) {
        console.log('🎯 Final analysis significantly updated');
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
      <Paper id="final-analysis-card" sx={{ p: 3 }}>
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
                transition: 'transform 0.3s',
                transform: analysisExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
              }}
            >
              <ExpandMore />
            </IconButton>
          </Box>
        </Box>

        {/* Collapsible Content */}
        <Collapse in={analysisExpanded} timeout={400}>
          {/* AI-Generated Content Warning - only show for real analysis */}
          {!isFakeAnalysis && (
            <Alert 
              severity="info" 
              icon={<AutoAwesome />}
              sx={{ mb: 2 }}
            >
              <Box>
                <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5, fontSize: '1rem' }}>
                  AI-Generated Content
                </Typography>
                <Typography variant="body1" sx={{ fontSize: '0.95rem' }}>
                  Always review AI generated content prior to use.
                </Typography>
              </Box>
            </Alert>
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
          {sessionStatus === 'failed' && errorMessage && !isFakeAnalysis && (
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
}

export default FinalAnalysisCard; 