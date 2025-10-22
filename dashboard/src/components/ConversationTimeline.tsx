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
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import { parseSessionChatFlow, getChatFlowStats } from '../utils/chatFlowParser';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import type { DetailedSession } from '../types';
import ChatFlowItem from './ChatFlowItem';
import CopyButton from './CopyButton';
import { websocketService } from '../services/websocketService';
import { 
  hasMarkdownSyntax, 
  finalAnswerMarkdownComponents, 
  thoughtMarkdownComponents 
} from '../utils/markdownComponents';
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
  type: 'thought' | 'final_answer' | 'summarization' | 'tool_call';
  content?: string; // For thought/final_answer/summarization
  stage_execution_id?: string;
  mcp_event_id?: string; // For tool_call and summarization
  waitingForDb?: boolean; // True when stream completed, waiting for DB confirmation
  // Tool call specific fields
  toolName?: string;
  toolArguments?: any;
  serverName?: string;
}

/**
 * StreamingItemRenderer Component
 * Renders streaming items with proper formatting (Markdown for final answers, hybrid for thoughts/summarizations)
 * Memoized to prevent unnecessary re-renders during rapid streaming updates
 */
const StreamingItemRenderer = memo(({ item }: { item: StreamingItem }) => {
  if (item.type === 'thought') {
    // Render thought with hybrid markdown support (matching DB rendering)
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 1.5, display: 'flex', gap: 1.5 }}>
        <Typography 
          variant="body2" 
          sx={{ 
            fontSize: '1.1rem', 
            lineHeight: 1,
            flexShrink: 0,
            mt: 0.25
          }}
        >
          💭
        </Typography>
        {hasMarkdown ? (
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <ReactMarkdown
              components={thoughtMarkdownComponents}
              skipHtml
            >
              {item.content}
            </ReactMarkdown>
          </Box>
        ) : (
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
        )}
      </Box>
    );
  }
  
  if (item.type === 'summarization') {
    // Render summarization with hybrid markdown support (maintains amber styling)
    const hasMarkdown = hasMarkdownSyntax(item.content || '');
    
    return (
      <Box sx={{ mb: 1.5 }}>
        {/* Header with amber styling */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 0.5 }}>
          <Typography
            variant="body2"
            sx={{
              fontSize: '1.1rem',
              lineHeight: 1,
              flexShrink: 0
            }}
          >
            📋
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              fontSize: '0.75rem',
              color: 'rgba(237, 108, 2, 0.9)',
              mt: 0.25
            }}
          >
            Tool Result Summary
          </Typography>
        </Box>
        {/* Content with subtle left border and dimmed text */}
        <Box 
          sx={{ 
            pl: 3.5,
            ml: 3.5,
            py: 0.5,
            borderLeft: '2px solid rgba(237, 108, 2, 0.2)' // Subtle amber left border
          }}
        >
          {hasMarkdown ? (
            <Box sx={{ 
              '& p': { color: 'text.secondary' }, // Apply dimmed color to markdown paragraphs
              '& li': { color: 'text.secondary' }  // Apply dimmed color to list items
            }}>
              <ReactMarkdown
                components={thoughtMarkdownComponents}
                skipHtml
              >
                {item.content}
              </ReactMarkdown>
            </Box>
          ) : (
            <Typography
              variant="body1"
              sx={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.7,
                fontSize: '1rem',
                color: 'text.secondary' // Slightly dimmed to differentiate from thoughts
              }}
            >
              {item.content}
            </Typography>
          )}
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
  
  // Render final answer with Markdown (matching DB rendering)
  return (
    <Box sx={{ mb: 2, mt: 3 }}>
      <Box sx={{ display: 'flex', gap: 1.5, mb: 1 }}>
        <Typography
          variant="body2"
          sx={{
            fontSize: '1.1rem',
            lineHeight: 1,
            flexShrink: 0
          }}
        >
          🎯
        </Typography>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: 0.5,
            fontSize: '0.75rem',
            color: '#2e7d32',
            mt: 0.25
          }}
        >
          Final Answer
        </Typography>
      </Box>
      <Box sx={{ pl: 3.5 }}>
        <ReactMarkdown
          urlTransform={defaultUrlTransform}
          components={finalAnswerMarkdownComponents}
        >
          {item.content}
        </ReactMarkdown>
      </Box>
    </Box>
  );
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
      } else if (item.type === 'summarization') {
        content += `📋 Tool Result Summary${item.mcp_event_id ? ` (MCP: ${item.mcp_event_id})` : ''}:\n${item.content}\n\n`;
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
      if (event.type === 'mcp.tool_call.started') {
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
          
          // Create unique key for this DB item (timestamp + type + identifier)
          const itemKey = `${dbItem.timestamp_us}-${dbItem.type}-${dbItem.mcp_event_id || dbItem.content?.substring(0, 50)}`;
          
          // Check if: matching type + (content OR mcp_event_id), AND not already claimed
          const typesMatch = dbItem.type === streamingItem.type;
          const contentsMatch = dbItem.content?.trim() === streamingItem.content?.trim();
          
          // For tool calls and summarizations, match by mcp_event_id (communication_id)
          const mcpEventMatches = streamingItem.type === 'tool_call'
            ? dbItem.type === 'tool_call' && dbItem.mcp_event_id === streamingItem.mcp_event_id
            : streamingItem.type === 'summarization'
              ? dbItem.mcp_event_id === streamingItem.mcp_event_id
              : true; // For thoughts/final_answer, ignore mcp_event_id
          
          // Match on either content (for thoughts/final_answer) or mcp_event_id (for tool_call/summarization)
          const shouldMatch = typesMatch && (contentsMatch || streamingItem.type === 'tool_call') && mcpEventMatches && !newlyClaimed.has(itemKey);
          
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
            {chatFlow.map((item) => (
              <ChatFlowItem key={`${item.type}-${item.timestamp_us}`} item={item} />
            ))}
            
            {/* Show streaming items at the end (will be cleared by deduplication when DB data arrives) */}
            {streamingItems.size > 0 && (
              Array.from(streamingItems.entries())
                // Sort by type to ensure thoughts appear before final answers (prevents visual glitches)
                .sort(([_keyA, itemA], [_keyB, itemB]) => {
                  // Type priority: thought = 0, final_answer = 1
                  const priorityA = itemA.type === 'thought' ? 0 : 1;
                  const priorityB = itemB.type === 'thought' ? 0 : 1;
                  return priorityA - priorityB;
                })
                .map(([entryKey, entryValue]) => (
                  <StreamingItemRenderer key={entryKey} item={entryValue} />
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
