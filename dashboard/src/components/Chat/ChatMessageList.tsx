import { useRef, useEffect, useState, useCallback } from 'react';
import { Box, Typography, Paper } from '@mui/material';
import { Psychology } from '@mui/icons-material';
import ChatUserMessageCard from './ChatUserMessageCard';
import ChatAssistantMessageCard from './ChatAssistantMessageCard';
import TypingIndicator from '../TypingIndicator';
import StreamingContentRenderer, { type StreamingItem } from '../StreamingContentRenderer';
import { websocketService } from '../../services/websocketService';
import { apiClient } from '../../services/api';
import type { ChatUserMessage, StageExecution, DetailedSession } from '../../types';
import { STAGE_STATUS, isValidStageStatus, type StageStatus } from '../../utils/statusConstants';
import { useAdvancedAutoScroll } from '../../hooks/useAdvancedAutoScroll';
import { 
  LLM_EVENTS, 
  STREAMING_CONTENT_TYPES, 
  parseStreamingContentType 
} from '../../utils/eventTypes';

interface ChatMessageListProps {
  sessionId: string;
  chatId: string;
}

// Message types for the chat list
interface UserMessageItem extends ChatUserMessage {
  type: 'user';
}

interface AssistantMessageItem extends StageExecution {
  type: 'assistant';
}

type ChatMessage = UserMessageItem | AssistantMessageItem;

// API response types
interface ChatMessagesResponse {
  messages: ChatUserMessage[];
}

// WebSocket event types
interface StageStartedEvent {
  type: 'stage.started';
  chat_id: string;
  stage_execution_id: string;
  stage_name: string;
  timestamp_us?: number;
  chat_user_message_id?: string;
  chat_user_message_content?: string;
  chat_user_message_author?: string;
}

interface StageCompletedEvent {
  type: 'stage.completed' | 'stage.failed';
  chat_id: string;
  stage_execution_id: string;
  stage_name: string;
  status: string;
  started_at_us?: number;
  completed_at_us?: number;
  duration_ms?: number;
  error_message?: string;
  timestamp_us?: number;
  chat_user_message_id?: string;
  chat_user_message_content?: string;
  chat_user_message_author?: string;
}

interface ChatUserMessageEvent {
  type: 'chat.user_message';
  chat_id: string;
  message_id: string;
  content: string;
  author: string;
  timestamp_us?: number;
}

type StageEvent = StageStartedEvent | StageCompletedEvent | ChatUserMessageEvent;

/**
 * Maps a WebSocket event status string to a valid StageStatus
 * Falls back to PENDING if the status is not recognized
 */
function mapEventStatusToStageStatus(status: string): StageStatus {
  if (isValidStageStatus(status)) {
    return status as StageStatus;
  }
  // Default to pending for unknown statuses
  console.warn(`Unknown stage status "${status}", defaulting to pending`);
  return STAGE_STATUS.PENDING;
}

export default function ChatMessageList({ sessionId, chatId }: ChatMessageListProps) {
  const scrollContainerRef = useRef<HTMLElement>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [loading, setLoading] = useState(true);
  const [streamingItems, setStreamingItems] = useState<Map<string, StreamingItem>>(new Map());

  // Advanced auto-scroll with user interaction detection
  useAdvancedAutoScroll({
    enabled: true,
    scrollMode: 'container',
    containerRef: scrollContainerRef,
    threshold: 10,
    scrollDelay: 100, // Faster response for chat
    debug: false
  });

  // Fetch chat messages - memoized so it can be called programmatically
  const fetchMessages = useCallback(
    async (showSpinner = true) => {
      if (showSpinner) {
        setLoading(true);
      }

      try {
        // Fetch user messages and stage executions in parallel
        const [userMessagesResponse, sessionDetail] = await Promise.all([
          apiClient.getChatMessages(chatId) as Promise<ChatMessagesResponse>,
          apiClient.getSessionDetail(sessionId) as Promise<DetailedSession>
        ]);
        
        // Extract user messages (type: 'user')
        const userMessages: UserMessageItem[] = userMessagesResponse.messages.map((msg) => ({
          type: 'user',
          message_id: msg.message_id,
          chat_id: msg.chat_id,
          content: msg.content,
          author: msg.author,
          created_at_us: msg.created_at_us
        }));
        
        // Extract stage executions for this chat (type: 'assistant')
        const chatStageExecutions: AssistantMessageItem[] = sessionDetail.stages
          .filter((stage) => stage.chat_id === chatId)
          .map((stage): AssistantMessageItem => ({
            type: 'assistant',
            execution_id: stage.execution_id,
            session_id: stage.session_id,
            stage_id: stage.stage_id,
            stage_index: stage.stage_index,
            stage_name: stage.stage_name,
            agent: stage.agent,
            status: stage.status,
            started_at_us: stage.started_at_us,
            completed_at_us: stage.completed_at_us,
            duration_ms: stage.duration_ms,
            stage_output: stage.stage_output,
            error_message: stage.error_message,
            chat_id: stage.chat_id,
            chat_user_message_id: stage.chat_user_message_id,
            chat_user_message: stage.chat_user_message,
            llm_interactions: stage.llm_interactions || [],
            mcp_communications: stage.mcp_communications || [],
            llm_interaction_count: stage.llm_interaction_count,
            mcp_communication_count: stage.mcp_communication_count,
            total_interactions: stage.total_interactions,
            stage_interactions_duration_ms: stage.stage_interactions_duration_ms,
            chronological_interactions: stage.chronological_interactions,
            stage_input_tokens: stage.stage_input_tokens,
            stage_output_tokens: stage.stage_output_tokens,
            stage_total_tokens: stage.stage_total_tokens
          }));
        
        // Merge and sort by timestamp
        const allMessages: ChatMessage[] = [...userMessages, ...chatStageExecutions].sort((a, b) => {
          const aTime = a.type === 'user' ? a.created_at_us : (a.started_at_us || 0);
          const bTime = b.type === 'user' ? b.created_at_us : (b.started_at_us || 0);
          return aTime - bTime;
        });
        
        setMessages(allMessages);
      } catch (error) {
        console.error('Failed to fetch chat messages:', error);
      } finally {
        if (showSpinner) {
          setLoading(false);
        }
      }
    },
    [chatId, sessionId]
  );

  // Fetch chat messages on mount
  useEffect(() => {
    void fetchMessages();
  }, [fetchMessages]);

  // Subscribe to stage events and chat messages for real-time updates
  useEffect(() => {
    if (!sessionId || !chatId) return;

    const handleStageEvent = (event: StageEvent) => {
      // Only track stages for this specific chat
      if (event.chat_id !== chatId) return;

      if (event.type === 'stage.started') {
        console.log('💬 Chat response started, showing typing indicator');
        setIsTyping(true);
        
        // If this stage has a user message, add it to messages immediately
        if (event.chat_user_message_content) {
          const userMessage: UserMessageItem = {
            type: 'user',
            message_id: event.chat_user_message_id || `temp-${Date.now()}`,
            chat_id: chatId,
            content: event.chat_user_message_content,
            author: event.chat_user_message_author || 'Unknown',
            created_at_us: event.timestamp_us || Date.now() * 1000
          };
          setMessages(prev => {
            // Check if message already exists
            const exists = prev.some(m => m.type === 'user' && m.message_id === userMessage.message_id);
            if (exists) return prev;
            return [...prev, userMessage];
          });
        }
      } else if (event.type === 'stage.completed' || event.type === 'stage.failed') {
        console.log('💬 Chat response completed, hiding typing indicator');
        setIsTyping(false);
        
        // Clear streaming items for this stage
        setStreamingItems(new Map());
        
        // Map event status to StageExecution status type using constants
        const stageStatus = mapEventStatusToStageStatus(event.status);
        
        // Add or update the assistant's response (partial data, will be hydrated)
        const assistantMessage: Partial<AssistantMessageItem> = {
          type: 'assistant',
          execution_id: event.stage_execution_id,
          stage_name: event.stage_name,
          status: stageStatus,
          started_at_us: event.started_at_us,
          completed_at_us: event.completed_at_us,
          duration_ms: event.duration_ms,
          error_message: event.error_message,
          llm_interactions: [],
          mcp_communications: [],
          chat_user_message: event.chat_user_message_content ? {
            message_id: event.chat_user_message_id || '',
            content: event.chat_user_message_content,
            author: event.chat_user_message_author || 'Unknown',
            created_at_us: event.timestamp_us || Date.now() * 1000
          } : null
        };
        
        setMessages(prev => {
          const existingIndex = prev.findIndex(m => m.type === 'assistant' && m.execution_id === assistantMessage.execution_id);
          if (existingIndex >= 0) {
            // Update existing message
            const updated = [...prev];
            updated[existingIndex] = { ...updated[existingIndex], ...assistantMessage } as ChatMessage;
            return updated;
          }
          // Add new message (will be properly hydrated by fetchMessages)
          return [...prev, assistantMessage as ChatMessage];
        });

        // Hydrate the assistant response with persisted interaction data.
        void fetchMessages(false);
      }
    };

    const handleChatMessage = (event: ChatUserMessageEvent) => {
      // Handle chat.user_message events
      if (event.type === 'chat.user_message' && event.chat_id === chatId) {
        const userMessage: UserMessageItem = {
          type: 'user',
          message_id: event.message_id,
          chat_id: event.chat_id,
          content: event.content,
          author: event.author,
          created_at_us: event.timestamp_us || Date.now() * 1000
        };
        setMessages(prev => {
          // Check if message already exists
          const exists = prev.some(m => m.type === 'user' && m.message_id === userMessage.message_id);
          if (exists) return prev;
          return [...prev, userMessage];
        });
      }
    };

    // Handle streaming events
    const handleStreamEvent = (event: any) => {
      if (event.type === LLM_EVENTS.STREAM_CHUNK) {
        console.log('🌊 Chat received streaming chunk:', event.stream_type, event.is_complete);
        
        setStreamingItems(prev => {
          const updated = new Map(prev);
          // Use composite key based on stream type
          const key = event.stream_type === STREAMING_CONTENT_TYPES.SUMMARIZATION && event.mcp_event_id
            ? `${event.mcp_event_id}-${STREAMING_CONTENT_TYPES.SUMMARIZATION}`
            : `${event.stage_execution_id || 'default'}-${event.stream_type}`;
          
          const streamType = parseStreamingContentType(event.stream_type);
          
          if (event.is_complete) {
            // Stream completed - mark as waiting for DB update
            const existing = prev.get(key);
            if (existing) {
              updated.set(key, {
                ...existing,
                content: event.chunk,
                waitingForDb: true
              });
            } else {
              updated.set(key, {
                type: streamType,
                content: event.chunk,
                stage_execution_id: event.stage_execution_id,
                mcp_event_id: event.mcp_event_id,
                waitingForDb: true
              });
            }
          } else {
            // Still streaming - update content
            updated.set(key, {
              type: streamType,
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

    // Subscribe to session channel for stage, chat, and streaming events
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      (event: any) => {
        if (event.type === LLM_EVENTS.STREAM_CHUNK) {
          handleStreamEvent(event);
        } else {
          handleStageEvent(event);
          if (event.type === 'chat.user_message') {
            handleChatMessage(event);
          }
        }
      }
    );

    return () => unsubscribe();
  }, [sessionId, chatId, fetchMessages]);

  return (
    <Box 
      ref={scrollContainerRef}
      data-autoscroll-container
      sx={{ flex: 1, overflowY: 'auto', p: 2 }}
    >
      {loading ? (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
          Loading messages...
        </Typography>
      ) : messages.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
          No messages yet. Start the conversation!
        </Typography>
      ) : (
        messages.map((msg) => {
          if (msg.type === 'user') {
            return <ChatUserMessageCard key={msg.message_id} message={msg} />;
          } else {
            return <ChatAssistantMessageCard key={msg.execution_id} execution={msg} />;
          }
        })
      )}
      
      {/* Show streaming items in real-time */}
      {streamingItems.size > 0 && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <Psychology sx={{ fontSize: 20, mr: 0.5, color: 'primary.main' }} />
            <Typography variant="caption" color="text.secondary">
              TARSy is thinking...
            </Typography>
          </Box>
          {Array.from(streamingItems.values()).map((item, index) => (
            <StreamingContentRenderer key={`stream-${index}`} item={item} />
          ))}
        </Paper>
      )}
      
      {isTyping && streamingItems.size === 0 && <TypingIndicator />}
    </Box>
  );
}