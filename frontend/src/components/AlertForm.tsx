/**
 * Alert submission form component
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  MenuItem,
  Button,
  Grid,
  Alert as MuiAlert,
  CircularProgress,
} from '@mui/material';
import { Send as SendIcon } from '@mui/icons-material';

import { Alert, AlertFormData, AlertResponse } from '../types';
import ApiService from '../services/api';

interface AlertFormProps {
  onAlertSubmitted: (alertResponse: AlertResponse) => void;
}

const AlertForm: React.FC<AlertFormProps> = ({ onAlertSubmitted }) => {
  const [formData, setFormData] = useState<AlertFormData>({
    alert: 'Namespace is stuck in Terminating',
    severity: 'warning',
    environment: 'production',
    cluster: 'https://api.okomk-7rbqf-kq6.9pbs.p3.openshiftapps.com:443',
    namespace: 'superman-dev',
    pod: '',
    message: 'namespace is stuck in \'Terminating\' phase',
    runbook: 'https://github.com/alexeykazakov/runbooks/blob/master/namespace-terminating.md'
  });

  const [availableAlertTypes, setAvailableAlertTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Load available alert types on component mount
  useEffect(() => {
    const loadAlertTypes = async () => {
      try {
        const alertTypes = await ApiService.getAlertTypes();
        setAvailableAlertTypes(alertTypes);
      } catch (error) {
        console.error('Failed to load alert types:', error);
        setError('Failed to load alert types from backend');
      }
    };

    loadAlertTypes();
  }, []);

  const handleInputChange = (field: keyof AlertFormData, value: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
    
    // Clear messages when user makes changes
    if (error) setError(null);
    if (success) setSuccess(null);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    // Validate required fields
    if (!formData.cluster || !formData.namespace) {
      setError('Cluster and Namespace are required fields');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      // Create alert object
      const alert: Alert = {
        alert: formData.alert,
        severity: formData.severity,
        environment: formData.environment,
        cluster: formData.cluster,
        namespace: formData.namespace,
        pod: formData.pod || undefined,
        message: formData.message,
        runbook: formData.runbook,
        timestamp: new Date().toISOString()
      };

      // Submit alert
      const response = await ApiService.submitAlert(alert);
      
      setSuccess(`Alert submitted successfully! ID: ${response.alert_id}`);
      onAlertSubmitted(response);

    } catch (error) {
      console.error('Error submitting alert:', error);
      setError('Failed to submit alert. Please check the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const severityOptions = [
    { value: 'warning', label: 'Warning' },
    { value: 'critical', label: 'Critical' },
    { value: 'info', label: 'Info' }
  ];

  const environmentOptions = [
    { value: 'production', label: 'Production' },
    { value: 'staging', label: 'Staging' },
    { value: 'development', label: 'Development' }
  ];

  return (
    <Card sx={{ maxWidth: 800, margin: '0 auto' }}>
      <CardContent>
        <Typography variant="h5" component="h2" gutterBottom>
          Submit Alert for Analysis
        </Typography>
        
        <Typography variant="body2" color="text.secondary" paragraph>
          Use this form to simulate an alert from your monitoring system. 
          The SRE AI Agent will process the alert, download the runbook, 
          gather system information, and provide detailed analysis.
        </Typography>

        {error && (
          <MuiAlert severity="error" sx={{ mb: 2 }}>
            {error}
          </MuiAlert>
        )}

        {success && (
          <MuiAlert severity="success" sx={{ mb: 2 }}>
            {success}
          </MuiAlert>
        )}

        <Box component="form" onSubmit={handleSubmit}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <TextField
                select
                fullWidth
                label="Alert Type"
                value={formData.alert}
                onChange={(e) => handleInputChange('alert', e.target.value)}
                required
              >
                {availableAlertTypes.map((alertType) => (
                  <MenuItem key={alertType} value={alertType}>
                    {alertType}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                select
                fullWidth
                label="Severity"
                value={formData.severity}
                onChange={(e) => handleInputChange('severity', e.target.value)}
                required
              >
                {severityOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                select
                fullWidth
                label="Environment"
                value={formData.environment}
                onChange={(e) => handleInputChange('environment', e.target.value)}
                required
              >
                {environmentOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Cluster URL"
                value={formData.cluster}
                onChange={(e) => handleInputChange('cluster', e.target.value)}
                placeholder="https://api.cluster.example.com:6443"
                required
              />
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Namespace"
                value={formData.namespace}
                onChange={(e) => handleInputChange('namespace', e.target.value)}
                placeholder="my-namespace"
                required
              />
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Pod (Optional)"
                value={formData.pod}
                onChange={(e) => handleInputChange('pod', e.target.value)}
                placeholder="my-pod-123"
              />
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                rows={3}
                label="Alert Message"
                value={formData.message}
                onChange={(e) => handleInputChange('message', e.target.value)}
                required
              />
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Runbook URL"
                value={formData.runbook}
                onChange={(e) => handleInputChange('runbook', e.target.value)}
                placeholder="https://github.com/org/repo/blob/master/runbooks/alert.md"
                required
              />
            </Grid>

            <Grid item xs={12}>
              <Button
                type="submit"
                variant="contained"
                size="large"
                startIcon={loading ? <CircularProgress size={20} /> : <SendIcon />}
                disabled={loading}
                fullWidth
              >
                {loading ? 'Submitting Alert...' : 'Submit Alert'}
              </Button>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
  );
};

export default AlertForm; 