import type { ReactElement } from 'react';
import { Alert, Button, Box, keyframes, useMediaQuery } from '@mui/material';
import { Refresh as RefreshIcon, Warning as WarningIcon } from '@mui/icons-material';

/**
 * Pulse animation for banner (defined at module scope to avoid recreation)
 * Subtle breathing effect to draw attention without being distracting
 */
const pulseAnimation = keyframes`
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.85;
  }
  100% {
    opacity: 1;
  }
`;

/**
 * Props for VersionUpdateBanner component
 */
interface VersionUpdateBannerProps {
  /**
   * Whether to show the banner (dashboard version has changed)
   */
  show: boolean;
}

/**
 * VersionUpdateBanner component
 * 
 * Displays a persistent warning banner at the top of the page when a new dashboard
 * version is available. The banner cannot be dismissed - user must refresh to update.
 * 
 * Design:
 * - Warning severity (yellow/orange styling)
 * - Fixed at top of page
 * - Persistent (no dismiss button)
 * - Clear call-to-action to refresh
 * 
 * @param props - Component props
 * @returns Banner component or null if not shown
 */
function VersionUpdateBanner({ show }: VersionUpdateBannerProps): ReactElement | null {
  // Respect user's motion preferences for accessibility
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  
  if (!show) {
    return null;
  }
  
  /**
   * Handle refresh button click
   * Reloads the entire page to get new JS bundles
   */
  const handleRefresh = (): void => {
    window.location.reload();
  };
  
  return (
    <Box
      sx={{
        position: 'sticky',
        top: 0,
        zIndex: 9999,
        width: '100%',
        // Apply pulse animation only if user hasn't requested reduced motion
        animation: prefersReducedMotion ? 'none' : `${pulseAnimation} 2s ease-in-out infinite`,
      }}
    >
      <Alert
        severity="warning"
        icon={<WarningIcon sx={{ fontSize: 28 }} />}
        action={
          <Button
            variant="contained"
            color="warning"
            size="medium"
            startIcon={<RefreshIcon />}
            onClick={handleRefresh}
            sx={{
              fontWeight: 'bold',
            }}
          >
            Refresh Now
          </Button>
        }
        sx={{
          borderRadius: 0,
          fontSize: '1.15rem',
          py: 2.5,
          px: 3,
          '& .MuiAlert-message': {
            display: 'flex',
            alignItems: 'center',
            width: '100%',
            fontSize: '1.15rem',
          },
          '& .MuiAlert-action': {
            alignItems: 'center',
            pt: 0,
          },
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Box sx={{ fontWeight: 'bold', fontSize: '1.3rem' }}>
            New Dashboard Version Available!
          </Box>
          <Box sx={{ fontSize: '1.05rem' }}>
            Refresh now to get the latest updates.
          </Box>
        </Box>
      </Alert>
    </Box>
  );
}

export default VersionUpdateBanner;

