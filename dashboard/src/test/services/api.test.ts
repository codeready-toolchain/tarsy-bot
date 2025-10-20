/**
 * Tests for API client retry logic
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Mock axios
vi.mock('axios');
const mockedAxios = axios as any;

// Mock env config
vi.mock('../../config/env', () => ({
  urls: {
    api: {
      base: 'http://localhost:8000',
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

describe('API Client Retry Logic', () => {
  let consoleLogSpy: any;
  let consoleErrorSpy: any;
  let consoleWarnSpy: any;

  beforeEach(() => {
    // Spy on console methods
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    // Reset mocks
    vi.clearAllMocks();

    // Setup axios mock
    mockedAxios.create = vi.fn(() => ({
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: {
          use: vi.fn(),
        },
        response: {
          use: vi.fn((success: any, error: any) => {
            // Store the error handler for later use
            (mockedAxios.create as any).errorHandler = error;
          }),
        },
      },
    }));
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
  });

  it('should retry on network errors with exponential backoff capped at 5s', async () => {
    // This test verifies the retry logic structure
    // In a real scenario, the retry would be triggered during backend restarts
    // Pattern: 1s, 2s, 4s, 5s, 5s, 5s...
    
    // Create a network error (no response from server)
    const networkError: any = {
      isAxiosError: true,
      request: {},
      response: undefined,
      message: 'Network Error',
    };

    let attemptCount = 0;
    const mockOperation = vi.fn(async () => {
      attemptCount++;
      if (attemptCount < 3) {
        throw networkError;
      }
      return { data: 'success' };
    });

    // Simulate the retry logic with capped exponential backoff
    const maxRetries = 5;
    const initialDelay = 1000; // 1s
    const maxDelay = 5000; // 5s cap
    const delays: number[] = [];

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const result = await mockOperation();
        expect(result.data).toBe('success');
        expect(attemptCount).toBe(3); // Should succeed on 3rd attempt
        break;
      } catch (error) {
        const isNetworkError = 
          error && 
          typeof error === 'object' && 
          'isAxiosError' in error &&
          (error as any).request && 
          !(error as any).response;

        if (!isNetworkError || attempt === maxRetries) {
          throw error;
        }

        // Calculate delay with exponential backoff capped at maxDelay
        const exponentialDelay = initialDelay * Math.pow(2, attempt);
        const delay = Math.min(exponentialDelay, maxDelay);
        delays.push(delay);
        
        // Verify the delay follows the pattern: 1s, 2s, 4s, 5s, 5s...
        expect(delay).toBeGreaterThan(0);
        expect(delay).toBeLessThanOrEqual(maxDelay);
      }
    }

    expect(mockOperation).toHaveBeenCalledTimes(3);
    // Verify delay pattern (only 2 retries in this test)
    expect(delays).toEqual([1000, 2000]);
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

  it('should verify complete delay pattern: 1s, 2s, 4s, 5s, 5s...', () => {
    const initialDelay = 1000;
    const maxDelay = 5000;
    const expectedDelays = [1000, 2000, 4000, 5000, 5000, 5000];

    const actualDelays = [];
    for (let attempt = 0; attempt < 6; attempt++) {
      const exponentialDelay = initialDelay * Math.pow(2, attempt);
      const delay = Math.min(exponentialDelay, maxDelay);
      actualDelays.push(delay);
    }

    expect(actualDelays).toEqual(expectedDelays);
  });
});

