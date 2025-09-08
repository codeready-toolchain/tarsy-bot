/**
 * Manual Alert Submission page component - EP-0018
 * Integrated from alert-dev-ui into the main dashboard
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Alert,
  Button,
  Fade,
  AppBar,
  Toolbar,
} from '@mui/material';
import {
  Psychology as BrainIcon,
  Refresh as RefreshIcon,
  ArrowBack as ArrowBackIcon,
} from '@mui/icons-material';

import type { AlertSubmissionResponse } from '../types';
import ManualAlertForm from './ManualAlertForm';
import AlertProcessingStatus from './AlertProcessingStatus';
import { apiClient } from '../services/api';

type AppState = 'form' | 'processing' | 'completed';

function ManualAlertSubmission() {
  const [appState, setAppState] = useState<AppState>('form');
  const [currentAlert, setCurrentAlert] = useState<AlertSubmissionResponse | null>(null);
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

  const handleAlertSubmitted = (alertResponse: AlertSubmissionResponse) => {
    setCurrentAlert(alertResponse);
    setAppState('processing');
  };

  const handleProcessingComplete = () => {
    setAppState('completed');
  };

  const handleNewAlert = () => {
    setAppState('form');
    setCurrentAlert(null);
  };

  const handleBack = () => {
    // Since this opens in a new tab, we can just close the window or go back
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.close();
    }
  };

  const renderContent = () => {
    switch (appState) {
      case 'form':
        return (
          <Fade in timeout={500}>
            <Box>
              <ManualAlertForm onAlertSubmitted={handleAlertSubmitted} />
            </Box>
          </Fade>
        );

      case 'processing':
        return (
          <Fade in timeout={500}>
            <Box>
              {currentAlert && (
                <AlertProcessingStatus
                  alertId={currentAlert.alert_id}
                  onComplete={handleProcessingComplete}
                />
              )}
            </Box>
          </Fade>
        );

      case 'completed':
        return (
          <Fade in timeout={500}>
            <Box>
              {currentAlert && (
                <>
                  <AlertProcessingStatus
                    alertId={currentAlert.alert_id}
                    onComplete={handleProcessingComplete}
                  />
                  <Box mt={3} display="flex" justifyContent="center" gap={2}>
                    <Button
                      variant="outlined"
                      startIcon={<RefreshIcon />}
                      onClick={handleNewAlert}
                      size="large"
                    >
                      Submit Another Alert
                    </Button>
                    <Button
                      variant="text"
                      startIcon={<ArrowBackIcon />}
                      onClick={handleBack}
                      size="large"
                    >
                      Back to Dashboard
                    </Button>
                  </Box>
                </>
              )}
            </Box>
          </Fade>
        );

      default:
        return null;
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default' }}>
      <AppBar position="static" elevation={1}>
        <Toolbar>
          <BrainIcon sx={{ mr: 2 }} />
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Tarsy-bot - Manual Alert Submission
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.8 }}>
            Automated Incident Response
          </Typography>
        </Toolbar>
      </AppBar>

      <Container maxWidth={false} sx={{ py: 4, px: { xs: 1, sm: 2 } }}>
        {/* Backend status indicator */}
        {backendStatus === 'error' && (
          <Alert severity="error" sx={{ mb: 3 }}>
            <Typography variant="body2">
              <strong>Backend Unavailable:</strong> The Tarsy-bot backend is not responding. 
              Please ensure the backend server is running on port 8000.
            </Typography>
          </Alert>
        )}

        {backendStatus === 'healthy' && appState === 'form' && (
          <Alert severity="success" sx={{ mb: 3 }}>
            <Typography variant="body2">
              🚀 Tarsy is ready! Submit an alert to see automated incident analysis in action.
            </Typography>
          </Alert>
        )}

        {/* Main content */}
        <Box>
          {renderContent()}
        </Box>

        {/* Footer */}
        <Box mt={6} textAlign="center">
          <Typography variant="body2" color="text.secondary">
            Tarsy-bot v1.0 - Powered by AI and MCP Servers
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" mt={1}>
            Submit alerts to get automated runbook analysis and system diagnostics
          </Typography>
        </Box>
      </Container>
    </Box>
  );
}

export default ManualAlertSubmission;
