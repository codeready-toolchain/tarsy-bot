import { useEffect, useState } from 'react';
import { Alert, AlertTitle, Box, Collapse, IconButton } from '@mui/material';
import { ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import type { SystemWarning, SystemWarningBannerProps } from '../types';
import { apiClient } from '../services/api';

/**
 * SystemWarningBanner displays system-level warnings at the top of the dashboard.
 * 
 * Warnings include non-fatal errors like:
 * - MCP server initialization failures
 * - Missing GitHub token (using default runbook)
 * - Other configuration issues
 * 
 * Polls the backend API every 10 seconds (configurable) to fetch updated warnings.
 */
export const SystemWarningBanner: React.FC<SystemWarningBannerProps> = ({ 
  pollInterval = 10000 
}) => {
  const [warnings, setWarnings] = useState<SystemWarning[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    // Fetch warnings on mount
    const fetchWarnings = async () => {
      try {
        const data = await apiClient.getSystemWarnings();
        setWarnings(data);
      } catch (error) {
        console.error('Failed to fetch system warnings:', error);
        // Don't show error to user - warnings are non-critical
      }
    };

    fetchWarnings();
    
    // Poll for updates at specified interval
    const interval = setInterval(fetchWarnings, pollInterval);
    
    return () => clearInterval(interval);
  }, [pollInterval]);

  // Don't render anything if there are no warnings
  if (warnings.length === 0) {
    return null;
  }

  const handleToggleExpand = (warningId: string) => {
    setExpandedId(expandedId === warningId ? null : warningId);
  };

  return (
    <Box sx={{ mb: 2 }}>
      {warnings.map((warning) => (
        <Alert 
          key={warning.warning_id}
          severity="warning"
          sx={{ mb: 1 }}
          action={
            warning.details ? (
              <IconButton
                size="small"
                onClick={() => handleToggleExpand(warning.warning_id)}
                aria-label={expandedId === warning.warning_id ? "Collapse details" : "Expand details"}
              >
                <ExpandMoreIcon 
                  sx={{ 
                    transform: expandedId === warning.warning_id ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.3s'
                  }} 
                />
              </IconButton>
            ) : undefined
          }
        >
          <AlertTitle>System Warning</AlertTitle>
          {warning.message}
          {warning.details && (
            <Collapse in={expandedId === warning.warning_id}>
              <Box sx={{ mt: 1, fontSize: '0.875rem', opacity: 0.9 }}>
                {warning.details}
              </Box>
            </Collapse>
          )}
        </Alert>
      ))}
    </Box>
  );
};

