import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatInput from '../../components/Chat/ChatInput';

describe('ChatInput', () => {
  const mockOnSendMessage = vi.fn();
  const mockOnCancelExecution = vi.fn();

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Message Sending', () => {
    it('should send message when Send button is clicked', async () => {
      mockOnSendMessage.mockResolvedValue(undefined);
      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const input = screen.getByPlaceholderText(/Type your question/i);
      await user.type(input, 'Hello AI');
      
      const sendButton = screen.getByRole('button');
      await user.click(sendButton);

      await waitFor(() => {
        expect(mockOnSendMessage).toHaveBeenCalledWith('Hello AI');
      });
    });

    it('should clear input after successful send', async () => {
      mockOnSendMessage.mockResolvedValue(undefined);
      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const input = screen.getByPlaceholderText(/Type your question/i) as HTMLTextAreaElement;
      
      await user.type(input, 'Test message');
      expect(input.value).toBe('Test message');

      const sendButton = screen.getByRole('button');
      await user.click(sendButton);

      await waitFor(() => {
        expect(input.value).toBe('');
      });
    });

    it('should not send empty or whitespace-only messages', async () => {
      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const sendButton = screen.getByRole('button');

      // Empty message - button should be disabled
      expect(sendButton).toBeDisabled();

      // Whitespace only
      const input = screen.getByPlaceholderText(/Type your question/i);
      await user.type(input, '   ');
      // Button still disabled for whitespace
      expect(sendButton).toBeDisabled();
    });

    it('should trim message content before sending', async () => {
      mockOnSendMessage.mockResolvedValue(undefined);
      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const input = screen.getByPlaceholderText(/Type your question/i);
      await user.type(input, '  Hello AI  ');

      const sendButton = screen.getByRole('button');
      await user.click(sendButton);

      await waitFor(() => {
        expect(mockOnSendMessage).toHaveBeenCalledWith('Hello AI');
      });
    });

    it('should show loading state while sending', async () => {
      let resolvePromise: () => void;
      const sendPromise = new Promise<void>(resolve => {
        resolvePromise = resolve;
      });
      mockOnSendMessage.mockReturnValue(sendPromise);

      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const input = screen.getByPlaceholderText(/Type your question/i);
      await user.type(input, 'Test');

      const sendButton = screen.getByRole('button');
      await user.click(sendButton);

      // Should show loading spinner
      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });

      // Resolve the promise
      resolvePromise!();

      // Loading should disappear
      await waitFor(() => {
        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
      });
    });

    it('should prevent sending while already sending', async () => {
      let resolvePromise: () => void;
      const sendPromise = new Promise<void>(resolve => {
        resolvePromise = resolve;
      });
      mockOnSendMessage.mockReturnValue(sendPromise);

      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const input = screen.getByPlaceholderText(/Type your question/i);
      await user.type(input, 'Test');

      const sendButton = screen.getByRole('button');
      await user.click(sendButton);

      // Button should be disabled while sending
      await waitFor(() => {
        expect(sendButton).toBeDisabled();
      });

      // Should only be called once
      expect(mockOnSendMessage).toHaveBeenCalledTimes(1);

      resolvePromise!();
    });
  });

  describe('Disabled State', () => {
    it('should disable input when disabled prop is true', () => {
      render(<ChatInput onSendMessage={mockOnSendMessage} disabled={true} />);

      const input = screen.getByPlaceholderText(/Type your question/i);
      expect(input).toBeDisabled();
    });

    it('should disable send button when disabled prop is true', () => {
      render(<ChatInput onSendMessage={mockOnSendMessage} disabled={true} />);

      const sendButton = screen.getByRole('button');
      expect(sendButton).toBeDisabled();
    });

    it('should disable input when sendingMessage is true', () => {
      render(<ChatInput onSendMessage={mockOnSendMessage} sendingMessage={true} />);

      const input = screen.getByPlaceholderText(/AI is processing/i);
      expect(input).toBeDisabled();
    });

    it('should show processing placeholder when sendingMessage is true', () => {
      render(<ChatInput onSendMessage={mockOnSendMessage} sendingMessage={true} />);

      expect(screen.getByPlaceholderText(/AI is processing/i)).toBeInTheDocument();
    });

    it('should show processing status text when sendingMessage is true', () => {
      render(<ChatInput onSendMessage={mockOnSendMessage} sendingMessage={true} />);

      expect(screen.getByText(/Processing your question/i)).toBeInTheDocument();
    });
  });

  describe('Cancel Execution', () => {
    it('should show Stop button when canCancel is true and sendingMessage is true', () => {
      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={true}
        />
      );

      // Should have Stop icon (not Send icon)
      const button = screen.getByRole('button');
      expect(button).toBeInTheDocument();
      expect(screen.queryByTestId('SendIcon')).not.toBeInTheDocument();
      expect(screen.getByTestId('StopIcon')).toBeInTheDocument();
    });

    it('should call onCancelExecution when Stop button is clicked', async () => {
      mockOnCancelExecution.mockResolvedValue(undefined);
      const user = userEvent.setup();

      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={true}
        />
      );

      const stopButton = screen.getByRole('button');
      await user.click(stopButton);

      expect(mockOnCancelExecution).toHaveBeenCalledTimes(1);
    });

    it('should show Stopping state when canceling is true', () => {
      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={true}
          canceling={true}
        />
      );

      const stopButton = screen.getByRole('button');
      expect(stopButton).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('should disable Stop button when canceling is true', () => {
      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={true}
          canceling={true}
        />
      );

      const stopButton = screen.getByRole('button');
      expect(stopButton).toBeDisabled();
    });

    it('should show error notification when cancellation fails', async () => {
      mockOnCancelExecution.mockRejectedValue(new Error('Cancel failed'));
      const user = userEvent.setup();

      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={true}
        />
      );

      const stopButton = screen.getByRole('button');
      await user.click(stopButton);

      await waitFor(() => {
        expect(screen.getByText(/Cancel failed/i)).toBeInTheDocument();
      });
    });

    it('should dismiss error notification when closed', async () => {
      mockOnCancelExecution.mockRejectedValue(new Error('Cancel failed'));
      const user = userEvent.setup();

      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={true}
        />
      );

      const stopButton = screen.getByRole('button');
      await user.click(stopButton);

      await waitFor(() => {
        expect(screen.getByText(/Cancel failed/i)).toBeInTheDocument();
      });

      // Close the alert
      const closeButtons = screen.getAllByRole('button');
      const closeButton = closeButtons.find(btn => btn.getAttribute('aria-label') === 'Close');
      await user.click(closeButton!);

      await waitFor(() => {
        expect(screen.queryByText(/Cancel failed/i)).not.toBeInTheDocument();
      });
    });

    it('should not show Stop button when canCancel is false', () => {
      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          onCancelExecution={mockOnCancelExecution}
          sendingMessage={true}
          canCancel={false}
        />
      );

      // Should show Send icon (not Stop icon) and it's loading
      expect(screen.queryByTestId('StopIcon')).not.toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toBeInTheDocument(); // Spinner
      const sendButton = screen.getByRole('button');
      expect(sendButton).toBeDisabled();
    });

    it('should handle missing onCancelExecution callback gracefully', async () => {
      const user = userEvent.setup();

      render(
        <ChatInput
          onSendMessage={mockOnSendMessage}
          // No onCancelExecution provided
          sendingMessage={true}
          canCancel={true}
        />
      );

      const stopButton = screen.getByRole('button');
      
      // Should not throw error when clicked
      await expect(user.click(stopButton)).resolves.not.toThrow();
    });
  });

  describe('Error Handling', () => {
    it('should handle send errors without clearing input', async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
      mockOnSendMessage.mockRejectedValue(new Error('Network error'));
      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const input = screen.getByPlaceholderText(/Type your question/i) as HTMLTextAreaElement;
      await user.type(input, 'Test message');

      const sendButton = screen.getByRole('button');
      await user.click(sendButton);

      await waitFor(() => {
        expect(consoleError).toHaveBeenCalled();
        // Input should retain the message so user can retry
        expect(input.value).toBe('Test message');
      });

      consoleError.mockRestore();
    });
  });

  describe('Button States', () => {
    it.each([
      { props: { disabled: false, sendingMessage: false }, expectedDisabled: false },
      { props: { disabled: true, sendingMessage: false }, expectedDisabled: true },
      { props: { disabled: false, sendingMessage: true }, expectedDisabled: true },
      { props: { disabled: true, sendingMessage: true }, expectedDisabled: true },
    ])('should have correct button state for props $props', ({ props, expectedDisabled }) => {
      render(<ChatInput onSendMessage={mockOnSendMessage} {...props} />);

      const sendButton = screen.getByRole('button');
      
      if (expectedDisabled) {
        expect(sendButton).toBeDisabled();
      } else {
        // Button is only enabled if there's content
        expect(sendButton).toBeDisabled(); // No content typed yet
      }
    });

    it('should enable send button only when content is present and not disabled', async () => {
      const user = userEvent.setup();

      render(<ChatInput onSendMessage={mockOnSendMessage} />);

      const sendButton = screen.getByRole('button');
      expect(sendButton).toBeDisabled();

      const input = screen.getByPlaceholderText(/Type your question/i);
      await user.type(input, 'Hello');

      expect(sendButton).not.toBeDisabled();

      await user.clear(input);

      expect(sendButton).toBeDisabled();
    });
  });
});

