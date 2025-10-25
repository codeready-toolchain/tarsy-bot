/**
 * Tests for AlertProcessingStatus component - Session Existence Polling
 * 
 * Tests the critical logic for checking if a session exists in the database
 * before enabling the "View Full Details" button to prevent 404 errors.
 * 
 * Tests cover:
 * - Recursive setTimeout polling with exponential backoff
 * - 404 error handling (stop polling immediately)
 * - Other errors (retry with backoff)
 * - Timeout behavior (keep button disabled, show error)
 * - Proper cleanup on unmount
 * 
 * Note: These tests focus on the most important scenarios rather than exhaustive
 * coverage, following the project's test philosophy of quality over quantity.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import AlertProcessingStatus from '../../components/AlertProcessingStatus';

// Mock the API client
vi.mock('../../services/api', () => ({
  apiClient: {
    getSessionDetail: vi.fn(),
  },
}));

// Mock the WebSocket service
vi.mock('../../services/websocketService', () => ({
  websocketService: {
    subscribeToChannel: vi.fn(() => vi.fn()), // Returns unsubscribe function
    onConnectionChange: vi.fn(() => vi.fn()), // Returns unsubscribe function
    isConnected: true,
    connect: vi.fn().mockResolvedValue(undefined),
  },
}));

// Mock ReactMarkdown to avoid unnecessary complexity in tests
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
  defaultUrlTransform: (url: string) => url,
}));

// Import after mocking
import { apiClient } from '../../services/api';

const theme = createTheme();

const renderWithTheme = (component: React.ReactElement) => {
  return render(<ThemeProvider theme={theme}>{component}</ThemeProvider>);
};

describe('AlertProcessingStatus - Session Existence Polling', () => {
  const mockSessionId = 'test-session-123';
  const mockOnComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it('should call API to check session existence on mount', async () => {
    // Mock API to return session immediately
    vi.mocked(apiClient.getSessionDetail).mockResolvedValueOnce({
      session_id: mockSessionId,
      status: 'in_progress',
      alert_data: {},
      stages: [],
    } as any);

    renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    // Should call API to check if session exists
    await waitFor(() => {
      expect(apiClient.getSessionDetail).toHaveBeenCalledWith(mockSessionId);
    }, { timeout: 10000 });

    // Should eventually show the "View Full Details" button
    await waitFor(() => {
      expect(screen.getByText('View Full Details')).toBeInTheDocument();
    }, { timeout: 10000 });
  });

  it('should show loading state while session is being verified', async () => {
    // Mock API to delay response
    vi.mocked(apiClient.getSessionDetail).mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                session_id: mockSessionId,
                status: 'in_progress',
                alert_data: {},
                stages: [],
              } as any),
            100
          )
        )
    );

    renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    // Should show the "Initializing session..." loading state initially
    const loadingText = await screen.findByText('Initializing session...', {}, { timeout: 2000 });
    expect(loadingText).toBeInTheDocument();
  });

  it('should retry polling with exponential backoff if initial session check fails with non-404 error', async () => {
    // Mock API to fail once with a 500 error, then succeed
    let callCount = 0;
    vi.mocked(apiClient.getSessionDetail).mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        // First call fails (500 - server error, not 404)
        return Promise.reject({ response: { status: 500 } });
      }
      // Second call succeeds
      return Promise.resolve({
        session_id: mockSessionId,
        status: 'in_progress',
        alert_data: {},
        stages: [],
      } as any);
    });

    renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    // Should eventually call API multiple times due to polling with backoff
    await waitFor(
      () => {
        expect(apiClient.getSessionDetail).toHaveBeenCalledTimes(2);
      },
      { timeout: 10000 }
    );

    // Should eventually show button after retry succeeds
    await waitFor(
      () => {
        expect(screen.getByText('View Full Details')).toBeInTheDocument();
      },
      { timeout: 10000 }
    );
  });

  it('should log success message when session is confirmed', async () => {
    const consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    vi.mocked(apiClient.getSessionDetail).mockResolvedValueOnce({
      session_id: mockSessionId,
      status: 'in_progress',
      alert_data: {},
      stages: [],
    } as any);

    renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    await waitFor(
      () => {
        expect(consoleLogSpy).toHaveBeenCalledWith(
          expect.stringContaining(`✅ Session ${mockSessionId} confirmed to exist in database`)
        );
      },
      { timeout: 10000 }
    );

    consoleLogSpy.mockRestore();
  });

  it('should stop polling immediately on 404 error and show error message', async () => {
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    // Mock API to always return 404
    vi.mocked(apiClient.getSessionDetail).mockRejectedValue({
      response: { status: 404 }
    });

    renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    // Should call API once and stop
    await waitFor(
      () => {
        expect(apiClient.getSessionDetail).toHaveBeenCalledTimes(1);
      },
      { timeout: 3000 }
    );

    // Should show error message instead of button
    await waitFor(
      () => {
        expect(screen.getByText(/Session not found/i)).toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // Wait a bit to ensure no more calls are made
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Should still only have been called once (no retries for 404)
    expect(apiClient.getSessionDetail).toHaveBeenCalledTimes(1);

    // Should NOT show the "View Full Details" button (error message shown instead)
    const button = screen.queryByRole('button', { name: /View Full Details/i });
    expect(button).not.toBeInTheDocument();

    // Should log warning
    expect(consoleWarnSpy).toHaveBeenCalledWith(
      expect.stringContaining(`❌ Session ${mockSessionId} not found (404)`)
    );

    consoleWarnSpy.mockRestore();
  }, 10000);

  it('should implement exponential backoff for non-404 errors', async () => {
    const consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    
    // Mock API to always fail with a 500 error (non-404)
    // Track call count
    let callCount = 0;
    const callTimes: number[] = [];
    vi.mocked(apiClient.getSessionDetail).mockImplementation(() => {
      callCount++;
      callTimes.push(Date.now());
      // Always reject to trigger retries with backoff
      return Promise.reject({ response: { status: 500 } });
    });

    renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    // Wait for at least 3 calls to verify backoff is happening
    await waitFor(
      () => {
        expect(apiClient.getSessionDetail).toHaveBeenCalledTimes(3);
      },
      { timeout: 10000 }
    );

    // Verify console logs show increasing retry delays
    expect(consoleLogSpy).toHaveBeenCalledWith(
      expect.stringContaining('retrying in 2000ms')
    );
    expect(consoleLogSpy).toHaveBeenCalledWith(
      expect.stringContaining('retrying in 4000ms')
    );

    // Verify calls are spaced out (not immediate retries)
    // Between call 1 and 2: ~2000ms, between call 2 and 3: ~4000ms
    if (callTimes.length >= 3) {
      const delay1 = callTimes[1] - callTimes[0];
      const delay2 = callTimes[2] - callTimes[1];
      
      // Allow some margin for test timing variance
      expect(delay1).toBeGreaterThan(1800);
      expect(delay2).toBeGreaterThan(3800);
      expect(delay2).toBeGreaterThan(delay1); // Second delay should be longer
    }

    consoleLogSpy.mockRestore();
  }, 15000);

  it('should cleanup pending timeout on unmount', async () => {
    // Mock API to fail to keep polling active
    vi.mocked(apiClient.getSessionDetail).mockRejectedValue({
      response: { status: 500 }
    });

    const { unmount } = renderWithTheme(
      <AlertProcessingStatus sessionId={mockSessionId} onComplete={mockOnComplete} />
    );

    // Wait for initial call
    await waitFor(() => {
      expect(apiClient.getSessionDetail).toHaveBeenCalled();
    }, { timeout: 3000 });

    // Unmount the component immediately
    unmount();

    const callCountAtUnmount = vi.mocked(apiClient.getSessionDetail).mock.calls.length;

    // Wait for a period longer than the backoff delay
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Should not have made additional calls after unmount
    // (may have made 1-2 calls before unmount, but no more after)
    expect(vi.mocked(apiClient.getSessionDetail).mock.calls.length).toBe(callCountAtUnmount);
  }, 10000);
});

