import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Paper,
  Box,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  CircularProgress,
  Tooltip,
  alpha,
  Alert,
  AlertTitle,
} from '@mui/material';
import { CancelOutlined, Replay as ReplayIcon, PlayArrow, PauseCircle } from '@mui/icons-material';
import StatusBadge from './StatusBadge';
import ProgressIndicator from './ProgressIndicator';
import TokenUsageDisplay from './TokenUsageDisplay';
import { formatTimestamp } from '../utils/timestamp';
import { apiClient, handleAPIError } from '../services/api';
import { isTerminalSessionStatus, SESSION_STATUS } from '../utils/statusConstants';
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
function SessionSummary({ summary, sessionStatus, sessionTokens, mcpSelection, stages }: { 
  summary: any, 
  sessionStatus: string, 
  sessionTokens?: { input_tokens?: number; output_tokens?: number; total_tokens?: number },
  mcpSelection?: any,
  stages?: any[]
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Calculate tool_list and tool_call counts from stage data
  const mcpBreakdown = (() => {
    if (!stages || stages.length === 0) {
      return { toolListCalls: 0, toolCalls: 0, total: summary.mcp_communications || 0 };
    }
    
    let toolListCalls = 0;
    let toolCalls = 0;
    
    stages.forEach((stage: any) => {
      if (stage.mcp_communications && Array.isArray(stage.mcp_communications)) {
        stage.mcp_communications.forEach((mcp: any) => {
          if (mcp.details?.communication_type === 'tool_list') {
            toolListCalls++;
          } else if (mcp.details?.communication_type === 'tool_call') {
            toolCalls++;
          }
        });
      }
    });
    
    return { toolListCalls, toolCalls, total: toolListCalls + toolCalls };
  })();

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
    const isInProgress =
      sessionStatus === SESSION_STATUS.IN_PROGRESS ||
      sessionStatus === SESSION_STATUS.PENDING ||
      sessionStatus === SESSION_STATUS.CANCELING;
    
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
            <Box sx={(theme) => ({ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 0.5,
              px: 1, 
              py: 0.25, 
              backgroundColor: alpha(theme.palette.info.main, 0.05),
              borderRadius: '12px',
              border: '1px solid',
              borderColor: alpha(theme.palette.info.main, 0.2)
            })}>
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
          <Box sx={(theme) => ({ 
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            px: 1,
            py: 0.5,
            backgroundColor: alpha(theme.palette.primary.main, 0.05),
            borderRadius: '16px',
            border: '1px solid',
            borderColor: alpha(theme.palette.primary.main, 0.2)
          })}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: 'primary.main' }}>
              🧠 {isInProgress ? '...' : summary.llm_interactions}
            </Typography>
            <Typography variant="caption" color="primary.main">
              LLM
            </Typography>
          </Box>
          
          {/* MCP calls badge */}
          <Tooltip 
            title={
              <Box sx={{ py: 0.5 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  MCP Communications
                </Typography>
                
                {/* Communication breakdown */}
                <Box sx={{ mb: 1.5, pb: 1.5, borderBottom: '1px solid rgba(255,255,255,0.2)' }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="body2">
                      📋 Tool list calls:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, ml: 2 }}>
                      {mcpBreakdown.toolListCalls}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="body2">
                      🔧 Tool calls:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, ml: 2 }}>
                      {mcpBreakdown.toolCalls}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5, pt: 0.5, borderTop: '1px solid rgba(255,255,255,0.15)' }}>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      Total:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700, ml: 2 }}>
                      {mcpBreakdown.total}
                    </Typography>
                  </Box>
                </Box>
                
                {/* MCP Configuration */}
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5, fontSize: '0.8rem' }}>
                  Configuration
                </Typography>
                {!mcpSelection ? (
                  <Typography variant="body2" sx={{ fontSize: '0.85rem' }}>
                    🔹 Using default MCP servers
                  </Typography>
                ) : (
                  <Box>
                    <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 500, fontSize: '0.85rem' }}>
                      Selected Servers:
                    </Typography>
                    {mcpSelection.servers.map((server: any, idx: number) => (
                      <Box key={idx} sx={{ ml: 1, mb: 0.5 }}>
                        <Typography variant="body2" sx={{ fontWeight: 500, fontSize: '0.85rem' }}>
                          • {server.name}
                        </Typography>
                        {server.tools && server.tools.length > 0 ? (
                          <Typography variant="caption" sx={{ ml: 2, display: 'block', opacity: 0.9, fontSize: '0.75rem' }}>
                            Tools: {server.tools.join(', ')}
                          </Typography>
                        ) : (
                          <Typography variant="caption" sx={{ ml: 2, display: 'block', opacity: 0.9, fontSize: '0.75rem' }}>
                            Tools: all
                          </Typography>
                        )}
                      </Box>
                    ))}
                  </Box>
                )}
              </Box>
            }
            placement="top"
            arrow
          >
            <Box sx={(theme) => ({ 
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              px: 1,
              py: 0.5,
              backgroundColor: alpha(theme.palette.warning.main, 0.08),
              borderRadius: '16px',
              border: '1px solid',
              borderColor: alpha(theme.palette.warning.main, 0.3),
              cursor: 'pointer',
              transition: 'all 0.2s ease-in-out',
              '&:hover': {
                backgroundColor: alpha(theme.palette.warning.main, 0.12),
                borderColor: alpha(theme.palette.warning.main, 0.4),
              }
            })}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: 'warning.main' }}>
                🔧 {isInProgress ? '...' : summary.mcp_communications}
              </Typography>
              <Typography variant="caption" color="warning.main">
                MCP
              </Typography>
            </Box>
          </Tooltip>
          
          {/* Errors badge - only show if there are actual errors */}
          {summary.errors_count > 0 && (
            <Box sx={(theme) => ({ 
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              px: 1,
              py: 0.5,
              backgroundColor: alpha(theme.palette.error.main, 0.05),
              borderRadius: '16px',
              border: '1px solid',
              borderColor: alpha(theme.palette.error.main, 0.2)
            })}>
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
             <Box sx={(theme) => ({ 
               display: 'flex',
               alignItems: 'center',
               gap: 0.5,
               px: 1,
               py: 0.5,
               backgroundColor: alpha(theme.palette.info.main, 0.05),
               borderRadius: '16px',
               border: '1px solid',
               borderColor: alpha(theme.palette.info.main, 0.2)
             })}>
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
             <Box sx={(theme) => ({ 
               display: 'flex',
               alignItems: 'center',
               gap: 0.5,
               px: 1,
               py: 0.5,
               backgroundColor: alpha(theme.palette.success.main, 0.05),
               borderRadius: '16px',
               border: '1px solid',
               borderColor: alpha(theme.palette.success.main, 0.2)
             })}>
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
  const navigate = useNavigate();
  
  const isInProgress =
    session.status === SESSION_STATUS.IN_PROGRESS ||
    session.status === SESSION_STATUS.PENDING ||
    session.status === SESSION_STATUS.CANCELING;
  const sessionIsCanceling = session.status === SESSION_STATUS.CANCELING;
  const sessionIsPaused = session.status === SESSION_STATUS.PAUSED;
  const canCancel = isInProgress || sessionIsCanceling || sessionIsPaused;
  const isTerminalStatus = isTerminalSessionStatus(session.status);
  const previousStatusRef = useRef<string>(session.status);
  
  // Cancel dialog state
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  
  // Resume state
  const [isResuming, setIsResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  
  // Detect status changes from in_progress to completed and trigger refresh
  useEffect(() => {
    const previousStatus = previousStatusRef.current;
    const currentStatus = session.status;
    
    // Check if status changed from in_progress/pending/paused to completed/failed/cancelled
    const wasInProgress =
      previousStatus === SESSION_STATUS.IN_PROGRESS ||
      previousStatus === SESSION_STATUS.PENDING ||
      previousStatus === SESSION_STATUS.PAUSED ||
      previousStatus === SESSION_STATUS.CANCELING;
    const nowCompleted =
      currentStatus === SESSION_STATUS.COMPLETED ||
      currentStatus === SESSION_STATUS.FAILED ||
      currentStatus === SESSION_STATUS.CANCELLED;
    
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
  
  // Clear canceling state when session status changes to cancelled
  useEffect(() => {
    if (session.status === SESSION_STATUS.CANCELLED && isCanceling) {
      setIsCanceling(false);
    }
  }, [session.status, isCanceling]);
  
  // Handle cancel button click
  const handleCancelClick = () => {
    setShowCancelDialog(true);
    setCancelError(null);
  };
  
  // Handle dialog close without canceling
  const handleDialogClose = () => {
    if (!isCanceling) {
      setShowCancelDialog(false);
      setCancelError(null);
    }
  };
  
  // Handle cancel confirmation
  const handleConfirmCancel = async () => {
    setIsCanceling(true);
    setCancelError(null);
    
    try {
      await apiClient.cancelSession(session.session_id);
      // Close dialog on success
      setShowCancelDialog(false);
      // Keep isCanceling true - will be cleared when WebSocket updates status to 'cancelled'
    } catch (error) {
      // Show error, allow retry
      const errorMessage = handleAPIError(error);
      setCancelError(errorMessage);
      setIsCanceling(false);
    }
  };
  
  // Handle resume button click
  const handleResumeClick = async () => {
    setIsResuming(true);
    setResumeError(null);
    
    try {
      await apiClient.resumeSession(session.session_id);
      // Resume initiated successfully
      // WebSocket will update status to 'in_progress'
    } catch (error) {
      // Show error
      const errorMessage = handleAPIError(error);
      setResumeError(errorMessage);
      setIsResuming(false);
    }
  };
  
  // Clear resuming state when session status changes away from paused
  useEffect(() => {
    if (session.status !== SESSION_STATUS.PAUSED && isResuming) {
      setIsResuming(false);
      setResumeError(null);
    }
  }, [session.status, isResuming]);
  
  // Handle re-submit button click
  const handleResubmit = () => {
    navigate('/submit-alert', {
      state: {
        resubmit: true,
        alertType: session.alert_type,
        runbook: session.runbook_url || null,
        alertData: session.alert_data,
        sessionId: session.session_id,
        mcpSelection: session.mcp_selection || null
      }
    });
  };

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
                {session.alert_type || 'Alert Processing'}
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
            
            {/* Author information */}
            {session.author && (
              <Typography 
                variant="body2" 
                color="text.secondary"
                sx={{ mt: 0.5 }}
              >
                Submitted by: <strong>{session.author}</strong>
              </Typography>
            )}
            
            {/* Runbook URL information */}
            {session.runbook_url && (
              <Typography 
                variant="body2" 
                color="text.secondary"
                sx={{ mt: 0.5, display: 'flex', alignItems: 'center', gap: 0.5 }}
              >
                Runbook: 
                <a 
                  href={session.runbook_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  style={{ 
                    color: 'inherit',
                    textDecoration: 'underline',
                    fontFamily: 'monospace',
                    fontSize: '0.85em'
                  }}
                >
                  {session.runbook_url.length > 200 
                    ? `${session.runbook_url.substring(0, 197)}...` 
                    : session.runbook_url}
                </a>
              </Typography>
            )}
          </Box>

          {/* Right side: Duration Timer and Action Buttons */}
          <Box sx={{ 
            display: 'flex', 
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 1.5,
            minWidth: 200
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
            
            {/* Action Buttons Section - More Prominent */}
            <Box sx={{ 
              display: 'flex', 
              flexDirection: 'column', 
              gap: 1.5, 
              width: '100%',
              mt: 1
            }}>
              {/* Resume Button - Only for paused sessions */}
              {sessionIsPaused && (
                <>
                  {/* Pause Alert - Only show when both status is PAUSED and metadata exists */}
                  {session.status === SESSION_STATUS.PAUSED && session.pause_metadata && (
                    <Alert 
                      severity="warning" 
                      icon={<PauseCircle />}
                      sx={{ mb: 1.5, width: '100%' }}
                    >
                      <AlertTitle sx={{ fontWeight: 600 }}>Session Paused</AlertTitle>
                      {session.pause_metadata.message || 'Session is paused and awaiting action.'}
                    </Alert>
                  )}
                  
                  <Button
                    variant="contained"
                    size="large"
                    onClick={handleResumeClick}
                    disabled={isResuming}
                    sx={{
                      minWidth: 180,
                      textTransform: 'none',
                      fontWeight: 600,
                      fontSize: '0.95rem',
                      py: 1,
                      px: 2.5,
                      backgroundColor: 'success.main',
                      color: 'white',
                      '&:hover': {
                        backgroundColor: 'success.dark',
                      },
                      transition: 'all 0.2s ease-in-out',
                    }}
                  >
                    {isResuming ? (
                      <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />
                    ) : (
                      <PlayArrow 
                        sx={{ 
                          mr: 1,
                          fontSize: '1.2rem',
                        }} 
                      />
                    )}
                    {isResuming ? 'RESUMING...' : 'RESUME SESSION'}
                  </Button>
                  
                  {/* Resume Error Display */}
                  {resumeError && (
                    <Box sx={(theme) => ({ 
                      p: 1.5, 
                      bgcolor: alpha(theme.palette.error.main, 0.05), 
                      borderRadius: 1, 
                      border: '1px solid', 
                      borderColor: 'error.main' 
                    })}>
                      <Typography variant="body2" color="error.main">
                        {resumeError}
                      </Typography>
                    </Box>
                  )}
                </>
              )}
              
              {/* Cancel Button - Only for active sessions */}
              {canCancel && (
                <Button
                  variant="outlined"
                  size="large"
                  onClick={handleCancelClick}
                  disabled={isCanceling || sessionIsCanceling}
                  sx={{
                    minWidth: 180,
                    textTransform: 'none',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    py: 1,
                    px: 2.5,
                    backgroundColor: 'white',
                    color: 'error.main',
                    borderColor: 'error.main',
                    borderWidth: 1.5,
                    '&:hover': {
                      backgroundColor: 'error.main',
                      borderColor: 'error.main',
                      color: 'white',
                    },
                    transition: 'all 0.2s ease-in-out',
                  }}
                >
                  {isCanceling || sessionIsCanceling ? (
                    <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />
                  ) : (
                    <CancelOutlined 
                      sx={{ 
                        mr: 1,
                        fontSize: '1.2rem',
                      }} 
                    />
                  )}
                  {isCanceling || sessionIsCanceling ? 'CANCELING...' : 'CANCEL SESSION'}
                </Button>
              )}
              
              {/* Re-submit Button - Only for terminal sessions */}
              {isTerminalStatus && (
                <Tooltip title="Submit a new alert with the same data" placement="left">
                  <Button
                    variant="outlined"
                    size="large"
                    onClick={handleResubmit}
                    sx={{
                      minWidth: 180,
                      textTransform: 'none',
                      fontWeight: 600,
                      fontSize: '0.95rem',
                      py: 1,
                      px: 2.5,
                      backgroundColor: 'white',
                      color: 'info.main',
                      borderColor: 'info.main',
                      borderWidth: 1.5,
                      '&:hover': {
                        backgroundColor: 'info.main',
                        borderColor: 'info.main',
                        color: 'white',
                      },
                      transition: 'all 0.2s ease-in-out',
                    }}
                  >
                    <ReplayIcon 
                      sx={{ 
                        mr: 1,
                        fontSize: '1.2rem',
                      }} 
                    />
                    RE-SUBMIT ALERT
                  </Button>
                </Tooltip>
              )}
            </Box>
          </Box>
        </Box>

        {/* Cancel Confirmation Dialog */}
        <Dialog
          open={showCancelDialog}
          onClose={handleDialogClose}
          maxWidth="sm"
          fullWidth
        >
          <DialogTitle>Cancel Session?</DialogTitle>
          <DialogContent>
            <DialogContentText>
              Are you sure you want to cancel this session? This action cannot be undone.
              The session will be marked as cancelled and any ongoing processing will be stopped.
            </DialogContentText>
            {cancelError && (
              <Box sx={(theme) => ({ mt: 2, p: 2, bgcolor: alpha(theme.palette.error.main, 0.05), borderRadius: 1, border: '1px solid', borderColor: 'error.main' })}>
                <Typography variant="body2" color="error.main">
                  {cancelError}
                </Typography>
              </Box>
            )}
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button 
              onClick={handleDialogClose} 
              disabled={isCanceling}
              color="inherit"
            >
              Cancel
            </Button>
            <Button 
              onClick={handleConfirmCancel} 
              variant="contained" 
              color="warning"
              disabled={isCanceling}
              startIcon={isCanceling ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              {isCanceling ? 'CANCELING...' : 'CONFIRM CANCELLATION'}
            </Button>
          </DialogActions>
        </Dialog>

        {/* Summary section */}
        <Box>
          {(session.total_interactions > 0 ||
            session.status === SESSION_STATUS.IN_PROGRESS ||
            session.status === SESSION_STATUS.PENDING ||
            session.status === SESSION_STATUS.CANCELING) && (
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
              mcpSelection={session.mcp_selection}
              stages={session.stages}
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