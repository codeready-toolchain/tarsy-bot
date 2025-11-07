import { useRef, useEffect, useState, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import ChatUserMessageCard from './ChatUserMessageCard';
import ChatAssistantMessageCard from './ChatAssistantMessageCard';
import TypingIndicator from '../TypingIndicator';
import { websocketService } from '../../services/websocketService';
import { apiClient } from '../../services/api';

interface ChatMessageListProps {
  sessionId: string;
  chatId: string;
}

export default function ChatMessageList({ sessionId, chatId }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<any[]>([]);
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
          apiClient.getChatMessages(chatId),
          apiClient.getSessionDetail(sessionId)
        ]);
        
        // Extract user messages (type: 'user')
        const userMessages = userMessagesResponse.messages.map((msg: any) => ({
          type: 'user',
          message_id: msg.message_id,
          content: msg.content,
          author: msg.author,
          created_at_us: msg.created_at_us
        }));
        
        // Extract stage executions for this chat (type: 'assistant')
        const chatStageExecutions = sessionDetail.stages
          .filter((stage: any) => stage.chat_id === chatId)
          .map((stage: any) => ({
            type: 'assistant',
            execution_id: stage.execution_id,
            stage_name: stage.stage_name,
            status: stage.status,
            started_at_us: stage.started_at_us,
            completed_at_us: stage.completed_at_us,
            stage_output: stage.stage_output,
            error_message: stage.error_message,
            llm_interactions: stage.llm_interactions || [],
            mcp_communications: stage.mcp_communications || [],
            chat_user_message: stage.chat_user_message || null
          }));
        
        // Merge and sort by timestamp
        const allMessages = [...userMessages, ...chatStageExecutions].sort((a, b) => {
          const aTime = (a as any).created_at_us || (a as any).started_at_us || 0;
          const bTime = (b as any).created_at_us || (b as any).started_at_us || 0;
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

    const handleStageEvent = (event: any) => {
      // Only track stages for this specific chat
      if (event.chat_id !== chatId) return;

      if (event.type === 'stage.started') {
        console.log('💬 Chat response started, showing typing indicator');
        setIsTyping(true);
        
        // If this stage has a user message, add it to messages immediately
        if (event.chat_user_message_content) {
          const userMessage = {
            type: 'user',
            message_id: event.chat_user_message_id || `temp-${Date.now()}`,
            content: event.chat_user_message_content,
            author: event.chat_user_message_author || 'Unknown',
            created_at_us: event.timestamp_us || Date.now() * 1000
          };
          setMessages(prev => {
            // Check if message already exists
            const exists = prev.some(m => m.message_id === userMessage.message_id);
            if (exists) return prev;
            return [...prev, userMessage];
          });
        }
      } else if (event.type === 'stage.completed' || event.type === 'stage.failed') {
        console.log('💬 Chat response completed, hiding typing indicator');
        setIsTyping(false);
        
        // Add or update the assistant's response
        const assistantMessage = {
          type: 'assistant',
          execution_id: event.stage_execution_id,
          stage_name: event.stage_name,
          status: event.status,
          started_at_us: event.started_at_us,
          completed_at_us: event.completed_at_us,
          duration_ms: event.duration_ms,
          error_message: event.error_message,
          llm_interactions: [],
          mcp_communications: [],
          chat_user_message: event.chat_user_message_content ? {
            message_id: event.chat_user_message_id,
            content: event.chat_user_message_content,
            author: event.chat_user_message_author,
            created_at_us: event.timestamp_us
          } : null
        };
        
        setMessages(prev => {
          const existingIndex = prev.findIndex(m => m.execution_id === assistantMessage.execution_id);
          if (existingIndex >= 0) {
            // Update existing message
            const updated = [...prev];
            updated[existingIndex] = assistantMessage;
            return updated;
          }
          // Add new message
          return [...prev, assistantMessage];
        });

        // Hydrate the assistant response with persisted interaction data.
        void fetchMessages(false);
      }
    };

    const handleChatMessage = (event: any) => {
      // Handle chat.user_message events
      if (event.type === 'chat.user_message' && event.chat_id === chatId) {
        const userMessage = {
          type: 'user',
          message_id: event.message_id,
          content: event.content,
          author: event.author,
          created_at_us: event.timestamp_us
        };
        setMessages(prev => {
          // Check if message already exists
          const exists = prev.some(m => m.message_id === userMessage.message_id);
          if (exists) return prev;
          return [...prev, userMessage];
        });
      }
    };

    // Subscribe to session channel for stage and chat events
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      (event: any) => {
        handleStageEvent(event);
        handleChatMessage(event);
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
        messages.map((msg) => (
          msg.type === 'user' ? (
            <ChatUserMessageCard key={msg.message_id} message={msg} />
          ) : (
            <ChatAssistantMessageCard key={msg.execution_id} execution={msg} />
          )
        ))
      )}
      {isTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </Box>
  );
}

