import { useEffect, useState, useMemo, memo } from 'react';
import { 
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  Alert,
  alpha
} from '@mui/material';
import { parseSessionChatFlow, getChatFlowStats } from '../utils/chatFlowParser';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import type { DetailedSession } from '../types';
import ChatFlowItem from './ChatFlowItem';
import CopyButton from './CopyButton';
import StreamingContentRenderer, { type StreamingItem } from './StreamingContentRenderer';
import { websocketService } from '../services/websocketService';
import { isTerminalSessionStatus } from '../utils/statusConstants';
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

// Extended streaming item for ConversationTimeline
// Includes additional fields for tool_call and user_message types
interface ConversationStreamingItem extends StreamingItem {
  // Tool call specific fields
  toolArguments?: any;
  serverName?: string;
  // User message specific fields
  author?: string;
}

/**
 * StreamingItemRenderer Component
 * Renders streaming items with proper formatting
 * Delegates common types (thought, final_answer, summarization) to shared StreamingContentRenderer
 * Handles ConversationTimeline-specific types (tool_call, user_message) locally
 */
const StreamingItemRenderer = memo(({ item }: { item: ConversationStreamingItem }) => {
  // Handle common streaming types with shared component
  if (item.type === 'thought' || item.type === 'final_answer' || item.type === 'summarization') {
    return <StreamingContentRenderer item={item} />;
  }
  
  if (item.type === 'user_message') {
    return (
      <Box sx={{ mb: 1.5, display: 'flex', gap: 1.5 }}>
        {/* Circular question mark avatar */}
        <Box
          sx={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            bgcolor: 'primary.main',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            mt: 0.25
          }}
        >
          <Typography variant="body2" sx={{ fontSize: '0.8rem', color: 'white', fontWeight: 600 }}>
            ?
          </Typography>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0, ml: 4, my: 1, mr: 1 }}>
          {/* Author name - subtle and lowercase */}
          <Typography
            variant="caption"
            sx={{
              fontWeight: 500,
              fontSize: '0.75rem',
              color: 'text.secondary',
              mb: 0.5,
              display: 'block'
            }}
          >
            {item.author} asked:
          </Typography>

          {/* Message content - conversational styling */}
          <Box
            sx={{
              p: 1.5,
              borderRadius: 1.5,
              bgcolor: 'grey.50',
              border: '1px solid',
              borderColor: 'grey.200',
            }}
          >
            <Typography
              variant="body1"
              sx={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.6,
                fontSize: '0.95rem',
                color: 'text.primary'
              }}
            >
              {item.content}
            </Typography>
          </Box>
        </Box>
      </Box>
    );
  }
  
  if (item.type === 'tool_call') {
    // Render in-progress tool call with loading indicator
    return (
      <Box sx={{ ml: 4, my: 1, mr: 1 }}>
        <Box
          sx={(theme) => ({
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            px: 1.5,
            py: 0.75,
            border: `2px dashed`,
            borderColor: alpha(theme.palette.primary.main, 0.4),
            borderRadius: 1.5,
            bgcolor: alpha(theme.palette.primary.main, 0.05),
          })}
        >
          {/* Spinning loader */}
          <Box
            sx={{
              width: 18,
              height: 18,
              border: '2px solid',
              borderColor: 'primary.main',
              borderTopColor: 'transparent',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
              '@keyframes spin': {
                '0%': { transform: 'rotate(0deg)' },
                '100%': { transform: 'rotate(360deg)' }
              }
            }}
          />
          <Typography
            variant="body2"
            sx={{
              fontFamily: 'monospace',
              fontWeight: 600,
              fontSize: '0.9rem',
              color: 'primary.main'
            }}
          >
            {item.toolName || 'Tool'}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.8rem', flex: 1 }}>
            Executing...
          </Typography>
        </Box>
      </Box>
    );
  }
  
  // Unsupported type
  return null;
});

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
  const [streamingItems, setStreamingItems] = useState<Map<string, ConversationStreamingItem>>(new Map());
  // Track which chatFlow items have been "claimed" by deduplication (prevents double-matching)
  const [claimedChatFlowItems, setClaimedChatFlowItems] = useState<Set<string>>(new Set());
  // Track if there's an active chat stage in progress (for showing processing indicator on completed sessions)
  const [activeChatStageInProgress, setActiveChatStageInProgress] = useState<boolean>(false);
  // Track collapsed stages by execution_id (default: all expanded)
  const [collapsedStages, setCollapsedStages] = useState<Map<string, boolean>>(new Map());
  
  // Handler to toggle stage collapse/expand
  const handleToggleStage = (stageId: string) => {
    setCollapsedStages(prev => {
      const updated = new Map(prev);
      updated.set(stageId, !prev.get(stageId));
      return updated;
    });
  };
  
  // Memoize chat flow stats to prevent recalculation on every render
  const chatStats = useMemo(() => {
    return getChatFlowStats(chatFlow);
  }, [chatFlow]);
  
  // Filter chat flow items based on collapse state
  // Always show stage_start items; hide content for collapsed stages
  const filteredChatFlow = useMemo(() => {
    return chatFlow.filter(item => {
      // Always show stage_start items (they contain the collapse/expand control)
      if (item.type === 'stage_start') {
        return true;
      }
      
      // For other items, hide if their stage is collapsed
      if (item.stageId && collapsedStages.get(item.stageId)) {
        return false;
      }
      
      return true;
    });
  }, [chatFlow, collapsedStages]);
  
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
      } else if (item.type === 'summarization') {
        content += `📋 Tool Result Summary${item.mcp_event_id ? ` (MCP: ${item.mcp_event_id})` : ''}:\n${item.content}\n\n`;
      } else if (item.type === 'final_answer') {
        content += `🎯 Final Answer:\n${item.content}\n\n`;
      }
    });
    
    return content;
  }, [chatFlow, chatStats, session.session_id, session.status, session.chain_id]);

  // Filter and sort streaming items for display (avoids showing duplicates during deduplication lag)
  const displayedStreamingItems = useMemo(() => {
    if (streamingItems.size === 0) return [];
    
    // Get recent DB items (last 3) to filter out duplicates
    const recentDbItems = chatFlow.slice(-3);
    
    return Array.from(streamingItems.entries())
      .filter(([, streamItem]) => {
        // Check if matching DB item exists
        const hasMatchingDbItem = recentDbItems.some(dbItem => {
          if (dbItem.type !== streamItem.type) return false;
          
          // Match by content for thoughts/final_answer
          if (streamItem.type === 'thought' || streamItem.type === 'final_answer') {
            return dbItem.content && streamItem.content && 
                   dbItem.content.trim() === streamItem.content.trim();
          }
          
          if (streamItem.type === 'user_message') {
            return (
              !!dbItem.messageId &&
              !!streamItem.messageId &&
              dbItem.messageId === streamItem.messageId
            );
          }
          
          // Match by mcp_event_id for tool_call/summarization
          return dbItem.mcp_event_id === streamItem.mcp_event_id;
        });
        
        return !hasMatchingDbItem;
      })
      .sort(([_keyA, itemA], [_keyB, itemB]) => {
        const priorityA = itemA.type === 'thought' ? 0 : 1;
        const priorityB = itemB.type === 'thought' ? 0 : 1;
        return priorityA - priorityB;
      });
  }, [streamingItems, chatFlow]);

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

  // Clear streaming items when switching sessions (prevents stale data from previous session)
  useEffect(() => {
    console.log('🔄 Session changed, clearing all streaming items');
    setStreamingItems(new Map());
  }, [session.session_id]);

  // Clear streaming items when session completes, fails, or is cancelled (with logging)
  useEffect(() => {
    if (isTerminalSessionStatus(session.status)) {
      console.log('✅ Session ended, clearing all streaming items');
      setStreamingItems(new Map());
    }
  }, [session.status]);

  // Clear streaming items on WebSocket reconnection for terminal sessions without active chat stage
  // This prevents "zombie" executions from catchup events after backend restart
  useEffect(() => {
    if (!session.session_id) return;
    
    // Only setup reconnection handler for terminal sessions without active chat stage
    if (!isTerminalSessionStatus(session.status) || activeChatStageInProgress) {
      return;
    }
    
    const handleReconnection = (connected: boolean) => {
      if (connected && isTerminalSessionStatus(session.status) && !activeChatStageInProgress) {
        console.log('🧹 WebSocket reconnected for terminal session - clearing stale streaming items');
        setStreamingItems(new Map());
      }
    };
    
    const unsubscribe = websocketService.onConnectionChange(handleReconnection);
    
    return () => unsubscribe();
  }, [session.session_id, session.status, activeChatStageInProgress]);

  // Subscribe to streaming events
  // For terminal sessions, only subscribe if there's an active chat stage in progress
  useEffect(() => {
    if (!session.session_id) return;
    
    // For terminal sessions, only subscribe if there's an ACTIVE chat stage processing (not completed)
    if (isTerminalSessionStatus(session.status) && !activeChatStageInProgress) {
      console.log('⏭️ Skipping streaming subscription for terminal session (no active chat stage)');
      return;
    }
    
    if (isTerminalSessionStatus(session.status) && activeChatStageInProgress) {
      console.log('✅ Enabling streaming subscription for terminal session with active chat stage');
    }
    
    const handleStreamEvent = (event: any) => {
      // Ignore ALL streaming events for terminal sessions without active chat stage processing
      // This prevents "zombie" executions from WebSocket catchup events after backend restart
      // Note: We DO show streaming events from ANY user when there's an active chat stage (collaborative viewing)
      if (isTerminalSessionStatus(session.status) && !activeChatStageInProgress) {
        console.log('⏭️ Ignoring zombie streaming event for completed work:', event.type);
        return;
      }
      
      if (event.type === 'stage.started' && event.chat_user_message_content) {
        // Handle stage.started events with user message data
        console.log('💬 Stage started with user message:', event.chat_user_message_content.substring(0, 50));
        setStreamingItems(prev => {
          const updated = new Map(prev);
          const key = `user-message-${event.chat_user_message_id}`;
          
          updated.set(key, {
            type: 'user_message' as const,
            content: event.chat_user_message_content,
            author: event.chat_user_message_author || 'Unknown',
            messageId: event.chat_user_message_id,
            waitingForDb: false
          });
          
          return updated;
        });
      } else if (event.type === 'mcp.tool_call.started') {
        setStreamingItems(prev => {
          const updated = new Map(prev);
          // Use communication_id as key for deduplication with DB
          const key = `tool-${event.communication_id}`;
          
          updated.set(key, {
            type: 'tool_call' as const,
            toolName: event.tool_name,
            toolArguments: event.tool_arguments,
            serverName: event.server_name,
            mcp_event_id: event.communication_id, // Matches event_id in DB
            stage_execution_id: event.stage_id,
            waitingForDb: false
          });
          
          return updated;
        });
      } else if (event.type === 'llm.stream.chunk') {
        console.log('🌊 Received streaming chunk:', event.stream_type, event.is_complete, event.mcp_event_id);
        
        setStreamingItems(prev => {
          const updated = new Map(prev);
          // Use composite key based on stream type
          // For summarization, use mcp_event_id to link to specific tool call
          const key = event.stream_type === 'summarization' && event.mcp_event_id
            ? `${event.mcp_event_id}-summarization`
            : `${event.stage_execution_id || 'default'}-${event.stream_type}`;
          
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
            } else {
              // Seed a new entry for completion event with no prior partial entry
              updated.set(key, {
                type: event.stream_type as 'thought' | 'final_answer' | 'summarization',
                content: event.chunk,
                stage_execution_id: event.stage_execution_id,
                mcp_event_id: event.mcp_event_id,
                waitingForDb: true
              });
              console.log('✅ Stream completed (no prior chunks), waiting for DB update to deduplicate');
            }
          } else {
            // Still streaming - update content
            updated.set(key, {
              type: event.stream_type as 'thought' | 'final_answer' | 'summarization',
              content: event.chunk,
              stage_execution_id: event.stage_execution_id,
              mcp_event_id: event.mcp_event_id,
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
  }, [session.session_id, session.status, activeChatStageInProgress]);

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
          
          // Create unique key for this DB item based on its primary identifier
          const itemKey = dbItem.mcp_event_id 
            ? `${dbItem.timestamp_us}-${dbItem.type}-event-${dbItem.mcp_event_id}`
            : `${dbItem.timestamp_us}-${dbItem.type}-content-${dbItem.content?.substring(0, 50)}`;
          
          // Separate matching logic by type for clarity
          let shouldMatch = false;
          
          if (newlyClaimed.has(itemKey)) {
            // Skip already claimed items
            shouldMatch = false;
          } else if (streamingItem.type === 'tool_call') {
            // Tool calls match by type and mcp_event_id only
            shouldMatch = dbItem.type === 'tool_call' && 
                         dbItem.mcp_event_id === streamingItem.mcp_event_id;
          } else if (streamingItem.type === 'summarization') {
            // Summarizations match by type and mcp_event_id
            shouldMatch = dbItem.type === 'summarization' && 
                         dbItem.mcp_event_id === streamingItem.mcp_event_id;
          } else if (streamingItem.type === 'user_message') {
            // User messages match by type and message_id
            shouldMatch = dbItem.type === 'user_message' && 
                         dbItem.messageId === streamingItem.messageId;
          } else {
            // Thoughts and final_answer match by type and content
            shouldMatch = dbItem.type === streamingItem.type && 
                         dbItem.content?.trim() === streamingItem.content?.trim();
          }
          
          if (shouldMatch) {
            // Found unclaimed match!
            updated.delete(key); // Clear streaming item
            newlyClaimed.add(itemKey); // Mark DB item as claimed
            itemsCleared++;
            console.log(`🎯 Matched streaming item to unclaimed DB item (ts: ${dbItem.timestamp_us}, type: ${dbItem.type})`);
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

  // Track chat stage progress for processing indicator (any chat, not just ours)
  useEffect(() => {
    if (!session.session_id) return;
    
    const handleStageEvent = (event: any) => {
      // Only track chat stages (those with chat_id)
      if (!event.chat_id) return;
      
      if (event.type === 'stage.started') {
        console.log('💬 Chat stage started (any user), showing processing indicator');
        setActiveChatStageInProgress(true);
      } else if (event.type === 'stage.completed' || event.type === 'stage.failed') {
        console.log('💬 Chat stage ended, hiding processing indicator');
        setActiveChatStageInProgress(false);
      }
    };
    
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${session.session_id}`,
      handleStageEvent
    );
    
    return () => unsubscribe();
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
            {Array.from(streamingItems.entries())
              // Sort by type to ensure thoughts appear before final answers
              .sort(([_keyA, itemA], [_keyB, itemB]) => {
                const priorityA = itemA.type === 'thought' ? 0 : 1;
                const priorityB = itemB.type === 'thought' ? 0 : 1;
                return priorityA - priorityB;
              })
              .map(([entryKey, entryValue]) => (
                <StreamingItemRenderer key={entryKey} item={entryValue} />
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
            {filteredChatFlow.map((item) => (
              <ChatFlowItem 
                key={`${item.type}-${item.timestamp_us}`} 
                item={item}
                isCollapsed={item.stageId ? collapsedStages.get(item.stageId) || false : false}
                onToggleCollapse={item.stageId ? () => handleToggleStage(item.stageId!) : undefined}
              />
            ))}
            
            {/* Show streaming items at the end (will be cleared by deduplication when DB data arrives) */}
            {displayedStreamingItems.map(([entryKey, entryValue]) => (
              <StreamingItemRenderer key={entryKey} item={entryValue} />
            ))}

            {/* Processing indicator at bottom when session/chat is in progress OR when there are streaming items */}
            {(session.status === 'in_progress' || streamingItems.size > 0 || activeChatStageInProgress) && <ProcessingIndicator />}
          </>
        )}
      </Box>
    </Card>
  );
}

export default ConversationTimeline;
