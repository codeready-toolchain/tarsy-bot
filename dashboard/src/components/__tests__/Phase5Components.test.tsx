import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CopyButton from '../CopyButton';
import ProgressIndicator from '../ProgressIndicator';

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn(),
  },
});

const theme = createTheme();

const renderWithTheme = (component: React.ReactElement) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('Phase 5 Components', () => {
  describe('CopyButton', () => {
    it('renders copy button with correct label', () => {
      renderWithTheme(
        <CopyButton text="test text" label="Copy Test" />
      );
      
      expect(screen.getByText('Copy Test')).toBeInTheDocument();
    });

    it('renders icon variant', () => {
      renderWithTheme(
        <CopyButton text="test text" variant="icon" />
      );
      
      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });

  describe('ProgressIndicator', () => {
    it('shows progress for in_progress status', () => {
      renderWithTheme(
        <ProgressIndicator 
          status="in_progress" 
          startedAt={Date.now() * 1000}
          showDuration={true}
        />
      );
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('shows duration for completed status', () => {
      renderWithTheme(
        <ProgressIndicator 
          status="completed" 
          duration={5000}
          showDuration={true}
        />
      );
      
      expect(screen.getByText('5s')).toBeInTheDocument();
    });

    it('does not render when duration is null and status is completed', () => {
      const { container } = renderWithTheme(
        <ProgressIndicator 
          status="completed" 
          duration={null}
          showDuration={true}
        />
      );
      
      expect(container.firstChild).toBeNull();
    });
  });
}); 