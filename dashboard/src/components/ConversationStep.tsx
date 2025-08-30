import React, { useState } from 'react';
import {
  Box,
  Typography,
  Collapse,
  IconButton,
  Chip
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  Error as ErrorIcon
} from '@mui/icons-material';
import ReactMarkdown from 'react-markdown';
import type { ConversationStepData } from '../utils/conversationParser';
import CopyButton from './CopyButton';
import JsonDisplay from './JsonDisplay';

interface ConversationStepProps {
  step: ConversationStepData;
  stepIndex: number;
  isLastStep: boolean;
}

// Helper function to get step emoji and styling
const getStepStyle = (type: string, success: boolean = true) => {
  switch (type) {
    case 'thought':
      return {
        emoji: '💭',
        color: 'text.primary',
        bgColor: 'transparent'
      };
    case 'action':
      return {
        emoji: '🔧',
        color: success ? 'primary.main' : 'error.main',
        bgColor: success ? 'primary.light' : 'error.light'
      };
    case 'analysis':
      return {
        emoji: '🎯',
        color: 'success.main',
        bgColor: 'success.light'
      };
    case 'summarization':
      return {
        emoji: '📋',
        color: 'info.main',
        bgColor: 'info.light'
      };
    case 'error':
      return {
        emoji: '❌',
        color: 'error.main',
        bgColor: 'transparent'
      };
    default:
      return {
        emoji: '•',
        color: 'text.secondary',
        bgColor: 'transparent'
      };
  }
};

/**
 * Individual conversation step component
 * Displays thoughts, actions, analysis, and errors with appropriate styling
 */
function ConversationStep({ 
  step, 
  stepIndex, 
  isLastStep 
}: ConversationStepProps) {
  const [isActionExpanded, setIsActionExpanded] = useState(false);
  const [isAnalysisExpanded, setIsAnalysisExpanded] = useState(false);
  const [isSummarizationExpanded, setIsSummarizationExpanded] = useState(false);
  
  const style = getStepStyle(step.type, step.success);
  const hasActionDetails = step.type === 'action' && (step.actionName || step.actionResult);
  const isActionSuccess = step.success && !(
    step.actionResult instanceof Error ||
    (typeof step.actionResult === 'string' && step.actionResult.startsWith('Error:')) ||
    (step.actionResult != null && typeof step.actionResult !== 'string' && String(step.actionResult).startsWith('Error:'))
  );

  const toggleActionExpansion = () => {
    setIsActionExpanded(prev => !prev);
  };

  const toggleAnalysisExpansion = () => {
    setIsAnalysisExpanded(prev => !prev);
  };

  const toggleSummarizationExpansion = () => {
    setIsSummarizationExpanded(prev => !prev);
  };

  const formatActionResult = (result: any): string => {
    if (typeof result === 'string') {
      return result;
    }
    if (typeof result === 'object' && result !== null) {
      return JSON.stringify(result, null, 2);
    }
    return result?.toString() || 'No result';
  };

  const getCopyText = (): string => {
    let text = `${style.emoji} ${step.content}`;
    
    if (step.type === 'action' && step.actionName) {
      text += `\n🔧 ${step.actionName}${step.actionInput ? ` ${step.actionInput}` : ''}`;
      
      if (step.actionResult) {
        text += `\n└─ ${formatActionResult(step.actionResult)}`;
      }
    }
    
    return text;
  };

  return (
    <Box sx={{
      py: 2,
      px: 2,
      mb: 1,
      borderRadius: 2,
      backgroundColor: stepIndex % 2 === 0 ? 'grey.50' : 'background.paper',
      border: '1px solid',
      borderColor: 'divider',
      '&:hover': {
        backgroundColor: stepIndex % 2 === 0 ? 'grey.50' : 'action.hover',
        borderColor: 'primary.light'
      }
    }}>
      {/* Step Content */}
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
        {/* Emoji Icon */}
        <Typography 
          variant="h6" 
          sx={{ 
            fontSize: '1.25rem',
            minWidth: 28,
            lineHeight: 1.5,
            userSelect: 'none'
          }}
        >
          {style.emoji}
        </Typography>
        
        {/* Step Text and Details */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Main Content */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1 }}>
            {/* Conditionally render based on step type */}
            {step.type === 'analysis' ? (
              <Box sx={{ flex: 1, minWidth: 0 }}>
                {/* Analysis Summary with Expand/Collapse */}
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography 
                    variant="body1" 
                    sx={{ 
                      lineHeight: 1.6,
                      fontSize: '0.95rem',
                      color: style.color,
                      flex: 1,
                      fontWeight: 'medium'
                    }}
                  >
                    {isAnalysisExpanded ? 'Final Analysis Report' : `Final Analysis Report (${Math.round(step.content.length / 100) / 10}k chars)`}
                  </Typography>
                  
                  <IconButton
                    onClick={toggleAnalysisExpansion}
                    size="small"
                    sx={{ 
                      color: style.color,
                      '&:hover': { backgroundColor: `${style.color}15` }
                    }}
                  >
                    {isAnalysisExpanded ? <ExpandLess /> : <ExpandMore />}
                  </IconButton>
                </Box>

                {/* Collapsible Full Analysis */}
                <Collapse in={isAnalysisExpanded}>
                  <Box sx={{ mt: 1 }}>
                    <ReactMarkdown
                      components={{
                        // Custom styling for markdown elements
                        h1: ({ children }) => (
                          <Typography variant="h5" gutterBottom sx={{ color: style.color, fontWeight: 'bold' }}>
                            {children}
                          </Typography>
                        ),
                        h2: ({ children }) => (
                          <Typography variant="h6" gutterBottom sx={{ color: style.color, fontWeight: 'bold', mt: 2 }}>
                            {children}
                          </Typography>
                        ),
                        h3: ({ children }) => (
                          <Typography variant="subtitle1" gutterBottom sx={{ color: style.color, fontWeight: 'bold', mt: 1.5 }}>
                            {children}
                          </Typography>
                        ),
                        p: ({ children }) => (
                          <Typography 
                            variant="body1" 
                            sx={{ 
                              lineHeight: 1.6,
                              fontSize: '0.95rem',
                              color: style.color,
                              mb: 1
                            }}
                          >
                            {children}
                          </Typography>
                        ),
                        ul: ({ children }) => (
                          <Box component="ul" sx={{ pl: 2, mb: 1, color: style.color }}>
                            {children}
                          </Box>
                        ),
                        li: ({ children }) => (
                          <Typography component="li" variant="body1" sx={{ fontSize: '0.95rem', lineHeight: 1.6, mb: 0.5 }}>
                            {children}
                          </Typography>
                        ),
                        code: ({ children, className }) => (
                          <Typography
                            component={className?.includes('language-') ? 'pre' : 'code'}
                            sx={{
                              fontFamily: 'monospace',
                              fontSize: '0.85rem',
                              backgroundColor: 'rgba(0, 0, 0, 0.04)',
                              padding: className?.includes('language-') ? 1 : 0.5,
                              borderRadius: 1,
                              display: className?.includes('language-') ? 'block' : 'inline',
                              whiteSpace: className?.includes('language-') ? 'pre' : 'pre-wrap',
                              overflow: 'auto'
                            }}
                          >
                            {children}
                          </Typography>
                        ),
                        strong: ({ children }) => (
                          <Typography component="strong" sx={{ fontWeight: 'bold', color: style.color }}>
                            {children}
                          </Typography>
                        )
                      }}
                    >
                      {step.content}
                    </ReactMarkdown>
                  </Box>
                </Collapse>
              </Box>
            ) : step.type === 'summarization' ? (
              <Box sx={{ flex: 1, minWidth: 0 }}>
                {/* Summarized Result Summary with Expand/Collapse */}
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography
                    variant="body1"
                    sx={{
                      lineHeight: 1.6,
                      fontSize: '0.95rem',
                      color: style.color,
                      flex: 1,
                      fontWeight: 'medium'
                    }}
                  >
                    {isSummarizationExpanded ? 'Summarized Result' : `Summarized Result (${Math.round(step.content.length / 100) / 10}k chars)`}
                  </Typography>
                  
                  <IconButton
                    onClick={toggleSummarizationExpansion}
                    size="small"
                    sx={{ 
                      color: style.color,
                      '&:hover': { backgroundColor: `${style.color}15` }
                    }}
                  >
                    {isSummarizationExpanded ? <ExpandLess /> : <ExpandMore />}
                  </IconButton>
                </Box>

                {/* Collapsible Summarized Content */}
                <Collapse in={isSummarizationExpanded}>
                  <Box sx={{ mt: 1 }}>
                <Box>
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => (
                        <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1, color: style.color }}>
                          {children}
                        </Typography>
                      ),
                      h2: ({ children }) => (
                        <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1, color: style.color }}>
                          {children}
                        </Typography>
                      ),
                      h3: ({ children }) => (
                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5, color: style.color }}>
                          {children}
                        </Typography>
                      ),
                      p: ({ children }) => (
                        <Typography 
                          variant="body1" 
                          sx={{ 
                            lineHeight: 1.6,
                            fontSize: '0.9rem',
                            color: style.color,
                            mb: 1
                          }}
                        >
                          {children}
                        </Typography>
                      ),
                      ul: ({ children }) => (
                        <Box component="ul" sx={{ pl: 2, mb: 1, color: style.color }}>
                          {children}
                        </Box>
                      ),
                      li: ({ children }) => (
                        <Typography component="li" variant="body1" sx={{ fontSize: '0.9rem', lineHeight: 1.6, mb: 0.5 }}>
                          {children}
                        </Typography>
                      ),
                      code: ({ children, className }) => (
                        <Typography
                          component={className?.includes('language-') ? 'pre' : 'code'}
                          sx={{
                            fontFamily: 'monospace',
                            fontSize: '0.8rem',
                            backgroundColor: 'rgba(0, 0, 0, 0.04)',
                            padding: className?.includes('language-') ? 1 : 0.5,
                            borderRadius: 1,
                            display: className?.includes('language-') ? 'block' : 'inline',
                            whiteSpace: className?.includes('language-') ? 'pre' : 'pre-wrap',
                            overflow: 'auto'
                          }}
                        >
                          {children}
                        </Typography>
                      ),
                      strong: ({ children }) => (
                        <Typography component="strong" sx={{ fontWeight: 'bold', color: style.color }}>
                          {children}
                        </Typography>
                      )
                    }}
                  >
                    {step.content}
                  </ReactMarkdown>
                </Box>
                  </Box>
                </Collapse>
              </Box>
            ) : (
              <Typography
                variant="body1"
                sx={{
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.6,
                  fontSize: '0.95rem',
                  color: style.color,
                  flex: 1
                }}
              >
                {step.content}
              </Typography>
            )}
            
            {/* Copy Button */}
            <CopyButton
              text={getCopyText()}
              variant="icon"
              size="small"
              tooltip="Copy step content"
            />
          </Box>

          {/* Error Message for Failed Steps */}
          {step.type === 'error' && step.errorMessage && (
            <Box sx={{ 
              mt: 1,
              p: 1,
              bgcolor: 'grey.100',
              borderRadius: 1,
              border: '1px solid',
              borderColor: 'error.main',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1
            }}>
              <ErrorIcon sx={{ color: 'error.main', fontSize: '1rem', mt: 0.125 }} />
              <Typography 
                variant="body2" 
                sx={{ 
                  color: 'error.main',
                  fontFamily: 'monospace',
                  fontSize: '0.875rem',
                  wordBreak: 'break-word',
                  whiteSpace: 'pre-wrap'
                }}
              >
                {step.errorMessage}
              </Typography>
            </Box>
          )}

          {/* Action Details */}
          {hasActionDetails && (
            <Box sx={{ mt: 1 }}>
              {/* Action Header - More Conversational Style */}
              <Box sx={{ 
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                cursor: 'pointer',
                py: 1,
                px: 1.5,
                bgcolor: 'action.hover',
                borderRadius: 2,
                border: '1px solid',
                borderColor: 'divider',
                '&:hover': {
                  bgcolor: 'action.selected',
                  borderColor: 'primary.main'
                },
                transition: 'all 0.2s ease-in-out'
              }}
              onClick={toggleActionExpansion}
              >
                <Box sx={{ 
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  bgcolor: isActionSuccess ? 'success.main' : 'error.main'
                }} />
                
                <Typography 
                  variant="body2" 
                  sx={{ 
                    color: 'text.primary',
                    fontWeight: 500,
                    fontSize: '0.875rem',
                    flex: 1
                  }}
                >
                  <Typography component="span" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                    {step.actionName}
                  </Typography>
                  {step.actionInput && (
                    <Typography component="span" sx={{ color: 'text.secondary', ml: 1 }}>
                      {step.actionInput}
                    </Typography>
                  )}
                </Typography>
                
                <Chip
                  size="small"
                  label={isActionSuccess ? 'Success' : 'Failed'}
                  variant="outlined"
                  color={isActionSuccess ? 'success' : 'error'}
                  sx={{ 
                    height: 24,
                    fontSize: '0.75rem'
                  }}
                />
                
                <IconButton 
                  size="small"
                  sx={{ 
                    p: 0.5,
                    color: 'text.secondary'
                  }}
                >
                  {isActionExpanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                </IconButton>
              </Box>

              {/* Expandable Result - Cleaner Style */}
              <Collapse in={isActionExpanded}>
                <Box sx={{ 
                  mt: 1,
                  borderRadius: 2,
                  overflow: 'hidden',
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'background.default'
                }}>
                  {/* Result Header */}
                  <Box sx={{ 
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    px: 1.5,
                    py: 1,
                    bgcolor: 'grey.50',
                    borderBottom: '1px solid',
                    borderColor: 'divider'
                  }}>
                    <Typography 
                      variant="body2" 
                      sx={{ 
                        fontWeight: 600,
                        color: 'text.secondary',
                        fontSize: '0.875rem'
                      }}
                    >
                      📋 Action Result
                    </Typography>
                    <CopyButton
                      text={formatActionResult(step.actionResult)}
                      variant="icon"
                      size="small"
                      tooltip="Copy result"
                    />
                  </Box>
                  
                  {/* Result Content */}
                  <Box sx={{ p: 1.5, bgcolor: 'background.paper' }}>
                    {typeof step.actionResult === 'object' && step.actionResult !== null ? (
                      <JsonDisplay 
                        data={step.actionResult} 
                        collapsed={false}
                        maxHeight={300}
                      />
                    ) : (
                      <Typography 
                        variant="body2" 
                        sx={{ 
                          fontFamily: 'monospace',
                          whiteSpace: 'pre-wrap',
                          fontSize: '0.875rem',
                          color: 'text.primary',
                          lineHeight: 1.4,
                          backgroundColor: 'grey.50',
                          p: 1.5,
                          borderRadius: 1,
                          border: '1px solid',
                          borderColor: 'divider'
                        }}
                      >
                        {formatActionResult(step.actionResult)}
                      </Typography>
                    )}
                  </Box>
                </Box>
              </Collapse>
            </Box>
          )}
        </Box>
      </Box>

      {/* Step Divider */}
      {!isLastStep && (
        <Box sx={{ 
          height: 1, 
          bgcolor: 'divider', 
          my: 2,
          ml: 3.5, // Align with content, offset by emoji width
          opacity: 0.3
        }} />
      )}
    </Box>
  );
}

// Wrap with React.memo to prevent unnecessary re-renders of individual conversation steps
export default React.memo(ConversationStep, (prevProps, nextProps) => {
  // Custom comparison function to optimize re-renders
  return (
    prevProps.step.content === nextProps.step.content &&
    prevProps.step.type === nextProps.step.type &&
    prevProps.step.success === nextProps.step.success &&
    prevProps.step.actionResult === nextProps.step.actionResult &&
    prevProps.stepIndex === nextProps.stepIndex &&
    prevProps.isLastStep === nextProps.isLastStep
  );
});
