import { useRef, useEffect, useState, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import ChatUserMessageCard from './ChatUserMessageCard';
import ChatAssistantMessageCard from './ChatAssistantMessageCard';
import TypingIndicator from '../TypingIndicator';
import { websocketService } from '../../services/websocketService';
import { apiClient } from '../../services/api';
import type { ChatUserMessage, StageExecution, DetailedSession } from '../../types';
import { STAGE_STATUS, isValidStageStatus, type StageStatus } from '../../utils/statusConstants';

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
  const bottomRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [loading, setLoading] = useState(true);

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

    // Subscribe to session channel for stage and chat events
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      (event: StageEvent) => {
        handleStageEvent(event);
        if (event.type === 'chat.user_message') {
          handleChatMessage(event);
        }
      }
    );

    return () => unsubscribe();
  }, [sessionId, chatId, fetchMessages]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
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
      {isTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </Box>
  );
}