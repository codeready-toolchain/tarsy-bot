import { useState, useEffect } from 'react';
import { 
  Paper, 
  Typography, 
  Box, 
  Button, 
  Alert, 
  AlertTitle,
  Snackbar
} from '@mui/material';
import { 
  Psychology, 
  ContentCopy, 
  ExpandMore, 
  ExpandLess 
} from '@mui/icons-material';
import ReactMarkdown from 'react-markdown';
import type { FinalAnalysisCardProps } from '../types';
import CopyButton from './CopyButton';

/**
 * FinalAnalysisCard component - Phase 3
 * Renders AI analysis markdown content with expand/collapse functionality and copy-to-clipboard feature
 * Optimized for live updates
 */
function FinalAnalysisCard({ analysis, sessionStatus, errorMessage }: FinalAnalysisCardProps) {
  const [analysisExpanded, setAnalysisExpanded] = useState<boolean>(false);
  const [copySuccess, setCopySuccess] = useState<boolean>(false);
  const [prevAnalysis, setPrevAnalysis] = useState<string | null>(null);
  const [isNewlyUpdated, setIsNewlyUpdated] = useState<boolean>(false);

  // Auto-expand when analysis first becomes available or changes significantly
  useEffect(() => {
    if (analysis && analysis !== prevAnalysis) {
      // If this is the first time analysis appears, or if it's significantly different
      const isFirstTime = !prevAnalysis && analysis;
      const isSignificantChange = prevAnalysis && analysis && 
        Math.abs(analysis.length - prevAnalysis.length) > 100;
      
      if (isFirstTime) {
        console.log('🎯 Final analysis first received, auto-expanding');
        setAnalysisExpanded(true);
        setIsNewlyUpdated(true);
      } else if (isSignificantChange) {
        console.log('🎯 Final analysis significantly updated');
        setIsNewlyUpdated(true);
      }
      
      setPrevAnalysis(analysis);
      
      // Clear the "newly updated" indicator after a few seconds
      if (isFirstTime || isSignificantChange) {
        const timer = setTimeout(() => {
          setIsNewlyUpdated(false);
        }, 3000);
        
        return () => clearTimeout(timer);
      }
    }
  }, [analysis, prevAnalysis]);

  // Handle copy to clipboard
  const handleCopyAnalysis = async () => {
    if (!analysis) return;
    
    try {
      await navigator.clipboard.writeText(analysis);
      setCopySuccess(true);
    } catch (error) {
      console.error('Failed to copy analysis:', error);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = analysis;
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

  // Show error state if session failed and no analysis available
  if (sessionStatus === 'failed' && !analysis && errorMessage) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Psychology color="primary" />
          Final AI Analysis
        </Typography>
        
        <Alert severity="error" sx={{ mt: 2 }}>
          <AlertTitle>Processing Error</AlertTitle>
          <Typography variant="body2">
            Session failed before analysis could be completed.
          </Typography>
          <Typography variant="body2" sx={{ mt: 1, fontFamily: 'monospace', fontSize: '0.875rem' }}>
            {errorMessage}
          </Typography>
        </Alert>
      </Paper>
    );
  }

  // Hide entirely if no analysis available - don't show empty state
  if (!analysis) {
    return null;
  }

  const isLongAnalysis = analysis.length > 1000;
  const shouldShowExpandButton = isLongAnalysis && !analysisExpanded;

  return (
    <>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Psychology color="primary" />
            Final AI Analysis
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
          </Typography>
          <Button
            startIcon={<ContentCopy />}
            variant="outlined"
            size="small"
            onClick={handleCopyAnalysis}
          >
            Copy Analysis
          </Button>
        </Box>

        {/* Analysis Content with Expand/Collapse */}
        <Box sx={{ position: 'relative' }}>
          <Box 
            sx={{ 
              maxHeight: analysisExpanded ? 'none' : isLongAnalysis ? '400px' : 'none',
              overflow: 'hidden',
              transition: 'max-height 0.3s ease-in-out'
            }}
          >
            <Paper 
              variant="outlined" 
              sx={{ 
                p: 3, 
                bgcolor: 'grey.50'
              }}
            >
              <ReactMarkdown
                components={{
                  // Custom styling for markdown elements
                  h1: ({ children }) => (
                    <Typography variant="h5" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold' }}>
                      {children}
                    </Typography>
                  ),
                  h2: ({ children }) => (
                    <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 2 }}>
                      {children}
                    </Typography>
                  ),
                  h3: ({ children }) => (
                    <Typography variant="subtitle1" gutterBottom sx={{ color: 'primary.main', fontWeight: 'bold', mt: 1.5 }}>
                      {children}
                    </Typography>
                  ),
                  p: ({ children }) => (
                    <Typography 
                      variant="body1" 
                      sx={{ 
                        lineHeight: 1.6,
                        fontSize: '0.95rem',
                        mb: 1
                      }}
                    >
                      {children}
                    </Typography>
                  ),
                  ul: ({ children }) => (
                    <Box component="ul" sx={{ pl: 2, mb: 1 }}>
                      {children}
                    </Box>
                  ),
                  li: ({ children }) => (
                    <Typography component="li" variant="body1" sx={{ fontSize: '0.95rem', lineHeight: 1.6, mb: 0.5 }}>
                      {children}
                    </Typography>
                  ),
                  code: ({ children, className }) => {
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
                        >
                          {children}
                        </Typography>
                      );
                    }
                  },
                  strong: ({ children }) => (
                    <Typography component="strong" sx={{ fontWeight: 'bold' }}>
                      {children}
                    </Typography>
                  ),
                  blockquote: ({ children }) => (
                    <Box sx={{
                      borderLeft: '4px solid',
                      borderColor: 'primary.main',
                      pl: 2,
                      ml: 0,
                      fontStyle: 'italic',
                      color: 'text.secondary',
                      mb: 1
                    }}>
                      {children}
                    </Box>
                  )
                }}
              >
                {analysis}
              </ReactMarkdown>
            </Paper>
          </Box>

          {/* Fade overlay and expand button when collapsed */}
          {shouldShowExpandButton && (
            <>
              <Box
                sx={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: '80px',
                  background: 'linear-gradient(transparent, white)',
                  pointerEvents: 'none'
                }}
              />
              <Box sx={{ textAlign: 'center', mt: 1 }}>
                <Button
                  variant="text"
                  startIcon={<ExpandMore />}
                  onClick={() => setAnalysisExpanded(true)}
                >
                  Show Full Analysis
                </Button>
              </Box>
            </>
          )}

          {/* Collapse button when expanded */}
          {analysisExpanded && isLongAnalysis && (
            <Box sx={{ textAlign: 'center', mt: 1 }}>
              <Button
                variant="text"
                startIcon={<ExpandLess />}
                onClick={() => setAnalysisExpanded(false)}
              >
                Show Less
              </Button>
            </Box>
          )}
        </Box>

        {/* Error message for failed sessions with analysis */}
        {sessionStatus === 'failed' && errorMessage && (
          <Alert severity="error" sx={{ mt: 2 }}>
            <AlertTitle>Session completed with errors</AlertTitle>
            <Typography variant="body2">
              {errorMessage}
            </Typography>
          </Alert>
        )}
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