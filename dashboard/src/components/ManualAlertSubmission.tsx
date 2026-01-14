/**
 * Manual Alert Submission page component - EP-0018
 * Integrated from alert-dev-ui into the main dashboard
 * 
 * Form navigates directly to session detail page on submission
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Alert,
  Fade,
} from '@mui/material';
import SharedHeader from './SharedHeader';
import VersionFooter from './VersionFooter';

import ManualAlertForm from './ManualAlertForm';
import { apiClient } from '../services/api';

function ManualAlertSubmission() {
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'healthy' | 'error'>('unknown');

  // Check backend health on component mount
  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        await apiClient.healthCheck();
        setBackendStatus('healthy');
      } catch (error) {
        setBackendStatus('error');
        console.error('Backend health check failed:', error);
      }
    };

    checkBackendHealth();
  }, []);

  return (
    <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default', px: 2, py: 2 }}>
      <SharedHeader 
        title="Manual Alert Submission"
        showBackButton={true}
      >
        <Typography variant="body2" sx={{ opacity: 0.8, color: 'white', mr: 2 }}>
          Automated Incident Response
        </Typography>
      </SharedHeader>

      <Container maxWidth={false} sx={{ py: 4, px: { xs: 1, sm: 2 } }}>
        {/* Backend status indicator */}
        {backendStatus === 'error' && (
          <Alert severity="error" sx={{ mb: 3 }}>
            <Typography variant="body2">
              <strong>Backend Unavailable:</strong> The TARSy backend is not responding. 
              Please ensure the backend server is running on port 8000.
            </Typography>
          </Alert>
        )}

        {backendStatus === 'healthy' && (
          <Alert severity="success" sx={{ mb: 3 }}>
            <Typography variant="body2">
              🚀 Tarsy is ready! Submit an alert to see automated incident analysis in action.
            </Typography>
          </Alert>
        )}

        {/* Main content - Form navigates directly to session detail on submission */}
        <Fade in timeout={500}>
          <Box>
            <ManualAlertForm />
          </Box>
        </Fade>

        {/* Version footer */}
        <VersionFooter />
      </Container>
    </Box>
  );
}

export default ManualAlertSubmission;
