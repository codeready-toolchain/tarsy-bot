import { memo } from 'react';
import { Box, Typography, Chip } from '@mui/material';
import type { LLMInteraction, LLMMessage } from '../types';
import { parseThoughtAndAction } from '../utils/reactParser';

interface LLMInteractionPreviewProps {
  interaction: LLMInteraction;
  showFullPreview?: boolean;
}

// Helper to get interaction type styling
const getInteractionTypeStyle = (interactionType: string) => {
  switch (interactionType) {
    case 'investigation':
      return {
        label: 'Investigation',
        color: 'primary' as const,
        bgColor: 'rgba(25, 118, 210, 0.08)',
        borderColor: 'rgba(25, 118, 210, 0.3)'
      };
    case 'summarization':
      return {
        label: 'Summarization',
        color: 'warning' as const,
        bgColor: 'rgba(237, 108, 2, 0.08)',
        borderColor: 'rgba(237, 108, 2, 0.4)'
      };
    case 'final_analysis':
      return {
        label: 'Final Analysis',
        color: 'success' as const,
        bgColor: 'rgba(46, 125, 50, 0.08)',
        borderColor: 'rgba(46, 125, 50, 0.4)'
      };
    default:
      return {
        label: 'LLM',
        color: 'default' as const,
        bgColor: 'transparent',
        borderColor: 'divider'
      };
  }
};

/**
 * LLMInteractionPreview component
 * Shows condensed preview of LLM interactions with first/last sentences of Thought and full Action
 */
function LLMInteractionPreview({ 
  interaction, 
  showFullPreview = true 
}: LLMInteractionPreviewProps) {
  
  // EP-0014: Helper to get messages array from either new conversation or legacy messages field
  const getMessages = (llm: LLMInteraction): LLMMessage[] => {
    // Try new conversation field first (EP-0014)
    if (llm.conversation?.messages && Array.isArray(llm.conversation.messages)) {
      return llm.conversation.messages;
    }
    // Fall back to legacy messages field for backward compatibility
    if (llm.messages && Array.isArray(llm.messages)) {
      return llm.messages;
    }
    return [];
  };

  const extractResponseText = (llm: LLMInteraction): string => {
    // EP-0010: Handle failed interactions
    if (llm.success === false) {
      return '';
    }
    
    // EP-0014: Use helper to get messages from either conversation or legacy field
    const messages = getMessages(llm);
    // Find the LATEST assistant message (for ReAct, we want the most recent reasoning)
    const assistantMsg = messages.slice().reverse().find((m: LLMMessage) => m?.role === 'assistant');
    if (assistantMsg) {
      if (typeof assistantMsg.content === 'string') return assistantMsg.content;
      if (assistantMsg.content !== undefined) return JSON.stringify(assistantMsg.content);
    }
    return '';
  };

  // EP-0010: Check if this is a failed interaction
  const isFailed = interaction.success === false;

  const parseActionDetails = (action: string) => {
    // Use case-insensitive regex to capture both action command and input
    // Handles variations like "Action input:", extra spaces, etc.
    const match = action.match(/([\s\S]*?)\bAction\s*Input\s*:\s*(.*)$/i);
    
    if (match) {
      const actionCommand = match[1].trim();
      const actionInput = match[2].trim();
      return { actionCommand, actionInput };
    }
    
    // If no Action Input found, treat entire text as action command
    return { actionCommand: action.trim(), actionInput: '' };
  };

  const getThoughtPreview = (thought: string): { first: string; lastTwo: string[]; hasMore: boolean } => {
    if (!thought) return { first: '', lastTwo: [], hasMore: false };
    
    // Split into sentences using more sophisticated regex
    const sentences = thought
      .split(/(?<=[.!?])\s+(?=[A-Z])/)
      .map(s => s.trim())
      .filter(s => s.length > 0);
    
    if (sentences.length === 0) return { first: '', lastTwo: [], hasMore: false };
    if (sentences.length === 1) return { first: sentences[0], lastTwo: [], hasMore: false };
    if (sentences.length === 2) return { first: sentences[0], lastTwo: [sentences[1]], hasMore: false };
    if (sentences.length === 3) return { first: sentences[0], lastTwo: [sentences[1], sentences[2]], hasMore: false };
    
    // For 4+ sentences, show first + last two with gap
    return {
      first: sentences[0],
      lastTwo: sentences.slice(-2),
      hasMore: true
    };
  };

  const responseText = extractResponseText(interaction);
  const { thought, action } = parseThoughtAndAction(responseText);
  const { first: firstThought, lastTwo: lastThoughts, hasMore } = getThoughtPreview(thought);
  const { actionCommand, actionInput } = parseActionDetails(action);
  
  // Get interaction type styling
  const interactionType = interaction.interaction_type || 'investigation';
  const typeStyle = getInteractionTypeStyle(interactionType);

  if (!showFullPreview) {
    // Compact version - show interaction type badge
    return (
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Chip 
          label={typeStyle.label} 
          size="small" 
          color={typeStyle.color}
          sx={{ fontWeight: 600 }}
        />
        {thought && (
          <Chip 
            label="Thought" 
            size="small" 
            variant="outlined" 
            color="primary"
          />
        )}
        {action && (
          <Chip 
            label="Action" 
            size="small" 
            variant="outlined" 
            color="secondary"
          />
        )}
      </Box>
    );
  }

  // Handle failed interactions
  if (isFailed) {
    return (
      <Box sx={{ mt: 1 }}>
        {/* Interaction Type Badge */}
        <Box sx={{ mb: 1, display: 'flex', gap: 1, alignItems: 'center' }}>
          <Chip 
            label={typeStyle.label} 
            size="small" 
            color={typeStyle.color}
            sx={{ fontWeight: 600, fontSize: '0.7rem' }}
          />
        </Box>
        
        <Typography variant="caption" sx={{ 
          fontWeight: 600, 
          color: 'error.main',
          textTransform: 'uppercase',
          letterSpacing: '0.5px'
        }}>
          LLM Error
        </Typography>
        
        <Box sx={{ 
          mt: 0.5,
          p: 0.75,
          bgcolor: 'grey.50',
          borderRadius: 1,
          border: 1,
          borderColor: 'error.main'
        }}>
          <Typography variant="body2" sx={{ 
            fontSize: '0.75rem',
            color: 'error.main',
            fontWeight: 500
          }}>
            {interaction.error_message ? 
              (interaction.error_message.length > 600 ? 
                `${interaction.error_message.substring(0, 600)}...` : 
                interaction.error_message
              ) : 
              'LLM request failed - no response received'
            }
          </Typography>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ mt: 1 }}>
      {/* Interaction Type Badge */}
      <Box sx={{ mb: 1.5, display: 'flex', gap: 1, alignItems: 'center' }}>
        <Chip 
          label={typeStyle.label} 
          size="small" 
          color={typeStyle.color}
          sx={{ fontWeight: 600, fontSize: '0.7rem' }}
        />
      </Box>
      
      {/* Thought Preview */}
      {thought && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" sx={{ 
            fontWeight: 600, 
            color: 'primary.main',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Thought
          </Typography>
          
          {firstThought && (
            <Box sx={{ mt: 0.5 }}>
              <Typography variant="body2" sx={{ 
                fontStyle: 'italic',
                color: 'text.secondary',
                fontSize: '0.875rem',
                lineHeight: 1.4
              }}>
                "{firstThought}"
              </Typography>
            </Box>
          )}
          
          {hasMore && (
            <Box sx={{ 
              mt: 1, 
              mb: 0.5, 
              textAlign: 'center',
              py: 0.5,
              px: 1
            }}>
              <Typography variant="body2" sx={{ 
                color: 'primary.main',
                fontSize: '0.8rem',
                fontWeight: 600,
                letterSpacing: '2px'
              }}>
                • • •
              </Typography>
            </Box>
          )}
          
          {lastThoughts.map((sentence, index) => (
            <Box key={index} sx={{ mt: 0.5 }}>
              <Typography variant="body2" sx={{ 
                fontStyle: 'italic',
                color: 'text.secondary',
                fontSize: '0.875rem',
                lineHeight: 1.4
              }}>
                "{sentence}"
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {/* Action Preview */}
      {action && (
        <Box>
          <Typography variant="caption" sx={{ 
            fontWeight: 600, 
            color: 'secondary.main',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Action
          </Typography>
          
          {/* Compact Action Display */}
          {(actionCommand || actionInput) && (
            <Box sx={{ 
              mt: 0.5,
              p: 0.75,
              bgcolor: 'grey.50',
              borderRadius: 1,
              border: 1,
              borderColor: 'divider'
            }}>
              <Typography variant="body2" sx={{ 
                fontFamily: 'monospace',
                fontSize: '0.75rem',
                color: 'text.secondary',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.3
              }}>
                {actionCommand && (
                  <Box component="span" sx={{ fontWeight: 600, color: 'text.primary' }}>
                    {actionCommand.length > 80 ? `${actionCommand.substring(0, 80)}...` : actionCommand}
                  </Box>
                )}
                {actionInput && actionInput !== actionCommand && (
                  <>
                    {actionCommand && (
                      <Box component="span" sx={{ color: 'text.disabled', mx: 0.5 }}>
                        •
                      </Box>
                    )}
                    <Box component="span" sx={{ fontStyle: 'italic' }}>
                      {actionInput.length > 60 ? `${actionInput.substring(0, 60)}...` : actionInput}
                    </Box>
                  </>
                )}
              </Typography>
            </Box>
          )}
          
          {/* Fallback for non-separated action content */}
          {!actionCommand && !actionInput && (
            <Box sx={{ 
              mt: 0.5,
              p: 1,
              bgcolor: 'grey.50',
              borderRadius: 1,
              border: 1,
              borderColor: 'divider'
            }}>
              <Typography variant="body2" sx={{ 
                fontFamily: 'monospace',
                fontSize: '0.8rem',
                color: 'text.primary',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: 120,
                overflow: 'auto'
              }}>
                {action.length > 200 ? `${action.substring(0, 200)}...` : action}
              </Typography>
            </Box>
          )}
        </Box>
      )}

      {/* Fallback for unstructured responses */}
      {!thought && !action && responseText && (
        <Box>
          <Typography variant="caption" sx={{ 
            fontWeight: 600, 
            color: 'text.secondary',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Response
          </Typography>
          
          <Box sx={{ 
            mt: 0.5,
            p: 1,
            bgcolor: 'grey.50',
            borderRadius: 1,
            border: 1,
            borderColor: 'divider'
          }}>
            <Typography variant="body2" sx={{ 
              fontSize: '0.875rem',
              color: 'text.secondary',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: 80,
              overflow: 'auto'
            }}>
              {responseText.length > 200 ? `${responseText.substring(0, 200)}...` : responseText}
            </Typography>
          </Box>
        </Box>
      )}
    </Box>
  );
}

export default memo(LLMInteractionPreview);