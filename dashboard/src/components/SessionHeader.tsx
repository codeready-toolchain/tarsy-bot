import { useState, useEffect, useRef } from 'react';
import {
  Paper,
  Box,
  Typography,
  Button
} from '@mui/material';
import StatusBadge from './StatusBadge';
import ProgressIndicator from './ProgressIndicator';
import TokenUsageDisplay from './TokenUsageDisplay';
import { formatTimestamp } from '../utils/timestamp';
import type { SessionHeaderProps } from '../types';

// Animation styles for processing sessions
const animationStyles = {
  breathingGlow: {
    '@keyframes breathingGlow': {
      '0%': { 
        boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), 0 0 8px 1px rgba(2, 136, 209, 0.2)'
      },
      '50%': { 
        boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), 0 0 24px 4px rgba(2, 136, 209, 0.45)'
      },
      '100%': { 
        boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), 0 0 8px 1px rgba(2, 136, 209, 0.2)'
      },
    },
    animation: 'breathingGlow 2.8s ease-in-out infinite',
  },
  pulse: {
    '@keyframes pulse': {
      '0%': { opacity: 1 },
      '50%': { opacity: 0.4 },
      '100%': { opacity: 1 },
    },
  },
};

// Maximum length for summary before showing truncation toggle
const MAX_SUMMARY_LENGTH = 300;

/**
 * Renders session summary with proper statistics display or fallback to JSON
 */
function SessionSummary({ summary, sessionStatus, sessionTokens }: { 
  summary: any, 
  sessionStatus: string, 
  sessionTokens?: { input_tokens?: number; output_tokens?: number; total_tokens?: number } 
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Check if summary is empty or just whitespace
  const isEmpty = !summary || 
    (typeof summary === 'string' && summary.trim() === '') ||
    (typeof summary === 'object' && Object.keys(summary).length === 0);

  // Don't render anything for empty summaries
  if (isEmpty) {
    return null;
  }

  // Handle statistics object from backend
  if (typeof summary === 'object' && summary.total_interactions !== undefined) {
    const isInProgress = sessionStatus === 'in_progress' || sessionStatus === 'pending';
    
    return (
      <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 1,
          fontWeight: 600 
        }}>
          📊 Session Summary
          {isInProgress && (
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 0.5,
              px: 1, 
              py: 0.25, 
              backgroundColor: 'info.50',
              borderRadius: '12px',
              border: '1px solid',
              borderColor: 'info.200'
            }}>
              <Box sx={{ 
                width: 6, 
                height: 6, 
                borderRadius: '50%', 
                backgroundColor: 'info.main',
                ...animationStyles.pulse,
                animation: 'pulse 2s infinite'
              }} />
              <Typography variant="caption" color="info.main" sx={{ fontWeight: 500 }}>
                Live Processing
              </Typography>
            </Box>
          )}
        </Typography>
        
        {/* Always show same badge layout - use placeholders during progress */}
        <Box sx={{ 
          display: 'flex',
          flexWrap: 'wrap',
          gap: 1,
          alignItems: 'center'
        }}>
          {/* Total interactions badge */}
          <Box sx={{ 
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            px: 1,
            py: 0.5,
            backgroundColor: 'grey.100',
            borderRadius: '16px',
            border: '1px solid',
            borderColor: 'grey.300'
          }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {isInProgress ? '...' : summary.total_interactions}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              total
            </Typography>
          </Box>
          
          {/* LLM calls badge */}
          <Box sx={{ 
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            px: 1,
            py: 0.5,
            backgroundColor: 'primary.50',
            borderRadius: '16px',
            border: '1px solid',
            borderColor: 'primary.200'
          }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: 'primary.main' }}>
              🧠 {isInProgress ? '...' : summary.llm_interactions}
            </Typography>
            <Typography variant="caption" color="primary.main">
              LLM
            </Typography>
          </Box>
          
          {/* MCP calls badge */}
          <Box sx={{ 
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            px: 1,
            py: 0.5,
            backgroundColor: 'secondary.50',
            borderRadius: '16px',
            border: '1px solid',
            borderColor: 'secondary.200'
          }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: 'secondary.main' }}>
              🔧 {isInProgress ? '...' : summary.mcp_communications}
            </Typography>
            <Typography variant="caption" color="secondary.main">
              MCP
            </Typography>
          </Box>
          
          {/* Errors badge - only show if there are actual errors */}
          {summary.errors_count > 0 && (
            <Box sx={{ 
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              px: 1,
              py: 0.5,
              backgroundColor: 'error.50',
              borderRadius: '16px',
              border: '1px solid',
              borderColor: 'error.200'
            }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: 'error.main' }}>
                ⚠️ {summary.errors_count}
              </Typography>
              <Typography variant="caption" color="error.main">
                errors
              </Typography>
            </Box>
          )}
          
           {/* Chain progress badge */}
           {summary.chain_statistics && (
             <Box sx={{ 
               display: 'flex',
               alignItems: 'center',
               gap: 0.5,
               px: 1,
               py: 0.5,
               backgroundColor: 'info.50',
               borderRadius: '16px',
               border: '1px solid',
               borderColor: 'info.200'
             }}>
               <Typography variant="body2" sx={{ fontWeight: 600, color: 'info.main' }}>
                 🔗 {isInProgress ? '...' : summary.chain_statistics.total_stages}
               </Typography>
               <Typography variant="caption" color="info.main">
                 stages
               </Typography>
             </Box>
           )}
           
           {/* EP-0009: Token usage badge */}
           {sessionTokens && (sessionTokens.total_tokens || sessionTokens.input_tokens || sessionTokens.output_tokens) && (
             <Box sx={{ 
               display: 'flex',
               alignItems: 'center',
               gap: 0.5,
               px: 1,
               py: 0.5,
               backgroundColor: 'success.50',
               borderRadius: '16px',
               border: '1px solid',
               borderColor: 'success.200'
             }}>
               <Typography variant="body2" sx={{ fontWeight: 600, color: 'success.main' }}>
                 🪙 {isInProgress ? '...' : (sessionTokens.total_tokens?.toLocaleString() || '—')}
               </Typography>
               <Typography variant="caption" color="success.main">
                 tokens
               </Typography>
             </Box>
           )}
        </Box>
      </Box>
    );
  }

  // Fallback for string summaries or other formats
  const summaryText = typeof summary === 'string' 
    ? summary 
    : JSON.stringify(summary, null, 2);

  // Check if truncation is needed
  const needsTruncation = summaryText.length > MAX_SUMMARY_LENGTH;
  const displayText = needsTruncation && !isExpanded 
    ? summaryText.substring(0, MAX_SUMMARY_LENGTH) + '...'
    : summaryText;

  return (
    <Box sx={{ mt: 1 }}>
      <Typography 
        variant="body2" 
        component="pre"
        sx={{ 
          whiteSpace: 'pre-wrap',
          fontFamily: 'monospace',
          fontSize: '0.875rem',
          lineHeight: 1.4,
          backgroundColor: 'grey.50',
          padding: 1,
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'grey.200',
          maxWidth: '100%',
          overflow: 'auto'
        }}
      >
        {displayText}
      </Typography>
      {needsTruncation && (
        <Button 
          size="small" 
          onClick={() => setIsExpanded(!isExpanded)}
          sx={{ mt: 0.5, fontSize: '0.75rem' }}
        >
          {isExpanded ? 'Show less' : 'Show more'}
        </Button>
      )}
    </Box>
  );
}

/**
 * SessionHeader component - Phase 3
 * Displays session metadata including status, timing, and summary information
 */
function SessionHeader({ session, onRefresh }: SessionHeaderProps) {
  const isInProgress = session.status === 'in_progress' || session.status === 'pending';
  const previousStatusRef = useRef<string>(session.status);
  
  // Detect status changes from in_progress to completed and trigger refresh
  useEffect(() => {
    const previousStatus = previousStatusRef.current;
    const currentStatus = session.status;
    
    // Check if status changed from in_progress/pending to completed/failed
    const wasInProgress = previousStatus === 'in_progress' || previousStatus === 'pending';
    const nowCompleted = currentStatus === 'completed' || currentStatus === 'failed';
    
    if (wasInProgress && nowCompleted && onRefresh) {
      console.log(`🔄 Status changed from ${previousStatus} to ${currentStatus}, refreshing session data for final stats`);
      // Small delay to ensure backend has processed the completion
      setTimeout(() => {
        onRefresh();
      }, 500);
    }
    
    // Update the ref for next comparison
    previousStatusRef.current = currentStatus;
  }, [session.status, onRefresh]);

  return (
    <Paper 
      elevation={2} 
      sx={{ 
        p: 3, 
        mb: 2, 
        borderRadius: 2,
        ...(isInProgress ? animationStyles.breathingGlow : {})
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {/* Header Row */}
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'flex-start',
          gap: 2,
          flexWrap: 'wrap'
        }}>
          {/* Left side: Alert details and metadata */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {/* Main title with Status Badge */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 0.5, flexWrap: 'wrap' }}>
              <Typography 
                variant="h5" 
                sx={{ 
                  fontWeight: 600,
                  wordBreak: 'break-word'
                }}
              >
                {session.alert_data?.alert_type || session.alert_type || 'Alert Processing'}
                {session.chain_definition?.name && (
                  <Typography component="span" sx={{ color: 'text.secondary', fontWeight: 400 }}>
                    {' - '}{session.chain_definition.name}
                  </Typography>
                )}
              </Typography>
              
              {/* Prominent Status Badge */}
              <Box sx={{ transform: 'scale(1.1)' }}>
                <StatusBadge status={session.status} />
              </Box>
            </Box>
            
            {/* Chain details */}
            {session.chain_definition?.description && (
              <Typography 
                variant="body2" 
                color="text.secondary" 
                sx={{ mb: 0.5 }}
              >
                chain:{session.chain_definition.description}
              </Typography>
            )}
            
            {/* Started at timestamp */}
            <Typography 
              variant="body2" 
              color="text.secondary" 
              sx={{ mb: 1 }}
            >
              Started at {formatTimestamp(session.started_at_us, 'absolute')}
            </Typography>
            
            {/* Session ID as smaller secondary info */}
            <Typography 
              variant="caption" 
              color="text.secondary"
              sx={{ 
                fontFamily: 'monospace',
                fontSize: '0.75rem',
                opacity: 0.7
              }}
            >
              {session.session_id}
            </Typography>
          </Box>

          {/* Right side: Duration Timer - Consistent Layout */}
          <Box sx={{ 
            display: 'flex', 
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 0.5,
            minWidth: 180
          }}>
            {/* Duration Label */}
            <Typography 
              variant="caption" 
              sx={{ 
                fontWeight: 600,
                color: isInProgress ? 'primary.main' : 'success.main',
                textTransform: 'uppercase',
                letterSpacing: 0.5
              }}
            >
              Duration
            </Typography>
            
            {/* Timer Display - Always show ticking duration */}
            <Box sx={{
              minHeight: 40,
              display: 'flex',
              alignItems: 'center',
              '& .MuiTypography-root': {
                fontSize: '1.4rem !important',
                fontWeight: '800 !important',
                color: isInProgress ? 'primary.main !important' : 'success.main !important'
              }
            }}>
              <ProgressIndicator 
                status={session.status}
                startedAt={session.started_at_us}
                duration={session.duration_ms}
                variant="linear"
                showDuration={true}
                size="large"
              />
            </Box>
          </Box>
        </Box>

        {/* Summary section */}
        <Box>
          {(session.total_interactions > 0 || session.status === 'in_progress' || session.status === 'pending') && (
            <SessionSummary 
              summary={{
                total_interactions: session.total_interactions,
                llm_interactions: session.llm_interaction_count,
                mcp_communications: session.mcp_communication_count,
                errors_count: session.error_message ? 1 : 0, // Simple error counting
                chain_statistics: session.total_stages ? {
                  total_stages: session.total_stages,
                  completed_stages: session.completed_stages || 0,
                  failed_stages: session.failed_stages || 0
                } : undefined
              }} 
              sessionStatus={session.status}
              sessionTokens={{
                input_tokens: session.session_input_tokens ?? undefined,
                output_tokens: session.session_output_tokens ?? undefined,
                total_tokens: session.session_total_tokens ?? undefined
              }}
            />
          )}
          
          {/* EP-0009: Detailed token breakdown - only show if we have token data */}
          {(session.session_total_tokens || session.session_input_tokens || session.session_output_tokens) && (
            <Box sx={{ mt: 2 }}>
              <TokenUsageDisplay
                tokenData={{
                  input_tokens: session.session_input_tokens,
                  output_tokens: session.session_output_tokens,
                  total_tokens: session.session_total_tokens
                }}
                variant="detailed"
                size="medium"
                showBreakdown={true}
                label="Session Token Usage"
                color="success"
              />
            </Box>
          )}
        </Box>
      </Box>
    </Paper>
  );
}

export default SessionHeader;