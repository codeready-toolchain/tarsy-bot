import { useState, useEffect } from 'react';
import { Box, Typography, Tooltip } from '@mui/material';
import { DASHBOARD_VERSION } from '../config/env';
import { apiClient } from '../services/api';

/**
 * VersionFooter component
 * Displays version information in the footer
 * - Shows single "Version: xxx" if dashboard and agent versions match
 * - Shows separate "Dashboard version: xxx" and "Agent version: yyy" if they differ
 */
function VersionFooter() {
  const [agentVersion, setAgentVersion] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<string>('checking');
  
  useEffect(() => {
    // Fetch backend version from health endpoint
    const fetchBackendVersion = async () => {
      try {
        const health: { status: string; version?: string; [key: string]: any } = await apiClient.healthCheck();
        const version = health.version || 'unknown';
        setAgentVersion(version);
        setBackendStatus(health.status || 'unknown');
      } catch (error) {
        console.error('Failed to fetch backend version:', error);
        setAgentVersion('unavailable');
        setBackendStatus('error');
      }
    };
    
    fetchBackendVersion();
  }, []);
  
  // Determine what to display
  const showSingleVersion = agentVersion && agentVersion === DASHBOARD_VERSION;
  const showSeparateVersions = agentVersion && agentVersion !== DASHBOARD_VERSION && agentVersion !== 'unavailable';
  
  return (
    <Box
      component="footer"
      sx={{
        mt: 4,
        mb: 2,
        py: 2,
        textAlign: 'center',
        borderTop: '1px solid',
        borderColor: 'divider',
      }}
    >
      {showSingleVersion && (
        <Tooltip title={`Agent status: ${backendStatus}`} arrow>
          <Typography variant="body2" color="text.secondary" sx={{ cursor: 'help' }}>
            TARSy - Powered by AI • Version: {DASHBOARD_VERSION}
          </Typography>
        </Tooltip>
      )}
      
      {showSeparateVersions && (
        <Tooltip title={`Agent status: ${backendStatus}`} arrow>
          <Typography variant="body2" color="text.secondary" sx={{ cursor: 'help' }}>
            TARSy - Powered by AI • Dashboard: {DASHBOARD_VERSION} • Agent: {agentVersion}
          </Typography>
        </Tooltip>
      )}
      
      {!agentVersion && backendStatus === 'checking' && (
        <Typography variant="body2" color="text.secondary">
          TARSy - Powered by AI • Loading version info...
        </Typography>
      )}
      
      {agentVersion === 'unavailable' && (
        <Typography variant="body2" color="text.secondary">
          TARSy - Powered by AI • Dashboard: {DASHBOARD_VERSION} • Agent: unavailable
        </Typography>
      )}
    </Box>
  );
}

export default VersionFooter;

