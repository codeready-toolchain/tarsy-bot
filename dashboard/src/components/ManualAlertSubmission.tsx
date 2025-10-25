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
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  ArrowBack as ArrowBackIcon,
} from '@mui/icons-material';
import SharedHeader from './SharedHeader';
import VersionFooter from './VersionFooter';

import type { AlertSubmissionResponse } from '../types';
import ManualAlertForm from './ManualAlertForm';
import AlertProcessingStatus from './AlertProcessingStatus';
import { apiClient } from '../services/api';
import { MANUAL_ALERT_APP_STATE, type ManualAlertAppState } from '../utils/statusConstants';

type AppState = ManualAlertAppState;

function ManualAlertSubmission() {
  const [appState, setAppState] = useState<AppState>(MANUAL_ALERT_APP_STATE.FORM);
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
    setAppState(MANUAL_ALERT_APP_STATE.PROCESSING);
  };

  const handleProcessingComplete = () => {
    setAppState(MANUAL_ALERT_APP_STATE.COMPLETED);
  };

  const handleNewAlert = () => {
    setAppState(MANUAL_ALERT_APP_STATE.FORM);
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
      case MANUAL_ALERT_APP_STATE.FORM:
        return (
          <Fade in timeout={500}>
            <Box>
              <ManualAlertForm onAlertSubmitted={handleAlertSubmitted} />
            </Box>
          </Fade>
        );

      case MANUAL_ALERT_APP_STATE.PROCESSING:
        return (
          <Fade in timeout={500}>
            <Box>
              {currentAlert && (
                <AlertProcessingStatus
                  key={currentAlert.session_id}
                  sessionId={currentAlert.session_id}
                  onComplete={handleProcessingComplete}
                />
              )}
            </Box>
          </Fade>
        );

      case MANUAL_ALERT_APP_STATE.COMPLETED:
        return (
          <Fade in timeout={500}>
            <Box>
              {currentAlert && (
                <>
                  <AlertProcessingStatus
                    key={currentAlert.session_id}
                    sessionId={currentAlert.session_id}
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
    <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default', px: 2, py: 2 }}>
      <SharedHeader 
        title="Manual Alert Submission"
        showBackButton={true}
        backUrl="/"
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

        {/* Version footer */}
        <VersionFooter />
      </Container>
    </Box>
  );
}

export default ManualAlertSubmission;
