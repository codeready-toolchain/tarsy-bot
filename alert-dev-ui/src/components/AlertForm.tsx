/**
 * Flexible Alert submission form component (Development/Testing Interface)
 * Supports arbitrary key-value pairs for flexible alert data structures
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
  Grid,
  Alert as MuiAlert,
  CircularProgress,
  IconButton,
  Divider,
  Chip,
} from '@mui/material';
import { 
  Send as SendIcon, 
  Add as AddIcon, 
  Remove as RemoveIcon,
  Close as CloseIcon 
} from '@mui/icons-material';

import { AlertResponse } from '../types';
import ApiService from '../services/api';

interface KeyValuePair {
  id: string;
  key: string;
  value: string;
}

interface AlertFormProps {
  onAlertSubmitted: (alertResponse: AlertResponse) => void;
}

/**
 * Generate a unique ID for key-value pairs
 */
const generateId = () => Math.random().toString(36).substr(2, 9);

/**
 * Common field presets for quick setup
 */
const fieldPresets = [
  { key: 'severity', value: 'critical', description: 'Alert severity level' },
  { key: 'environment', value: 'production', description: 'Environment (prod/staging/dev)' },
  { key: 'cluster', value: 'https://api.cluster.example.com:443', description: 'Kubernetes cluster URL' },
  { key: 'namespace', value: 'default', description: 'Kubernetes namespace' },
  { key: 'pod', value: 'web-app-abc123', description: 'Pod name (optional)' },
  { key: 'message', value: 'Sample alert message', description: 'Alert description' },
  { key: 'region', value: 'us-west-2', description: 'Cloud region' },
  { key: 'service', value: 'web-service', description: 'Service name' },
];

const AlertForm: React.FC<AlertFormProps> = ({ onAlertSubmitted }) => {
  // Required fields
  const [alertType, setAlertType] = useState('');
  const [runbook, setRunbook] = useState('https://github.com/alexeykazakov/runbooks/blob/master/namespace-terminating-v2.md');
  
  // Dynamic key-value pairs
  const [keyValuePairs, setKeyValuePairs] = useState<KeyValuePair[]>([
    { id: generateId(), key: 'severity', value: 'critical' },
    { id: generateId(), key: 'environment', value: 'production' },
    { id: generateId(), key: 'cluster', value: 'https://api.crc.testing:6443' },
    { id: generateId(), key: 'namespace', value: 'superman-dev' },
    { id: generateId(), key: 'message', value: 'Namespace is stuck in terminating state' }
  ]);

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
        // Set default alertType to 'kubernetes' if available, otherwise first available type
        if (alertTypes.includes('kubernetes')) {
          setAlertType('kubernetes');
        } else if (alertTypes.length > 0) {
          setAlertType(alertTypes[0]);
        }
      } catch (error) {
        console.error('Failed to load alert types:', error);
        setError('Failed to load alert types from backend');
      }
    };

    loadAlertTypes();
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
   * Add a preset field
   */
  const addPresetField = (preset: typeof fieldPresets[0]) => {
    // Check if key already exists
    const keyExists = keyValuePairs.some(pair => pair.key === preset.key);
    if (!keyExists) {
      setKeyValuePairs(prev => [
        ...prev,
        { id: generateId(), key: preset.key, value: preset.value }
      ]);
    }
  };

  /**
   * Handle form submission
   */
  const handleSubmit = async () => {
    // Reset previous states
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      // Comprehensive form validation
      const validationErrors: string[] = [];
      
      // Validate required fields
      if (!alertType || alertType.trim().length === 0) {
        validationErrors.push('Alert Type is required');
      }
      
      if (!runbook || runbook.trim().length === 0) {
        validationErrors.push('Runbook URL is required');
      } else {
        // Validate runbook URL format
        try {
          new URL(runbook);
        } catch (urlError) {
          validationErrors.push('Runbook must be a valid URL (e.g., https://github.com/...)');
        }
      }

      // Validate key-value pairs
      const processedPairs: { key: string; value: any }[] = [];
      const usedKeys = new Set<string>();
      
      for (let index = 0; index < keyValuePairs.length; index++) {
        const pair = keyValuePairs[index];
        // Skip empty pairs
        if (!pair.key && !pair.value) {
          continue;
        }
        
        // Validate key
        if (!pair.key || pair.key.trim().length === 0) {
          validationErrors.push(`Row ${index + 1}: Key cannot be empty`);
          continue;
        }
        
        const trimmedKey = pair.key.trim();
        
        // Check for duplicate keys
        if (usedKeys.has(trimmedKey)) {
          validationErrors.push(`Row ${index + 1}: Duplicate key "${trimmedKey}"`);
          continue;
        }
        
        // Validate key format (no special characters except underscore)
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmedKey)) {
          validationErrors.push(`Row ${index + 1}: Key "${trimmedKey}" contains invalid characters. Use only letters, numbers, and underscores.`);
          continue;
        }
        
        usedKeys.add(trimmedKey);
        
                 // Validate value (keep as string for now, will process later)
         let valueForStorage = pair.value;
         
         if (typeof pair.value === 'string' && pair.value.trim().length > 0) {
           const trimmedValue = pair.value.trim();
           
           // Validate JSON if it looks like JSON
           if ((trimmedValue.startsWith('{') && trimmedValue.endsWith('}')) ||
               (trimmedValue.startsWith('[') && trimmedValue.endsWith(']'))) {
             try {
               JSON.parse(trimmedValue); // Just validate, don't store parsed value yet
               valueForStorage = trimmedValue;
             } catch (jsonError) {
               validationErrors.push(`Row ${index + 1}: Invalid JSON format for key "${trimmedKey}"`);
               continue;
             }
           } else {
             valueForStorage = trimmedValue;
           }
         }
         
         processedPairs.push({ key: trimmedKey, value: valueForStorage });
      }

      // Show validation errors
      if (validationErrors.length > 0) {
        setError(`Validation failed:\n${validationErrors.map((err, i) => `${i + 1}. ${err}`).join('\n')}`);
        return;
      }

      // Build alert data
      const alertData: any = {
        alert_type: alertType.trim(),
        runbook: runbook.trim(),
        data: {}
      };

             // Add processed key-value pairs to data with type conversion
       processedPairs.forEach(pair => {
         let processedValue = pair.value;
         
         if (typeof pair.value === 'string' && pair.value.trim().length > 0) {
           const trimmedValue = pair.value.trim();
           
           // Try to parse as JSON if it looks like JSON
           if ((trimmedValue.startsWith('{') && trimmedValue.endsWith('}')) ||
               (trimmedValue.startsWith('[') && trimmedValue.endsWith(']'))) {
             try {
               processedValue = JSON.parse(trimmedValue);
             } catch {
               // Keep as string if JSON parsing fails (shouldn't happen due to validation)
               processedValue = trimmedValue;
             }
           }
           // Try to parse as number
           else if (/^-?\d+(\.\d+)?$/.test(trimmedValue)) {
             processedValue = Number(trimmedValue);
           }
           // Try to parse as boolean
           else if (trimmedValue.toLowerCase() === 'true' || trimmedValue.toLowerCase() === 'false') {
             processedValue = trimmedValue.toLowerCase() === 'true';
           }
           // Keep as string
           else {
             processedValue = trimmedValue;
           }
         }
         
         alertData.data[pair.key] = processedValue;
       });

      // Input sanitization and size checks
      const alertDataJson = JSON.stringify(alertData);
      const MAX_PAYLOAD_SIZE = 5 * 1024 * 1024; // 5MB limit
      
      if (alertDataJson.length > MAX_PAYLOAD_SIZE) {
        setError(`Alert data is too large (${(alertDataJson.length / 1024 / 1024).toFixed(2)}MB). Maximum size is 5MB.`);
        return;
      }

      // Log submission attempt
      console.log('Submitting alert:', { 
        alert_type: alertData.alert_type, 
        data_keys: Object.keys(alertData.data),
        size_bytes: alertDataJson.length 
      });

      // Submit flexible alert with timeout
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Request timeout')), 30000) // 30 second timeout
      );
      
      const submitPromise = ApiService.submitAlert(alertData);
      
      const response = await Promise.race([submitPromise, timeoutPromise]) as any;
      
      setSuccess(`Alert submitted successfully! 
        ID: ${response.alert_id}
        Status: ${response.status}
        Message: ${response.message || 'Processing started'}
        Data size: ${(alertDataJson.length / 1024).toFixed(1)}KB`);
      
      onAlertSubmitted(response);

      // Clear form on successful submission
      setKeyValuePairs([{ id: generateId(), key: '', value: '' }]);

    } catch (error: any) {
      console.error('Error submitting alert:', error);
      
      // Enhanced error handling with specific messages
      let errorMessage = 'Failed to submit alert';
      
      if (error.message === 'Request timeout') {
        errorMessage = 'Request timed out. The server may be overloaded or down.';
      } else if (error.response) {
        // API error with response
        const status = error.response.status;
        const data = error.response.data;
        
        if (status === 400) {
          if (data.detail && typeof data.detail === 'object') {
            if (data.detail.validation_errors) {
              errorMessage = `Validation failed:\n${data.detail.validation_errors.map((err: any) => 
                `• ${err.field}: ${err.message}`
              ).join('\n')}`;
            } else {
              errorMessage = `Bad Request: ${data.detail.message || data.detail.error || 'Invalid request format'}`;
            }
          } else if (typeof data.detail === 'string') {
            errorMessage = `Bad Request: ${data.detail}`;
          } else {
            errorMessage = 'Bad Request: Invalid data format';
          }
        } else if (status === 413) {
          errorMessage = 'Request payload too large. Please reduce the amount of data.';
        } else if (status === 422) {
          if (data.detail && data.detail.validation_errors) {
            errorMessage = `Validation failed:\n${data.detail.validation_errors.map((err: any) => 
              `• ${err.field}: ${err.message}`
            ).join('\n')}`;
          } else {
            errorMessage = 'Data validation failed. Please check your input.';
          }
        } else if (status === 429) {
          errorMessage = 'Too many requests. Please wait a moment and try again.';
        } else if (status === 500) {
          errorMessage = 'Server error occurred. Please try again later.';
        } else if (status === 503) {
          errorMessage = 'Service temporarily unavailable. Please try again later.';
        } else {
          errorMessage = `Request failed with status ${status}: ${data.detail || data.message || 'Unknown error'}`;
        }
      } else if (error.request) {
        // Network error
        errorMessage = 'Network error. Please check your connection and ensure the backend is running.';
      } else {
        // Other errors
        errorMessage = `Unexpected error: ${error.message}`;
      }
      
      setError(errorMessage);
      
      // Log detailed error information for debugging
      console.error('Detailed error information:', {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
        url: error.config?.url,
        method: error.config?.method
      });
      
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ maxWidth: 900, margin: '0 auto' }}>
      <CardContent>
        <Typography variant="h5" component="h2" gutterBottom>
          Submit Flexible Alert for Analysis
        </Typography>
        
        <Typography variant="body2" color="text.secondary" paragraph>
          Use this form to submit alerts with flexible data structures. 
          Only Alert Type and Runbook are required - add any additional fields as key-value pairs.
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

        <Box component="form" onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
          <Grid container spacing={3}>
            {/* Required Fields */}
            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 600 }}>
                Required Fields
              </Typography>
            </Grid>

            <Grid item xs={12} md={6}>
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
            </Grid>

            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Runbook URL"
                value={runbook}
                onChange={(e) => setRunbook(e.target.value)}
                placeholder="https://github.com/org/repo/blob/master/runbooks/alert.md"
                required
                helperText="URL to the processing runbook"
              />
            </Grid>

            <Grid item xs={12}>
              <Divider sx={{ my: 2 }} />
            </Grid>

            {/* Dynamic Fields */}
            <Grid item xs={12}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6" sx={{ color: 'primary.main', fontWeight: 600 }}>
                  Additional Alert Data
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

              {/* Field Presets */}
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Quick Add Common Fields:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {fieldPresets.map((preset) => (
                    <Chip
                      key={preset.key}
                      label={preset.key}
                      onClick={() => addPresetField(preset)}
                      size="small"
                      variant="outlined"
                      sx={{ cursor: 'pointer' }}
                      title={preset.description}
                    />
                  ))}
                </Box>
              </Box>
            </Grid>

            {/* Key-Value Pairs */}
            {keyValuePairs.map((pair, index) => (
              <Grid item xs={12} key={pair.id}>
                <Box sx={{ 
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
                    label="Field Name"
                    value={pair.key}
                    onChange={(e) => updateKeyValuePair(pair.id, 'key', e.target.value)}
                    placeholder="e.g., severity, cluster, etc."
                    size="small"
                    sx={{ flex: 1 }}
                  />
                  <TextField
                    label="Value"
                    value={pair.value}
                    onChange={(e) => updateKeyValuePair(pair.id, 'value', e.target.value)}
                    placeholder="Field value (strings, JSON objects, arrays, etc.)"
                    multiline
                    maxRows={3}
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
              </Grid>
            ))}

            <Grid item xs={12}>
              <Divider sx={{ my: 2 }} />
            </Grid>

            {/* Submit Button */}
            <Grid item xs={12}>
              <Button
                type="submit"
                variant="contained"
                size="large"
                startIcon={loading ? <CircularProgress size={20} /> : <SendIcon />}
                disabled={loading}
                fullWidth
              >
                {loading ? 'Submitting Alert...' : 'Submit Flexible Alert'}
              </Button>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
  );
};

export default AlertForm;