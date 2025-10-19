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
import { websocketService } from '../services/websocketService';
// Auto-scroll is now handled by the centralized system in SessionDetailPageBase

interface ProcessingIndicatorProps {
  message?: string;
  centered?: boolean;
}

/**
 * ProcessingIndicator Component
 * Animated pulsing dots with optional message
 */
function ProcessingIndicator({ message = 'Processing...', centered = false }: ProcessingIndicatorProps) {
  return (
    <Box 
      sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: 1.5,
        ...(centered ? { py: 4, justifyContent: 'center' } : { mt: 2 }),
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
        {message}
      </Typography>
    </Box>
  );
}

interface ConversationTimelineProps {
  session: DetailedSession;
  autoScroll?: boolean;
}

interface StreamingItem {
  type: 'thought' | 'final_answer';
  content: string;
  stage_execution_id?: string;
  waitingForDb?: boolean; // True when stream completed, waiting for DB confirmation
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
  const [streamingItems, setStreamingItems] = useState<Map<string, StreamingItem>>(new Map());
  // Track which chatFlow items have been "claimed" by deduplication (prevents double-matching)
  const [claimedChatFlowItems, setClaimedChatFlowItems] = useState<Set<string>>(new Set());
  
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

  // Subscribe to streaming events
  useEffect(() => {
    if (!session.session_id) return;
    
    const handleStreamEvent = (event: any) => {
      if (event.type === 'llm.stream.chunk') {
        console.log('🌊 Received streaming chunk:', event.stream_type, event.is_complete);
        
        setStreamingItems(prev => {
          const updated = new Map(prev);
          const key = event.stage_execution_id || 'default';
          
          if (event.is_complete) {
            // Stream completed - mark as waiting for DB update
            // Don't set timeout - let content-based deduplication handle it
            const existing = prev.get(key);
            if (existing) {
              updated.set(key, {
                ...existing,
                content: event.chunk, // Final content update
                waitingForDb: true // Mark as waiting for DB confirmation
              });
              console.log('✅ Stream completed, waiting for DB update to deduplicate');
            }
          } else {
            // Still streaming - update content
            updated.set(key, {
              type: event.stream_type as 'thought' | 'final_answer',
              content: event.chunk,
              stage_execution_id: event.stage_execution_id,
              waitingForDb: false
            });
          }
          
          return updated;
        });
      }
    };
    
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${session.session_id}`,
      handleStreamEvent
    );
    
    return () => unsubscribe();
  }, [session.session_id]);

  // Clear streaming items when their content appears in DB data (smart deduplication with claimed-item tracking)
  // ONLY runs when chatFlow changes (DB update), NOT when streaming chunks arrive
  useEffect(() => {
    setStreamingItems(prev => {
      // Early exit if nothing to deduplicate
      if (prev.size === 0 || chatFlow.length === 0) {
        return prev;
      }
      
      const updated = new Map(prev);
      const newlyClaimed = new Set(claimedChatFlowItems);
      let itemsCleared = 0;
      
      // For each streaming item (in insertion order = chronological), find its matching unclaimed DB item
      for (const [key, streamingItem] of prev.entries()) {
        // Search from OLDEST to NEWEST (last 20 items for performance)
        // This ensures chronological matching: 1st stream → 1st unclaimed DB item
        const searchStart = Math.max(0, chatFlow.length - 20);
        const searchEnd = chatFlow.length;
        
        for (let i = searchStart; i < searchEnd; i++) {
          const dbItem = chatFlow[i];
          
          // Create unique key for this DB item (timestamp + type + content hash)
          const itemKey = `${dbItem.timestamp_us}-${dbItem.type}-${dbItem.content?.substring(0, 50)}`;
          
          // Check if: matching type + content, AND not already claimed
          if (dbItem.type === streamingItem.type && 
              dbItem.content?.trim() === streamingItem.content?.trim() &&
              !newlyClaimed.has(itemKey)) {
            
            // Found unclaimed match!
            updated.delete(key); // Clear streaming item
            newlyClaimed.add(itemKey); // Mark DB item as claimed
            itemsCleared++;
            console.log(`🎯 Matched streaming item to unclaimed DB item (ts: ${dbItem.timestamp_us})`);
            break; // Stop searching for this streaming item
          }
        }
      }
      
      // Update claimed items tracking if we claimed new items
      if (newlyClaimed.size > claimedChatFlowItems.size) {
        setClaimedChatFlowItems(newlyClaimed);
      }
      
      if (itemsCleared > 0) {
        console.log(`🧹 Cleared ${itemsCleared} streaming items via claimed-item matching`);
        return updated; // Return new Map only if we made changes
      }
      
      return prev; // Return same reference to avoid unnecessary re-renders
    });
  }, [chatFlow, claimedChatFlowItems]); // Depend on both chatFlow and claimed items

  // Clear claimed items tracking when session changes (cleanup)
  useEffect(() => {
    console.log('🔄 Session changed, resetting claimed items tracking');
    setClaimedChatFlowItems(new Set());
  }, [session.session_id]);

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
            color={
              chatStats.toolCallsCount === 0 
                ? 'default' 
                : chatStats.successfulToolCalls === chatStats.toolCallsCount 
                  ? 'success' 
                  : 'warning'
            }
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
        {chatFlow.length === 0 && streamingItems.size > 0 ? (
          // Show streaming items even before DB has data
          <Box>
            {Array.from(streamingItems.values()).map((item, idx) => (
              <Box 
                key={`streaming-${idx}`} 
                sx={{ 
                  mb: 1.5, 
                  display: 'flex', 
                  gap: 1.5
                }}
              >
                <Typography 
                  variant="body2" 
                  sx={{ 
                    fontSize: '1.1rem', 
                    lineHeight: 1,
                    flexShrink: 0,
                    mt: 0.25
                  }}
                >
                  {item.type === 'thought' ? '💭' : '🎯'}
                </Typography>
                <Typography 
                  variant="body1" 
                  sx={{ 
                    whiteSpace: 'pre-wrap', 
                    wordBreak: 'break-word',
                    lineHeight: 1.7,
                    fontSize: '1rem',
                    color: 'text.primary'
                  }}
                >
                  {item.content}
                </Typography>
              </Box>
            ))}
            <ProcessingIndicator />
          </Box>
        ) : chatFlow.length === 0 ? (
          // Empty/Loading state - show appropriate message based on session status
          <Box>
            {session.status === 'in_progress' ? (
              // Session is actively processing - show processing indicator
              <ProcessingIndicator centered />
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
            {chatFlow.map((item) => (
              <ChatFlowItem key={`${item.type}-${item.timestamp_us}`} item={item} />
            ))}
            
            {/* Show streaming items at the end (will be cleared by deduplication when DB data arrives) */}
            {streamingItems.size > 0 && (
              Array.from(streamingItems.values()).map((item, idx) => (
                <Box 
                  key={`streaming-${idx}`} 
                  sx={{ 
                    mb: 1.5, 
                    display: 'flex', 
                    gap: 1.5
                  }}
                >
                  <Typography 
                    variant="body2" 
                    sx={{ 
                      fontSize: '1.1rem',
                      lineHeight: 1,
                      flexShrink: 0,
                      mt: 0.25
                    }}
                  >
                    {item.type === 'thought' ? '💭' : '🎯'}
                  </Typography>
                  <Typography 
                    variant="body1" 
                    sx={{ 
                      whiteSpace: 'pre-wrap', 
                      wordBreak: 'break-word',
                      lineHeight: 1.7,
                      fontSize: '1rem',
                      color: 'text.primary'
                    }}
                  >
                    {item.content}
                  </Typography>
                </Box>
              ))
            )}

            {/* Processing indicator at bottom when session is still in progress */}
            {session.status === 'in_progress' && <ProcessingIndicator />}
          </>
        )}
      </Box>
    </Card>
  );
}

export default ConversationTimeline;
