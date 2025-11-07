import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useChatState } from '../../hooks/useChatState';
import { apiClient } from '../../services/api';
import { websocketService } from '../../services/websocketService';
import type { Chat, ChatUserMessage } from '../../types';

// Mock dependencies
vi.mock('../../services/api');
vi.mock('../../services/websocketService');

describe('useChatState', () => {
  const mockSessionId = 'test-session-123';
  const mockChatId = 'chat-456';
  const mockChat: Chat = {
    chat_id: mockChatId,
    session_id: mockSessionId,
    created_by: 'test-user',
    created_at_us: Date.now() * 1000,
    conversation_history: '[]',
    chain_id: 'default-chain',
    mcp_selection: null,
    context_captured_at_us: Date.now() * 1000,
    pod_id: null,
    last_interaction_at: null,
  };

  let unsubscribeMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Set up WebSocket mock for all tests
    unsubscribeMock = vi.fn();
    vi.mocked(websocketService.subscribeToChannel).mockReturnValue(unsubscribeMock);
    
    // Set up default availability check mock (can be overridden in specific tests)
    vi.mocked(apiClient.checkChatAvailable).mockResolvedValue({ 
      available: true, 
      reason: 'Session completed' 
    });
  });

  describe('Chat availability', () => {
    it('should check chat availability on mount', async () => {
      const mockAvailability = { available: true, reason: 'Session completed' };
      vi.mocked(apiClient.checkChatAvailable).mockResolvedValue(mockAvailability);

      const { result } = renderHook(() => useChatState(mockSessionId));

      await waitFor(() => {
        expect(apiClient.checkChatAvailable).toHaveBeenCalledWith(mockSessionId);
        expect(result.current.isAvailable).toBe(true);
        expect(result.current.availabilityReason).toBe('Session completed');
      });
    });
  });

  describe('Chat creation and messaging', () => {
    it('should create chat and send messages successfully', async () => {
      vi.mocked(apiClient.createChat).mockResolvedValue(mockChat);
      
      const mockMessage: ChatUserMessage = {
        message_id: 'msg-123',
        chat_id: mockChatId,
        content: 'Hello AI',
        author: 'test-user',
        created_at_us: Date.now() * 1000,
      };
      vi.mocked(apiClient.sendChatMessage).mockResolvedValue(mockMessage);

      const { result } = renderHook(() => useChatState(mockSessionId));

      // Create chat
      await act(async () => {
        await result.current.createChat();
      });

      expect(result.current.chat).toEqual(mockChat);

      // Send message
      await act(async () => {
        await result.current.sendMessage('Hello AI', 'test-user');
      });

      expect(result.current.userMessages).toHaveLength(1);
      expect(result.current.userMessages[0]).toEqual(mockMessage);
      expect(apiClient.sendChatMessage).toHaveBeenCalledWith(mockChatId, 'Hello AI', 'test-user');
    });

    it('should throw error when sending without initialized chat', async () => {
      const { result } = renderHook(() => useChatState(mockSessionId));

      await expect(
        act(async () => {
          await result.current.sendMessage('Test', 'user');
        })
      ).rejects.toThrow('Chat not initialized');
    });
  });

  describe('WebSocket integration', () => {
    it('should track active execution via WebSocket events', async () => {
      vi.mocked(apiClient.createChat).mockResolvedValue(mockChat);
      const mockMessage: ChatUserMessage = {
        message_id: 'msg-123',
        chat_id: mockChatId,
        content: 'Test',
        author: 'user',
        created_at_us: Date.now() * 1000,
      };
      vi.mocked(apiClient.sendChatMessage).mockResolvedValue(mockMessage);

      const { result } = renderHook(() => useChatState(mockSessionId));

      await act(async () => {
        await result.current.createChat();
      });

      await waitFor(() => {
        expect(result.current.chat).not.toBeNull();
      });

      await act(async () => {
        await result.current.sendMessage('Test', 'user');
      });

      // Get WebSocket handler
      const subscribeCall = vi.mocked(websocketService.subscribeToChannel).mock.calls[0];
      const wsHandler = subscribeCall[1];

      // Simulate stage.started event
      act(() => {
        wsHandler({
          type: 'stage.started',
          chat_id: mockChatId,
          stage_id: 'execution-789',
        });
      });

      expect(result.current.activeExecutionId).toBe('execution-789');
      expect(result.current.sendingMessage).toBe(false);

      // Stage completes
      act(() => {
        wsHandler({ type: 'stage.completed', chat_id: mockChatId });
      });

      expect(result.current.activeExecutionId).toBeNull();
    });

    it('should unsubscribe from WebSocket on unmount', async () => {
      vi.mocked(apiClient.createChat).mockResolvedValue(mockChat);

      const { result, unmount } = renderHook(() => useChatState(mockSessionId));

      await act(async () => {
        await result.current.createChat();
      });

      unmount();

      expect(unsubscribeMock).toHaveBeenCalled();
    });
  });

  describe('Execution cancellation', () => {
    it('should cancel active execution', async () => {
      vi.mocked(apiClient.createChat).mockResolvedValue(mockChat);
      vi.mocked(apiClient.cancelChatExecution).mockResolvedValue({
        success: true,
        message: 'Cancelled',
      });

      const mockMessage: ChatUserMessage = {
        message_id: 'msg-1',
        chat_id: mockChatId,
        content: 'Test',
        author: 'user',
        created_at_us: Date.now() * 1000,
      };
      vi.mocked(apiClient.sendChatMessage).mockResolvedValue(mockMessage);

      const { result } = renderHook(() => useChatState(mockSessionId));

      await act(async () => {
        await result.current.createChat();
      });

      await waitFor(() => {
        expect(result.current.chat).not.toBeNull();
      });

      await act(async () => {
        await result.current.sendMessage('Test', 'user');
      });

      // Set active execution via WebSocket
      const subscribeCall = vi.mocked(websocketService.subscribeToChannel).mock.calls[0];
      const wsHandler = subscribeCall[1];
      act(() => {
        wsHandler({ type: 'stage.started', chat_id: mockChatId, stage_id: 'exec-123' });
      });

      expect(result.current.activeExecutionId).toBe('exec-123');

      // Cancel
      await act(async () => {
        await result.current.cancelExecution();
      });

      expect(apiClient.cancelChatExecution).toHaveBeenCalledWith('exec-123');
      expect(result.current.canceling).toBe(true);
    });

    it('should throw error when canceling without active execution', async () => {
      vi.mocked(apiClient.createChat).mockResolvedValue(mockChat);
      
      const { result } = renderHook(() => useChatState(mockSessionId));

      await act(async () => {
        await result.current.createChat();
      });

      await expect(
        act(async () => {
          await result.current.cancelExecution();
        })
      ).rejects.toThrow('No active execution to cancel');
    });
  });
});
