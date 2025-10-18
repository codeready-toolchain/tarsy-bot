import { useEffect, useState, useMemo } from 'react';
import { 
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  Alert
} from '@mui/material';
import { parseSessionChatFlow, getChatFlowStats } from '../utils/chatFlowParser';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import type { DetailedSession } from '../types';
import ChatFlowItem from './ChatFlowItem';
import CopyButton from './CopyButton';
// Auto-scroll is now handled by the centralized system in SessionDetailPageBase

interface ConversationTimelineProps {
  session: DetailedSession;
  autoScroll?: boolean;
}

/**
 * Conversation Timeline Component
 * Renders session as a continuous chat-like flow with thoughts, tool calls, and final answers
 * Plugs into the shared SessionDetailPageBase
 */
function ConversationTimeline({ 
  session, 
  autoScroll: _autoScroll = true // Auto-scroll handled by centralized system
}: ConversationTimelineProps) {
  const [chatFlow, setChatFlow] = useState<ChatFlowItemData[]>([]);
  const [error, setError] = useState<string | null>(null);
  
  // Memoize chat flow stats to prevent recalculation on every render
  const chatStats = useMemo(() => {
    return getChatFlowStats(chatFlow);
  }, [chatFlow]);
  
  // Memoize formatSessionForCopy to prevent recalculation on every render
  const formatSessionForCopy = useMemo((): string => {
    if (chatFlow.length === 0) return '';
    
    let content = `=== CHAT FLOW SESSION ===\n`;
    content += `Session ID: ${session.session_id}\n`;
    content += `Status: ${session.status}\n`;
    content += `Chain: ${session.chain_id || 'Unknown'}\n`;
    content += `Total Items: ${chatStats.totalItems}\n`;
    content += `${'='.repeat(60)}\n\n`;
    
    chatFlow.forEach((item) => {
      if (item.type === 'stage_start') {
        content += `\n=== Stage: ${item.stageName} (${item.stageAgent}) ===\n\n`;
      } else if (item.type === 'thought') {
        content += `💭 Thought:\n${item.content}\n\n`;
      } else if (item.type === 'tool_call') {
        content += `🔧 Tool Call: ${item.toolName}\n`;
        content += `   Server: ${item.serverName}\n`;
        content += `   Arguments: ${JSON.stringify(item.toolArguments, null, 2)}\n`;
        if (item.success) {
          content += `   Result: ${typeof item.toolResult === 'string' ? item.toolResult : JSON.stringify(item.toolResult, null, 2)}\n`;
        } else {
          content += `   Error: ${item.errorMessage}\n`;
        }
        content += '\n';
      } else if (item.type === 'final_answer') {
        content += `🎯 Final Answer:\n${item.content}\n\n`;
      }
    });
    
    return content;
  }, [chatFlow, chatStats, session.session_id, session.status, session.chain_id]);

  // Parse session data into chat flow
  useEffect(() => {
    if (session) {
      try {
        const flow = parseSessionChatFlow(session);
        
        // Check if this is a meaningful update
        setChatFlow(prevFlow => {
          // If no previous data, always update
          if (prevFlow.length === 0) {
            console.log('🔄 Initial chat flow parsing');
            return flow;
          }
          
          // Check if meaningful data has changed
          if (prevFlow.length !== flow.length) {
            console.log('🔄 Chat flow length changed, updating');
            return flow;
          }
          
          // Check if last item changed
          const prevLast = prevFlow[prevFlow.length - 1];
          const newLast = flow[flow.length - 1];
          if (JSON.stringify(prevLast) !== JSON.stringify(newLast)) {
            console.log('🔄 Last chat item changed, updating');
            return flow;
          }
          
          console.log('🔄 No meaningful chat flow changes, keeping existing data');
          return prevFlow;
        });
        
        setError(null);
      } catch (err) {
        console.error('Failed to parse chat flow:', err);
        setError('Failed to parse chat flow data');
        setChatFlow([]);
      }
    }
  }, [session]);

  // Calculate stage stats
  const stageCount = session.stages?.length || 0;
  const completedStages = session.stages?.filter(s => s.status === 'completed').length || 0;
  const failedStages = session.stages?.filter(s => s.status === 'failed').length || 0;

  // Show error state if parsing failed
  if (error) {
    return (
      <Card>
        <CardContent sx={{ p: 3 }}>
          <Alert severity="error">
            <Typography variant="h6">
              Chat Flow Parsing Error
            </Typography>
            <Typography variant="body2">
              {error}
            </Typography>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      {/* Chain Progress Header */}
      <CardContent sx={{ bgcolor: 'grey.50', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" color="primary.main">
            Chain: {session.chain_id || 'Unknown'}
          </Typography>
          <CopyButton
            text={formatSessionForCopy}
            variant="button"
            buttonVariant="outlined"
            size="small"
            label="Copy Chat Flow"
            tooltip="Copy entire reasoning flow to clipboard"
          />
        </Box>

        {/* Chain Status Chips */}
        <Box display="flex" gap={1} flexWrap="wrap">
          <Chip 
            label={`${stageCount} stages`} 
            color="primary" 
            variant="outlined" 
            size="small"
          />
          <Chip 
            label={`${completedStages} completed`} 
            color="success" 
            variant="outlined" 
            size="small"
          />
          {failedStages > 0 && (
            <Chip 
              label={`${failedStages} failed`} 
              color="error" 
              variant="outlined" 
              size="small"
            />
          )}
          <Chip 
            label={`${chatStats.thoughtsCount} thoughts`}
            size="small"
            variant="outlined"
          />
          <Chip 
            label={`${chatStats.successfulToolCalls}/${chatStats.toolCallsCount} tool calls`}
            size="small"
            variant="outlined"
            color={chatStats.successfulToolCalls === chatStats.toolCallsCount ? 'success' : 'warning'}
          />
          <Chip 
            label={`${chatStats.finalAnswersCount} analyses`}
            size="small"
            variant="outlined"
            color="success"
          />
        </Box>
      </CardContent>

      {/* Blue Header Bar - Visual Separator */}
      <Box
        sx={{
          bgcolor: '#e3f2fd', // Light blue background
          py: 1.5,
          px: 3,
          borderTop: '2px solid #1976d2', // Blue accent line
          borderBottom: '1px solid #bbdefb'
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography
            variant="subtitle2"
            sx={{
              fontWeight: 600,
              color: '#1565c0',
              fontSize: '0.9rem',
              letterSpacing: 0.3
            }}
          >
            💬 AI Reasoning Flow
          </Typography>
        </Box>
      </Box>

      {/* Continuous Chat Flow */}
      <Box 
        sx={{ 
          p: 3,
          bgcolor: 'white',
          minHeight: 200
        }}
      >
        {chatFlow.length === 0 ? (
          // Empty/Loading state - show appropriate message based on session status
          <Box>
            {session.status === 'in_progress' ? (
              // Session is actively processing - show processing indicator
              <Box 
                sx={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 1.5,
                  py: 4,
                  justifyContent: 'center',
                  opacity: 0.7
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    gap: 0.5,
                    '& > div': {
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      bgcolor: '#1976d2',
                      animation: 'pulse 1.4s ease-in-out infinite',
                    },
                    '& > div:nth-of-type(2)': {
                      animationDelay: '0.2s',
                    },
                    '& > div:nth-of-type(3)': {
                      animationDelay: '0.4s',
                    },
                    '@keyframes pulse': {
                      '0%, 80%, 100%': {
                        opacity: 0.3,
                        transform: 'scale(0.8)',
                      },
                      '40%': {
                        opacity: 1,
                        transform: 'scale(1.2)',
                      },
                    },
                  }}
                >
                  <Box />
                  <Box />
                  <Box />
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.9rem', fontStyle: 'italic' }}>
                  Processing...
                </Typography>
              </Box>
            ) : (
              // Session completed/failed but has no chat flow data
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography variant="body2" color="text.secondary">
                  No reasoning steps available for this session
                </Typography>
              </Box>
            )}
          </Box>
        ) : (
          // Chat flow has items - render them
          <>
            {chatFlow.map((item, index) => (
              <ChatFlowItem key={`${item.type}-${index}-${item.timestamp_us}`} item={item} />
            ))}

            {/* Processing indicator at bottom when session is still in progress */}
            {session.status === 'in_progress' && (
              <Box 
                sx={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 1.5,
                  mt: 2,
                  opacity: 0.7
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    gap: 0.5,
                    '& > div': {
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      bgcolor: '#1976d2',
                      animation: 'pulse 1.4s ease-in-out infinite',
                    },
                    '& > div:nth-of-type(2)': {
                      animationDelay: '0.2s',
                    },
                    '& > div:nth-of-type(3)': {
                      animationDelay: '0.4s',
                    },
                    '@keyframes pulse': {
                      '0%, 80%, 100%': {
                        opacity: 0.3,
                        transform: 'scale(0.8)',
                      },
                      '40%': {
                        opacity: 1,
                        transform: 'scale(1.2)',
                      },
                    },
                  }}
                >
                  <Box />
                  <Box />
                  <Box />
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.9rem', fontStyle: 'italic' }}>
                  Processing...
                </Typography>
              </Box>
            )}
          </>
        )}
      </Box>
    </Card>
  );
}

export default ConversationTimeline;
