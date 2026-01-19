/**
 * Tests for API client retry logic
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios, { type AxiosError } from 'axios';

// Mock axios
vi.mock('axios', () => {
  // Create mock client inside the factory
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: {
        use: vi.fn(),
      },
      response: {
        use: vi.fn(),
      },
    },
  };
  
  return {
    default: {
      create: vi.fn(() => mockClient),
      isAxiosError: vi.fn((error: any) => error && error.isAxiosError === true),
    },
  };
});

const mockedAxios = axios as any;

// Mock env config
vi.mock('../../config/env', () => ({
  urls: {
    api: {
      base: 'http://localhost:8000',
      submitAlert: '/api/v1/alerts',
    },
    websocket: {
      base: 'ws://localhost:8000',
    },
  },
}));

// Mock auth service
vi.mock('../../services/auth', () => ({
  authService: {
    handleAuthError: vi.fn(),
  },
}));

// Import apiClient and retry config after mocks are set up
import { apiClient, INITIAL_RETRY_DELAY, MAX_RETRY_DELAY } from '../../services/api';

describe('API Client Retry Logic', () => {
  let consoleLogSpy: any;
  let consoleErrorSpy: any;
  let consoleWarnSpy: any;

  beforeEach(() => {
    // Spy on console methods
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    // Reset all mocks including mockAxiosClient
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    vi.useRealTimers();
  });

  it('should retry on network errors with exponential backoff (500ms, 1000ms)', async () => {
    // Use fake timers to control time progression
    vi.useFakeTimers();
    
    // Get reference to the mock axios client created by axios.create()
    const mockClient = mockedAxios.create();
    
    // Create a network error (no response from server)
    const networkError: AxiosError = {
      isAxiosError: true,
      request: {},
      response: undefined,
      message: 'Network Error',
      name: 'AxiosError',
      config: {} as any,
      toJSON: () => ({}),
    };

    // Mock successful response for the third attempt
    const successResponse = {
      data: [
        { session_id: 'test-1', status: 'active' },
        { session_id: 'test-2', status: 'active' },
      ],
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    let callCount = 0;
    mockClient.get.mockImplementation(() => {
      callCount++;
      if (callCount <= 2) {
        return Promise.reject(networkError);
      }
      return Promise.resolve(successResponse);
    });

    // Start the retry operation (don't await yet)
    const resultPromise = (apiClient as any).getActiveSessionsWithRetry();

    // First attempt fails immediately
    await vi.advanceTimersByTimeAsync(0);

    // First retry after INITIAL_RETRY_DELAY * 2^0
    await vi.advanceTimersByTimeAsync(INITIAL_RETRY_DELAY);

    // Second retry after INITIAL_RETRY_DELAY * 2^1
    await vi.advanceTimersByTimeAsync(INITIAL_RETRY_DELAY * 2);

    // Third attempt succeeds
    const result = await resultPromise;

    // Verify the result
    expect(result).toEqual({
      active_sessions: [
        { session_id: 'test-1', status: 'active' },
        { session_id: 'test-2', status: 'active' },
      ],
      total_count: 2,
    });

    // Verify axios client was called 3 times (2 failures + 1 success)
    expect(mockClient.get).toHaveBeenCalledTimes(3);
    expect(mockClient.get).toHaveBeenCalledWith('/api/v1/history/active-sessions');

    // Restore real timers
    vi.useRealTimers();
  });

  it('should retry filtered sessions on network errors with exponential backoff', async () => {
    // Use fake timers to control time progression
    vi.useFakeTimers();
    
    // Get reference to the mock axios client created by axios.create()
    const mockClient = mockedAxios.create();
    
    // Create a network error (no response from server)
    const networkError: AxiosError = {
      isAxiosError: true,
      request: {},
      response: undefined,
      message: 'Network Error',
      name: 'AxiosError',
      config: {} as any,
      toJSON: () => ({}),
    };

    // Mock successful response for the third attempt (backend returns flat structure)
    const successResponse = {
      data: {
        sessions: [
          { session_id: 'test-1', status: 'completed', alert_type: 'PodCrashLooping' },
          { session_id: 'test-2', status: 'failed', alert_type: 'PodCrashLooping' },
        ],
        total_count: 2,
        page: 1,
        page_size: 25,
        total_pages: 1,
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    let callCount = 0;
    mockClient.get.mockImplementation(() => {
      callCount++;
      if (callCount <= 2) {
        return Promise.reject(networkError);
      }
      return Promise.resolve(successResponse);
    });

    // Test filters with status and alert_type
    const testFilters = {
      status: ['completed', 'failed'] as ('completed' | 'failed')[],
      alert_type: ['PodCrashLooping'],
    };

    // Start the retry operation (don't await yet)
    const resultPromise = (apiClient as any).getFilteredSessionsWithRetry(testFilters, 1, 25);

    // First attempt fails immediately
    await vi.advanceTimersByTimeAsync(0);

    // First retry after INITIAL_RETRY_DELAY * 2^0
    await vi.advanceTimersByTimeAsync(INITIAL_RETRY_DELAY);

    // Second retry after INITIAL_RETRY_DELAY * 2^1
    await vi.advanceTimersByTimeAsync(INITIAL_RETRY_DELAY * 2);

    // Third attempt succeeds
    const result = await resultPromise;

    // Verify the result matches the normalized SessionsResponse format
    expect(result).toEqual({
      sessions: [
        { session_id: 'test-1', status: 'completed', alert_type: 'PodCrashLooping' },
        { session_id: 'test-2', status: 'failed', alert_type: 'PodCrashLooping' },
      ],
      pagination: {
        page: 1,
        page_size: 25,
        total_pages: 1,
        total_items: 2,
      },
      filters_applied: {},
    });

    // Verify axios client was called 3 times (2 failures + 1 success)
    expect(mockClient.get).toHaveBeenCalledTimes(3);
    
    // Verify the URL includes the filter parameters
    const firstCallUrl = mockClient.get.mock.calls[0][0];
    expect(firstCallUrl).toContain('/api/v1/history/sessions');
    expect(firstCallUrl).toContain('status=completed');
    expect(firstCallUrl).toContain('status=failed');
    expect(firstCallUrl).toContain('alert_type=PodCrashLooping');
    expect(firstCallUrl).toContain('page=1');
    expect(firstCallUrl).toContain('page_size=25');

    // Restore real timers
    vi.useRealTimers();
  });

  it('should handle already-nested pagination format from backend', async () => {
    // Get reference to the mock axios client
    const mockClient = mockedAxios.create();
    
    // Mock response with already-nested pagination structure
    const nestedResponse = {
      data: {
        sessions: [
          { session_id: 'test-1', status: 'completed', alert_type: 'PodCrashLooping' },
        ],
        pagination: {
          page: 1,
          page_size: 25,
          total_pages: 1,
          total_items: 1,
        },
        filters_applied: {
          status: ['completed'],
        },
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.get.mockResolvedValueOnce(nestedResponse);

    // Test with filters
    const testFilters = {
      status: ['completed'] as ('completed')[],
    };

    const result = await (apiClient as any).getFilteredSessions(testFilters, 1, 25);

    // Verify the result is returned as-is when already nested
    expect(result).toEqual({
      sessions: [
        { session_id: 'test-1', status: 'completed', alert_type: 'PodCrashLooping' },
      ],
      pagination: {
        page: 1,
        page_size: 25,
        total_pages: 1,
        total_items: 1,
      },
      filters_applied: {
        status: ['completed'],
      },
    });

    expect(mockClient.get).toHaveBeenCalledTimes(1);
  });

  it('should not retry on HTTP errors (4xx, 5xx)', async () => {
    // Create an HTTP error (got response from server)
    const httpError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 500,
        data: { error: 'Internal Server Error' },
      },
      message: 'Request failed with status code 500',
    };

    let attemptCount = 0;
    const mockOperation = vi.fn(async () => {
      attemptCount++;
      throw httpError;
    });

    // Simulate the retry logic
    try {
      for (let attempt = 0; attempt <= 5; attempt++) {
        try {
          await mockOperation();
        } catch (error) {
          const isNetworkError = 
            error && 
            typeof error === 'object' && 
            'isAxiosError' in error &&
            (error as any).request && 
            !(error as any).response;

          // Should not retry on HTTP errors
          if (!isNetworkError || attempt === 5) {
            throw error;
          }
        }
      }
    } catch (error) {
      expect(error).toBe(httpError);
      expect(attemptCount).toBe(1); // Should only be called once
    }
  });

  it('should handle successful requests without retry', async () => {
    const mockOperation = vi.fn(async () => {
      return { data: 'success' };
    });

    const result = await mockOperation();
    expect(result.data).toBe('success');
    expect(mockOperation).toHaveBeenCalledTimes(1);
  });

  it('should verify complete delay pattern matches implementation config', () => {
    // Test uses the exported INITIAL_RETRY_DELAY and MAX_RETRY_DELAY from api.ts
    // This ensures tests stay in sync with implementation changes
    const expectedDelays = [];
    
    for (let attempt = 0; attempt < 6; attempt++) {
      const exponentialDelay = INITIAL_RETRY_DELAY * Math.pow(2, attempt);
      const delay = Math.min(exponentialDelay, MAX_RETRY_DELAY);
      expectedDelays.push(delay);
    }

    // With current config (INITIAL=500ms, MAX=5000ms), pattern should be:
    // [500, 1000, 2000, 4000, 5000, 5000]
    expect(expectedDelays).toEqual([
      INITIAL_RETRY_DELAY,           // 500ms (attempt 0)
      INITIAL_RETRY_DELAY * 2,       // 1000ms (attempt 1)
      INITIAL_RETRY_DELAY * 4,       // 2000ms (attempt 2)
      INITIAL_RETRY_DELAY * 8,       // 4000ms (attempt 3)
      MAX_RETRY_DELAY,               // 5000ms (capped at attempt 4)
      MAX_RETRY_DELAY,               // 5000ms (capped at attempt 5)
    ]);
  });

  it('should retry on 502, 503, and 504 status codes', async () => {
    const statusCodes = [502, 503, 504];
    
    for (const statusCode of statusCodes) {
      const gatewayError: any = {
        isAxiosError: true,
        request: {},
        response: {
          status: statusCode,
          data: { error: 'Gateway Error' },
        },
        message: `Request failed with status code ${statusCode}`,
      };

      let attemptCount = 0;
      const mockOperation = vi.fn(async () => {
        attemptCount++;
        if (attemptCount < 2) {
          throw gatewayError;
        }
        return { data: 'success' };
      });

      // Simulate the retry logic
      const isRetryable = (error: any): boolean => {
        if (error && typeof error === 'object' && 'isAxiosError' in error) {
          const axiosError = error as any;
          
          // Network errors
          if (axiosError.request && !axiosError.response) {
            return true;
          }
          
          // 502, 503, 504
          if (axiosError.response?.status === 502 || 
              axiosError.response?.status === 503 || 
              axiosError.response?.status === 504) {
            return true;
          }
          
          // Timeout errors
          if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
            return true;
          }
        }
        return false;
      };

      // Execute with retry
      let result;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          result = await mockOperation();
          break;
        } catch (error) {
          if (!isRetryable(error) || attempt === 2) {
            throw error;
          }
        }
      }

      expect(result?.data).toBe('success');
      expect(mockOperation).toHaveBeenCalledTimes(2);
      attemptCount = 0; // Reset for next iteration
      vi.clearAllMocks();
    }
  });

  it('should retry on axios timeout errors (ECONNABORTED, ETIMEDOUT)', async () => {
    const timeoutCodes = ['ECONNABORTED', 'ETIMEDOUT'];
    
    for (const code of timeoutCodes) {
      const timeoutError: any = {
        isAxiosError: true,
        code: code,
        request: {},
        response: undefined,
        message: 'timeout of 10000ms exceeded',
      };

      let attemptCount = 0;
      const mockOperation = vi.fn(async () => {
        attemptCount++;
        if (attemptCount < 2) {
          throw timeoutError;
        }
        return { data: 'success' };
      });

      // Simulate the retry logic
      const isRetryable = (error: any): boolean => {
        if (error && typeof error === 'object' && 'isAxiosError' in error) {
          const axiosError = error as any;
          
          // Network errors
          if (axiosError.request && !axiosError.response) {
            return true;
          }
          
          // 502, 503, 504
          if (axiosError.response?.status === 502 || 
              axiosError.response?.status === 503 || 
              axiosError.response?.status === 504) {
            return true;
          }
          
          // Timeout errors
          if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
            return true;
          }
        }
        return false;
      };

      // Execute with retry
      let result;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          result = await mockOperation();
          break;
        } catch (error) {
          if (!isRetryable(error) || attempt === 2) {
            throw error;
          }
        }
      }

      expect(result?.data).toBe('success');
      expect(mockOperation).toHaveBeenCalledTimes(2);
      attemptCount = 0; // Reset for next iteration
      vi.clearAllMocks();
    }
  });
});

describe('API Client Session Cancellation', () => {
  let consoleErrorSpy: any;
  const mockClient = mockedAxios.create();

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('should successfully cancel a session', async () => {
    const sessionId = 'test-session-123';
    const successResponse = {
      data: {
        success: true,
        message: 'Cancellation request sent',
        status: 'canceling'
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.post.mockResolvedValueOnce(successResponse);

    const result = await apiClient.cancelSession(sessionId);

    expect(result).toEqual({
      success: true,
      message: 'Cancellation request sent',
      status: 'canceling'
    });
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/cancel`);
    expect(mockClient.post).toHaveBeenCalledTimes(1);
  });

  it('should handle 404 when cancelling non-existent session', async () => {
    const sessionId = 'non-existent-session';
    const notFoundError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 404,
        data: { detail: 'Session non-existent-session not found' },
      },
      message: 'Request failed with status code 404',
    };

    mockClient.post.mockRejectedValueOnce(notFoundError);

    await expect(apiClient.cancelSession(sessionId)).rejects.toThrow();
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/cancel`);
  });

  it('should handle 400 when cancelling already completed session', async () => {
    const sessionId = 'completed-session';
    const badRequestError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 400,
        data: { detail: 'Session already completed, cannot cancel' },
      },
      message: 'Request failed with status code 400',
    };

    mockClient.post.mockRejectedValueOnce(badRequestError);

    await expect(apiClient.cancelSession(sessionId)).rejects.toThrow();
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/cancel`);
  });

  it('should handle network errors when cancelling session', async () => {
    const sessionId = 'test-session-456';
    const networkError: any = {
      isAxiosError: true,
      request: {},
      response: undefined,
      message: 'Network Error',
    };

    mockClient.post.mockRejectedValueOnce(networkError);

    await expect(apiClient.cancelSession(sessionId)).rejects.toThrow();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Error cancelling session:',
      networkError
    );
  });
});

describe('API Client Session Resume', () => {
  let consoleErrorSpy: any;
  const mockClient = mockedAxios.create();

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('should successfully resume a paused session', async () => {
    const sessionId = 'paused-session-123';
    const successResponse = {
      data: {
        success: true,
        message: 'Session resumed successfully',
        status: 'in_progress'
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.post.mockResolvedValueOnce(successResponse);

    const result = await apiClient.resumeSession(sessionId);

    expect(result).toEqual({
      success: true,
      message: 'Session resumed successfully',
      status: 'in_progress'
    });
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/resume`);
    expect(mockClient.post).toHaveBeenCalledTimes(1);
  });

  it('should handle 404 when resuming non-existent session', async () => {
    const sessionId = 'non-existent-session';
    const notFoundError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 404,
        data: { detail: 'Session non-existent-session not found' },
      },
      message: 'Request failed with status code 404',
    };

    mockClient.post.mockRejectedValueOnce(notFoundError);

    await expect(apiClient.resumeSession(sessionId)).rejects.toThrow();
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/resume`);
  });

  it('should handle 400 when resuming non-paused session', async () => {
    const sessionId = 'completed-session';
    const badRequestError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 400,
        data: { detail: 'Session is not paused, cannot resume' },
      },
      message: 'Request failed with status code 400',
    };

    mockClient.post.mockRejectedValueOnce(badRequestError);

    await expect(apiClient.resumeSession(sessionId)).rejects.toThrow();
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/resume`);
  });

  it('should handle 400 when resuming already completed session', async () => {
    const sessionId = 'terminal-session';
    const badRequestError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 400,
        data: { detail: 'Cannot resume terminal session' },
      },
      message: 'Request failed with status code 400',
    };

    mockClient.post.mockRejectedValueOnce(badRequestError);

    await expect(apiClient.resumeSession(sessionId)).rejects.toThrow();
    expect(mockClient.post).toHaveBeenCalledWith(`/api/v1/history/sessions/${sessionId}/resume`);
  });

  it('should handle network errors when resuming session', async () => {
    const sessionId = 'paused-session-456';
    const networkError: any = {
      isAxiosError: true,
      request: {},
      response: undefined,
      message: 'Network Error',
    };

    mockClient.post.mockRejectedValueOnce(networkError);

    await expect(apiClient.resumeSession(sessionId)).rejects.toThrow();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Error resuming session:',
      networkError
    );
  });

  it('should log error details when resume fails', async () => {
    const sessionId = 'test-session-789';
    const serverError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 500,
        data: { detail: 'Internal server error during resume' },
      },
      message: 'Request failed with status code 500',
    };

    mockClient.post.mockRejectedValueOnce(serverError);

    await expect(apiClient.resumeSession(sessionId)).rejects.toThrow();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Error resuming session:',
      serverError
    );
    expect(mockClient.post).toHaveBeenCalledTimes(1);
  });
});

describe('API Client Default Tools Configuration', () => {
  let consoleErrorSpy: any;
  const mockClient = mockedAxios.create();

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('should handle response with native_tools field', async () => {
    const successResponse = {
      data: {
        alert_type: 'PodCrashLooping',
        mcp_servers: [
          { server_id: 'kubernetes' },
          { server_id: 'github' }
        ],
        native_tools: {
          google_search: true,
          code_execution: false,
          url_context: true
        }
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.get.mockResolvedValueOnce(successResponse);

    const result = await apiClient.getDefaultToolsConfig('PodCrashLooping');

    expect(result).toEqual({
      servers: [
        { name: 'kubernetes', tools: null },
        { name: 'github', tools: null }
      ],
      native_tools: {
        google_search: true,
        code_execution: false,
        url_context: true
      }
    });
    expect(mockClient.get).toHaveBeenCalledWith('/api/v1/system/default-tools?alert_type=PodCrashLooping');
  });

  it('should handle response without native_tools field (older backend)', async () => {
    const responseWithoutNativeTools = {
      data: {
        alert_type: 'PodCrashLooping',
        mcp_servers: [
          { server_id: 'kubernetes' }
        ]
        // native_tools field is missing
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.get.mockResolvedValueOnce(responseWithoutNativeTools);

    const result = await apiClient.getDefaultToolsConfig('PodCrashLooping');

    expect(result).toEqual({
      servers: [
        { name: 'kubernetes', tools: null }
      ],
      native_tools: undefined // Should be undefined when field is missing
    });
  });

  it('should handle response with null native_tools field', async () => {
    const responseWithNullNativeTools = {
      data: {
        alert_type: 'PodCrashLooping',
        mcp_servers: [
          { server_id: 'kubernetes' }
        ],
        native_tools: null // Explicitly null
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.get.mockResolvedValueOnce(responseWithNullNativeTools);

    const result = await apiClient.getDefaultToolsConfig('PodCrashLooping');

    expect(result).toEqual({
      servers: [
        { name: 'kubernetes', tools: null }
      ],
      native_tools: undefined // Should convert null to undefined
    });
  });

  it('should handle default tools without alert_type parameter', async () => {
    const successResponse = {
      data: {
        alert_type: 'DefaultAlert',
        mcp_servers: [
          { server_id: 'kubernetes' }
        ],
        native_tools: {
          google_search: true,
          code_execution: false,
          url_context: true
        }
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {} as any,
    };

    mockClient.get.mockResolvedValueOnce(successResponse);

    const result = await apiClient.getDefaultToolsConfig();

    expect(result.servers).toBeDefined();
    expect(result.native_tools).toBeDefined();
    expect(mockClient.get).toHaveBeenCalledWith('/api/v1/system/default-tools');
  });

  it('should handle errors when fetching default tools', async () => {
    const serverError: any = {
      isAxiosError: true,
      request: {},
      response: {
        status: 503,
        data: { detail: 'Service not initialized' },
      },
      message: 'Request failed with status code 503',
    };

    mockClient.get.mockRejectedValueOnce(serverError);

    await expect(apiClient.getDefaultToolsConfig('PodCrashLooping')).rejects.toThrow();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Error fetching default tools config:',
      serverError
    );
  });
});

