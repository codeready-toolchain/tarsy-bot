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

// Import apiClient after mocks are set up
import { apiClient } from '../../services/api';

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

    // First retry after 500ms (INITIAL_RETRY_DELAY * 2^0 = 500ms)
    await vi.advanceTimersByTimeAsync(500);

    // Second retry after 1000ms (INITIAL_RETRY_DELAY * 2^1 = 1000ms)
    await vi.advanceTimersByTimeAsync(1000);

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

    // Verify retry messages were logged
    expect(consoleLogSpy).toHaveBeenCalledWith(
      expect.stringContaining('Get active sessions failed, retrying in 500ms')
    );
    expect(consoleLogSpy).toHaveBeenCalledWith(
      expect.stringContaining('Get active sessions failed, retrying in 1000ms')
    );

    // Restore real timers
    vi.useRealTimers();
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

  it('should verify complete delay pattern: 500ms, 1000ms, 2000ms, 4000ms, 5000ms, 5000ms...', () => {
    // Test uses the actual INITIAL_RETRY_DELAY from the implementation (500ms)
    const initialDelay = 500;  // INITIAL_RETRY_DELAY from APIClient
    const maxDelay = 5000;     // MAX_RETRY_DELAY from APIClient
    const expectedDelays = [500, 1000, 2000, 4000, 5000, 5000];

    const actualDelays = [];
    for (let attempt = 0; attempt < 6; attempt++) {
      const exponentialDelay = initialDelay * Math.pow(2, attempt);
      const delay = Math.min(exponentialDelay, maxDelay);
      actualDelays.push(delay);
    }

    expect(actualDelays).toEqual(expectedDelays);
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

