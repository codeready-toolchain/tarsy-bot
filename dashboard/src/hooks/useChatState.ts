import { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../services/api';
import type { Chat, ChatUserMessage, StageExecution } from '../types';

interface ChatState {
  chat: Chat | null;
  userMessages: ChatUserMessage[];
  assistantResponses: Map<string, StageExecution>; // message_id -> stage execution
  loading: boolean;
  error: string | null;
  isAvailable: boolean;
  availabilityReason?: string;
}

export function useChatState(sessionId: string, sessionStatus?: string) {
  const [state, setState] = useState<ChatState>({
    chat: null,
    userMessages: [],
    assistantResponses: new Map(),
    loading: false,
    error: null,
    isAvailable: false,
  });

  // Check chat availability on mount
  const checkAvailability = useCallback(async () => {
    try {
      const result = await apiClient.checkChatAvailable(sessionId);
      setState(prev => ({
        ...prev,
        isAvailable: result.available,
        availabilityReason: result.reason,
      }));
    } catch (error) {
      console.error('Failed to check chat availability:', error);
    }
  }, [sessionId]);

  // Create chat
  const createChat = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const chat = await apiClient.createChat(sessionId);
      setState(prev => ({ ...prev, chat, loading: false }));
      return chat;
    } catch (error: any) {
      const errorMessage = error.message || 'Failed to create chat';
      setState(prev => ({ ...prev, error: errorMessage, loading: false }));
      throw error;
    }
  }, [sessionId]);

  // Send message with optimistic update
  const sendMessage = useCallback(async (content: string, author: string) => {
    if (!state.chat) {
      throw new Error('Chat not initialized');
    }

    // Optimistic update
    const tempMessage: ChatUserMessage = {
      message_id: `temp-${Date.now()}`,
      chat_id: state.chat.chat_id,
      content,
      author,
      created_at_us: Date.now() * 1000,
    };

    setState(prev => ({
      ...prev,
      userMessages: [...prev.userMessages, tempMessage],
    }));

    try {
      const message = await apiClient.sendChatMessage(state.chat.chat_id, content, author);
      
      // Replace temp message with real one
      setState(prev => ({
        ...prev,
        userMessages: prev.userMessages.map(m => 
          m.message_id === tempMessage.message_id ? message : m
        ),
      }));

      return message;
    } catch (error: any) {
      // Remove temp message on error
      setState(prev => ({
        ...prev,
        userMessages: prev.userMessages.filter(m => m.message_id !== tempMessage.message_id),
        error: error.message || 'Failed to send message',
      }));
      throw error;
    }
  }, [state.chat]);

  // Add assistant response (from WebSocket stage execution)
  const addAssistantResponse = useCallback((messageId: string, execution: StageExecution) => {
    setState(prev => {
      const newResponses = new Map(prev.assistantResponses);
      newResponses.set(messageId, execution);
      return { ...prev, assistantResponses: newResponses };
    });
  }, []);

  // Check availability on mount and when session status changes (e.g., in_progress -> completed)
  useEffect(() => {
    checkAvailability();
  }, [checkAvailability, sessionStatus]);

  return {
    ...state,
    createChat,
    sendMessage,
    addAssistantResponse,
    checkAvailability,
  };
}

