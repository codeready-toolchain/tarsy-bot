import type { ReactElement } from 'react';
import { Alert, Button, Box } from '@mui/material';
import { Refresh as RefreshIcon } from '@mui/icons-material';

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
      }}
    >
      <Alert
        severity="warning"
        action={
          <Button
            color="inherit"
            size="small"
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
          '& .MuiAlert-message': {
            display: 'flex',
            alignItems: 'center',
            width: '100%',
          },
        }}
      >
        <strong>New dashboard version available.</strong> Refresh to update and get the latest features and fixes.
      </Alert>
    </Box>
  );
}

export default VersionUpdateBanner;

