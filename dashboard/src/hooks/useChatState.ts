import { useState, useCallback, useEffect, useRef } from 'react';
import { apiClient } from '../services/api';
import { websocketService } from '../services/websocketService';
import type { Chat, ChatUserMessage, StageExecution } from '../types';

interface ChatState {
  chat: Chat | null;
  userMessages: ChatUserMessage[];
  assistantResponses: Map<string, StageExecution>; // message_id -> stage execution
  loading: boolean;
  error: string | null;
  isAvailable: boolean;
  availabilityReason?: string;
  sendingMessage: boolean; // Track when a message is being sent
  activeExecutionId: string | null; // Track active execution for cancellation
  canceling: boolean; // Track if cancellation is in progress
}

export function useChatState(sessionId: string, sessionStatus?: string) {
  const [state, setState] = useState<ChatState>({
    chat: null,
    userMessages: [],
    assistantResponses: new Map(),
    loading: false,
    error: null,
    isAvailable: false,
    sendingMessage: false,
    activeExecutionId: null,
    canceling: false,
  });

  // Track the message ID we're waiting for processing to start
  const pendingMessageIdRef = useRef<string | null>(null);
  // Safety timeout to clear sending state if WebSocket event never arrives
  const sendingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

    // Set sending state immediately
    setState(prev => ({ ...prev, sendingMessage: true }));

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
        // DON'T clear sendingMessage yet - wait for stage.started event from WebSocket
      }));

      // Store the message ID so we know which processing to wait for
      pendingMessageIdRef.current = message.message_id;

      // Set safety timeout (30 seconds) in case WebSocket event never arrives
      if (sendingTimeoutRef.current) {
        clearTimeout(sendingTimeoutRef.current);
      }
      sendingTimeoutRef.current = setTimeout(() => {
        console.warn('💬 Chat processing timeout - clearing sending indicator');
        setState(prev => ({ ...prev, sendingMessage: false }));
        pendingMessageIdRef.current = null;
        sendingTimeoutRef.current = null;
      }, 30000); // 30 seconds

      return message;
    } catch (error: any) {
      // Remove temp message on error
      setState(prev => ({
        ...prev,
        userMessages: prev.userMessages.filter(m => m.message_id !== tempMessage.message_id),
        error: error.message || 'Failed to send message',
        sendingMessage: false, // Clear sending state on error
      }));
      pendingMessageIdRef.current = null;
      if (sendingTimeoutRef.current) {
        clearTimeout(sendingTimeoutRef.current);
        sendingTimeoutRef.current = null;
      }
      throw error;
    }
  }, [state.chat]);

  // Cancel active chat execution
  const cancelExecution = useCallback(async () => {
    if (!state.activeExecutionId) {
      throw new Error('No active execution to cancel');
    }

    setState(prev => ({ ...prev, canceling: true }));

    try {
      await apiClient.cancelChatExecution(state.activeExecutionId);
      // Success - state will be cleared by stage.completed/failed event
    } catch (error: any) {
      setState(prev => ({ ...prev, canceling: false }));
      throw error;
    }
  }, [state.activeExecutionId, state.canceling]);

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

  // Subscribe to WebSocket events to detect when chat processing starts
  useEffect(() => {
    if (!sessionId || !state.chat) return;

    const handleStageEvent = (event: any) => {
      // Capture stage_id (execution ID) when stage starts
      if (
        event.type === 'stage.started' && 
        event.chat_id === state.chat?.chat_id &&
        pendingMessageIdRef.current // We're waiting for a response
      ) {
        setState(prev => ({ 
          ...prev, 
          sendingMessage: false,
          activeExecutionId: event.stage_id // Track stage_id for cancellation
        }));
        pendingMessageIdRef.current = null;
        // Clear the safety timeout
        if (sendingTimeoutRef.current) {
          clearTimeout(sendingTimeoutRef.current);
          sendingTimeoutRef.current = null;
        }
      }

      // Clear execution ID and canceling state when stage completes/fails
      if (
        (event.type === 'stage.completed' || event.type === 'stage.failed') &&
        event.chat_id === state.chat?.chat_id
      ) {
        setState(prev => ({ 
          ...prev, 
          sendingMessage: false,
          activeExecutionId: null, // Clear tracked execution
          canceling: false // Clear canceling state
        }));
        pendingMessageIdRef.current = null;
        // Clear the safety timeout
        if (sendingTimeoutRef.current) {
          clearTimeout(sendingTimeoutRef.current);
          sendingTimeoutRef.current = null;
        }
      }
    };

    // Subscribe to session channel for stage events
    const unsubscribe = websocketService.subscribeToChannel(
      `session:${sessionId}`,
      handleStageEvent
    );

    // Cleanup function
    return () => {
      unsubscribe();
      // Clear timeout on unmount
      if (sendingTimeoutRef.current) {
        clearTimeout(sendingTimeoutRef.current);
        sendingTimeoutRef.current = null;
      }
    };
  }, [sessionId, state.chat]);

  return {
    ...state,
    createChat,
    sendMessage,
    cancelExecution,
    addAssistantResponse,
    checkAvailability,
  };
}

