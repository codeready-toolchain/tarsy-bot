import { useRef, useEffect, useState } from 'react';
import { Box, Typography } from '@mui/material';
import ChatUserMessageCard from './ChatUserMessageCard';
import ChatAssistantMessageCard from './ChatAssistantMessageCard';
import TypingIndicator from '../TypingIndicator';
import { websocketService } from '../../services/websocketService';

interface ChatMessageListProps {
  sessionId: string;
  chatId: string;
}

export default function ChatMessageList({ sessionId, chatId }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [messages] = useState<any[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch chat messages on mount
  useEffect(() => {
    const fetchMessages = async () => {
      try {
        setLoading(true);
        // TODO: Fetch user messages and stage executions for this chat
        // When backend API is ready, fetch and merge messages here
        console.log('Chat messages will be fetched for:', { sessionId, chatId });
      } catch (error) {
        console.error('Failed to fetch chat messages:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchMessages();
  }, [sessionId, chatId]);

  // Subscribe to stage events to show typing indicator during chat processing
  useEffect(() => {
    if (!sessionId || !chatId) return;

    const handleStageEvent = (event: any) => {
      // Only track stages for this specific chat
      if (event.chat_id !== chatId) return;

      if (event.type === 'stage.started') {
        console.log('💬 Chat response started, showing typing indicator');
        setIsTyping(true);
      } else if (event.type === 'stage.completed' || event.type === 'stage.failed') {
        console.log('💬 Chat response completed, hiding typing indicator');
        setIsTyping(false);
      }
    };

    // Subscribe to session channel for stage events
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      handleStageEvent
    );

    return () => unsubscribe();
  }, [sessionId, chatId]);

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

