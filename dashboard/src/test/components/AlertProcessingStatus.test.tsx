/**
 * Tests for AlertProcessingStatus component - Session Existence Polling
 * 
 * Tests the critical logic for checking if a session exists in the database
 * before enabling the "View Full Details" button to prevent 404 errors.
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

  it('should retry polling if initial session check fails', async () => {
    // Mock API to fail once, then succeed
    let callCount = 0;
    vi.mocked(apiClient.getSessionDetail).mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        // First call fails (404)
        return Promise.reject({ response: { status: 404 } });
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

    // Should eventually call API multiple times due to polling
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
});

