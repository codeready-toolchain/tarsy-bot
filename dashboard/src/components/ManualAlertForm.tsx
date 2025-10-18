/**
 * Manual Alert submission form component - EP-0018
 * Redesigned with dual-mode input: Key-Value pairs or Free-Text parsing
 * Supports runbook dropdown with GitHub repository integration
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  MenuItem,
  Button,
  Stack,
  Alert as MuiAlert,
  CircularProgress,
  IconButton,
  Divider,
  Autocomplete,
  Tabs,
  Tab,
  Paper,
} from '@mui/material';
import { 
  Send as SendIcon, 
  Add as AddIcon, 
  Close as CloseIcon 
} from '@mui/icons-material';

import type { KeyValuePair, ManualAlertFormProps } from '../types';
import { apiClient } from '../services/api';

/**
 * Generate a unique ID for key-value pairs
 */
const generateId = () => Math.random().toString(36).substr(2, 9);

/**
 * Default runbook option constant
 */
const DEFAULT_RUNBOOK = 'Default Runbook';

/**
 * Parse free-text input into key-value pairs
 * Attempts to parse "Key: Value" or "Key=Value" patterns line by line
 */
const parseFreeText = (text: string): { success: boolean; data: Record<string, any> } => {
  const lines = text.split('\n');
  const data: Record<string, any> = {};
  let successCount = 0;

  for (const line of lines) {
    const trimmedLine = line.trim();
    if (!trimmedLine) continue;

    // Try parsing "Key: Value" format
    const colonMatch = trimmedLine.match(/^([^:]+):\s*(.*)$/);
    if (colonMatch) {
      const key = colonMatch[1].trim();
      const value = colonMatch[2].trim();
      if (key) {
        data[key] = value;
        successCount++;
        continue;
      }
    }

    // Try parsing "Key=Value" format
    const equalsMatch = trimmedLine.match(/^([^=]+)=(.*)$/);
    if (equalsMatch) {
      const key = equalsMatch[1].trim();
      const value = equalsMatch[2].trim();
      if (key) {
        data[key] = value;
        successCount++;
        continue;
      }
    }
  }

  // Consider parsing successful if we extracted at least one key-value pair
  return {
    success: successCount > 0,
    data: successCount > 0 ? data : { message: text }
  };
};

const ManualAlertForm: React.FC<ManualAlertFormProps> = ({ onAlertSubmitted }) => {
  // Common fields
  const [alertType, setAlertType] = useState('');
  const [runbook, setRunbook] = useState<string | null>(DEFAULT_RUNBOOK);
  
  // Mode selection (0 = Key-Value, 1 = Free-Text)
  const [mode, setMode] = useState(0);
  
  // Mode A: Key-value pairs
  const [keyValuePairs, setKeyValuePairs] = useState<KeyValuePair[]>([
    { id: generateId(), key: 'cluster', value: '' },
    { id: generateId(), key: 'namespace', value: '' },
    { id: generateId(), key: 'message', value: '' }
  ]);

  // Mode B: Free text
  const [freeText, setFreeText] = useState('');

  // Available options
  const [availableAlertTypes, setAvailableAlertTypes] = useState<string[]>([]);
  const [availableRunbooks, setAvailableRunbooks] = useState<string[]>([]);
  
  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Load available alert types and runbooks on component mount
  useEffect(() => {
    const loadOptions = async () => {
      try {
        // Load alert types
        const alertTypes = await apiClient.getAlertTypes();
        if (Array.isArray(alertTypes)) {
          setAvailableAlertTypes(alertTypes);
          // Set default alertType to 'kubernetes' if available, otherwise first available type
          if (alertTypes.includes('kubernetes')) {
            setAlertType('kubernetes');
          } else if (alertTypes.length > 0) {
            setAlertType(alertTypes[0]);
          }
        }

        // Load runbooks
        const runbooks = await apiClient.getRunbooks();
        if (Array.isArray(runbooks)) {
          // Add "Default Runbook" as first option
          setAvailableRunbooks([DEFAULT_RUNBOOK, ...runbooks]);
        } else {
          setAvailableRunbooks([DEFAULT_RUNBOOK]);
        }
      } catch (error) {
        console.error('Failed to load options:', error);
        setError('Failed to load options from backend. Please check if the backend is running.');
      }
    };

    loadOptions();
  }, []);

  /**
   * Add a new empty key-value pair
   */
  const addKeyValuePair = () => {
    setKeyValuePairs(prev => [
      ...prev,
      { id: generateId(), key: '', value: '' }
    ]);
  };

  /**
   * Remove a key-value pair by ID
   */
  const removeKeyValuePair = (id: string) => {
    setKeyValuePairs(prev => prev.filter(pair => pair.id !== id));
  };

  /**
   * Update a key-value pair
   */
  const updateKeyValuePair = (id: string, field: 'key' | 'value', newValue: string) => {
    setKeyValuePairs(prev =>
      prev.map(pair =>
        pair.id === id ? { ...pair, [field]: newValue } : pair
      )
    );
    
    // Clear messages when user makes changes
    if (error) setError(null);
    if (success) setSuccess(null);
  };

  /**
   * Handle form submission for key-value mode
   */
  const handleKeyValueSubmit = async () => {
    // Reset previous states
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      // Validate alert type
      if (!alertType || alertType.trim().length === 0) {
        setError('Alert Type is required');
        return;
      }

      // Process key-value pairs (filter empty ones)
      const processedData: Record<string, any> = {};
      for (const pair of keyValuePairs) {
        // Skip completely empty pairs
        if (!pair.key && !pair.value) continue;
        
        // Validate key
        if (!pair.key || pair.key.trim().length === 0) {
          setError(`Key cannot be empty if value is provided`);
          return;
        }
        
        const trimmedKey = pair.key.trim();
        const trimmedValue = pair.value.trim();
        
        // Add to data only if not empty
        if (trimmedValue) {
          processedData[trimmedKey] = trimmedValue;
        }
      }

      // Build alert data
      const alertData: any = {
        alert_type: alertType.trim(),
        data: processedData
      };
      
      // Add runbook only if not "Default Runbook"
      if (runbook && runbook !== DEFAULT_RUNBOOK) {
        alertData.runbook = runbook;
      }

      // Submit alert
      const response = await apiClient.submitAlert(alertData);
      
      setSuccess(`Alert submitted successfully! 
        Session ID: ${response.session_id}
        Status: ${response.status}
        Message: ${response.message || 'Processing started'}`);
      
      onAlertSubmitted(response);

      // Clear form on successful submission
      setKeyValuePairs([
        { id: generateId(), key: 'cluster', value: '' },
        { id: generateId(), key: 'namespace', value: '' },
        { id: generateId(), key: 'message', value: '' }
      ]);

    } catch (error: any) {
      console.error('Error submitting alert:', error);
      
      let errorMessage = 'Failed to submit alert';
      if (error.response?.data?.detail) {
        errorMessage = typeof error.response.data.detail === 'string' 
          ? error.response.data.detail 
          : error.response.data.detail.message || errorMessage;
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handle form submission for free-text mode
   */
  const handleFreeTextSubmit = async () => {
    // Reset previous states
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      // Validate alert type
      if (!alertType || alertType.trim().length === 0) {
        setError('Alert Type is required');
        return;
      }

      // Validate free text
      if (!freeText || freeText.trim().length === 0) {
        setError('Free text cannot be empty');
        return;
      }

      // Parse free text
      const parsed = parseFreeText(freeText);

      // Build alert data
      const alertData: any = {
        alert_type: alertType.trim(),
        data: parsed.data
      };
      
      // Add runbook only if not "Default Runbook"
      if (runbook && runbook !== DEFAULT_RUNBOOK) {
        alertData.runbook = runbook;
      }

      // Submit alert
      const response = await apiClient.submitAlert(alertData);
      
      setSuccess(`Alert submitted successfully! 
        Session ID: ${response.session_id}
        Status: ${response.status}
        Message: ${response.message || 'Processing started'}
        Parsing: ${parsed.success ? 'Structured data extracted' : 'Sent as message field'}`);
      
      onAlertSubmitted(response);

      // Clear form on successful submission
      setFreeText('');

    } catch (error: any) {
      console.error('Error submitting alert:', error);
      
      let errorMessage = 'Failed to submit alert';
      if (error.response?.data?.detail) {
        errorMessage = typeof error.response.data.detail === 'string' 
          ? error.response.data.detail 
          : error.response.data.detail.message || errorMessage;
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ width: '100%' }}>
      <CardContent>
        <Typography variant="h5" component="h2" gutterBottom>
          Submit Manual Alert for Analysis
        </Typography>
        
        <Typography variant="body2" color="text.secondary" paragraph>
          Choose between structured key-value input or free-text format. 
          Select a runbook from the dropdown or use the default.
        </Typography>

        {error && (
          <MuiAlert severity="error" sx={{ mb: 2 }}>
            <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
              {error}
            </Typography>
          </MuiAlert>
        )}

        {success && (
          <MuiAlert severity="success" sx={{ mb: 2 }}>
            <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
              {success}
            </Typography>
          </MuiAlert>
        )}

        <Box>
          <Stack spacing={3}>
            {/* Common Section */}
            <Box>
              <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 600 }}>
                Alert Configuration
              </Typography>
            </Box>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                select
                fullWidth
                label="Alert Type"
                value={alertType}
                onChange={(e) => setAlertType(e.target.value)}
                required
                helperText="The type of alert for agent selection"
                disabled={availableAlertTypes.length === 0}
              >
                {availableAlertTypes.length === 0 ? (
                  <MenuItem disabled>Loading alert types...</MenuItem>
                ) : (
                  availableAlertTypes.map((type) => (
                    <MenuItem key={type} value={type}>
                      {type}
                    </MenuItem>
                  ))
                )}
              </TextField>

              <Autocomplete
                fullWidth
                freeSolo
                value={runbook}
                onChange={(_, newValue) => setRunbook(newValue)}
                options={availableRunbooks}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Runbook"
                    helperText="Select from list or enter custom URL"
                  />
                )}
              />
            </Stack>

            <Divider sx={{ my: 2 }} />

            {/* Mode Selection Tabs */}
            <Paper elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
              <Tabs value={mode} onChange={(_, newValue) => setMode(newValue)}>
                <Tab label="Key-Value Mode" />
                <Tab label="Free-Text Mode" />
              </Tabs>
            </Paper>

            {/* Mode A: Key-Value Form */}
            {mode === 0 && (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                  <Typography variant="h6" sx={{ color: 'primary.main', fontWeight: 600 }}>
                    Alert Data (Key-Value)
                  </Typography>
                  <Button
                    startIcon={<AddIcon />}
                    onClick={addKeyValuePair}
                    size="small"
                    variant="outlined"
                  >
                    Add Field
                  </Button>
                </Box>

                <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
                  Add key-value pairs for your alert data. Empty fields will be ignored.
                </Typography>

                <Stack spacing={2}>
                  {keyValuePairs.map((pair) => (
                    <Box key={pair.id} sx={{ 
                      display: 'flex', 
                      alignItems: 'flex-start', 
                      gap: 2,
                      p: 2,
                      backgroundColor: 'grey.50',
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'grey.200'
                    }}>
                      <TextField
                        label="Key"
                        value={pair.key}
                        onChange={(e) => updateKeyValuePair(pair.id, 'key', e.target.value)}
                        placeholder="e.g., cluster, namespace"
                        size="small"
                        sx={{ flex: 1 }}
                      />
                      <TextField
                        label="Value"
                        value={pair.value}
                        onChange={(e) => updateKeyValuePair(pair.id, 'value', e.target.value)}
                        placeholder="Field value"
                        size="small"
                        sx={{ flex: 2 }}
                      />
                      <IconButton
                        onClick={() => removeKeyValuePair(pair.id)}
                        size="small"
                        color="error"
                        title="Remove field"
                      >
                        <CloseIcon />
                      </IconButton>
                    </Box>
                  ))}
                </Stack>

                <Box sx={{ mt: 3 }}>
                  <Button
                    variant="contained"
                    size="large"
                    startIcon={loading ? <CircularProgress size={20} /> : <SendIcon />}
                    disabled={loading}
                    fullWidth
                    onClick={handleKeyValueSubmit}
                  >
                    {loading ? 'Submitting Alert...' : 'Send Alert (Key-Value Mode)'}
                  </Button>
                </Box>
              </Box>
            )}

            {/* Mode B: Free-Text Form */}
            {mode === 1 && (
              <Box>
                <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 600 }}>
                  Alert Data (Free-Text)
                </Typography>

                <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
                  Enter alert data in free-text format. We'll try to parse "Key: Value" or "Key=Value" patterns.
                  If parsing fails, the entire text will be sent as a message field.
                </Typography>

                <TextField
                  fullWidth
                  multiline
                  rows={12}
                  value={freeText}
                  onChange={(e) => {
                    setFreeText(e.target.value);
                    if (error) setError(null);
                    if (success) setSuccess(null);
                  }}
                  placeholder={`Alert: ProgressingApplication
Severity: warning
Environment: staging
Cluster: host
Namespace: openshift-gitops
Pod: openshift-gitops-application-controller-0
Message: The 'tarsy' Argo CD application is stuck in 'Progressing' status`}
                  variant="outlined"
                  sx={{ 
                    fontFamily: 'monospace',
                    '& .MuiInputBase-input': {
                      fontFamily: 'monospace'
                    }
                  }}
                />

                <Box sx={{ mt: 3 }}>
                  <Button
                    variant="contained"
                    size="large"
                    startIcon={loading ? <CircularProgress size={20} /> : <SendIcon />}
                    disabled={loading}
                    fullWidth
                    onClick={handleFreeTextSubmit}
                  >
                    {loading ? 'Submitting Alert...' : 'Send Alert (Free-Text Mode)'}
                  </Button>
                </Box>
              </Box>
            )}
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ManualAlertForm;
