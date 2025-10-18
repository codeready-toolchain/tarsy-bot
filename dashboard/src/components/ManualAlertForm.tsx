/**
 * Manual Alert submission form component - EP-0018
 * Redesigned with dual-mode input: Text or Structured Key-Value pairs
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
  Autocomplete,
  Paper,
} from '@mui/material';
import { 
  Send as SendIcon, 
  Add as AddIcon, 
  Close as CloseIcon,
  Description as DescriptionIcon,
  TableChart as TableChartIcon
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

/**
 * Validate runbook URL to prevent SSRF attacks
 * Only allows:
 * - Default runbook option
 * - URLs from the backend's approved list
 * - GitHub URLs (github.com or raw.githubusercontent.com)
 */
const isValidRunbookUrl = (url: string | null, approvedRunbooks: string[]): boolean => {
  // Allow null or empty
  if (!url) return true;
  
  // Allow default runbook
  if (url === DEFAULT_RUNBOOK) return true;
  
  // Allow if it's in the approved list from backend
  if (approvedRunbooks.includes(url)) return true;
  
  // For custom URLs, only allow GitHub
  try {
    const urlObj = new URL(url);
    const hostname = urlObj.hostname.toLowerCase();
    
    // Only allow GitHub domains
    return hostname === 'github.com' || 
           hostname === 'www.github.com' || 
           hostname === 'raw.githubusercontent.com';
  } catch {
    // Invalid URL format
    return false;
  }
};

const ManualAlertForm: React.FC<ManualAlertFormProps> = ({ onAlertSubmitted }) => {
  // Common fields
  const [alertType, setAlertType] = useState('');
  const [runbook, setRunbook] = useState<string | null>(DEFAULT_RUNBOOK);
  
  // Mode selection (0 = Structured, 1 = Text) - Default to Text
  const [mode, setMode] = useState(1);
  
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
  const [runbookError, setRunbookError] = useState<string | null>(null);

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

      // Validate runbook URL to prevent SSRF
      if (!isValidRunbookUrl(runbook, availableRunbooks)) {
        setError('Invalid runbook URL. Only GitHub URLs or approved runbooks are allowed.');
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

      // Validate runbook URL to prevent SSRF
      if (!isValidRunbookUrl(runbook, availableRunbooks)) {
        setError('Invalid runbook URL. Only GitHub URLs or approved runbooks are allowed.');
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
    <Box sx={{ width: '100%' }}>
      {/* M3 Header Section */}
      <Box sx={{ mb: 3, px: 3 }}>
        <Typography 
          variant="h4" 
          component="h1" 
          gutterBottom 
          sx={{ 
            fontWeight: 600,
            mb: 1,
            letterSpacing: '-0.02em'
          }}
        >
          Submit Alert for Analysis
        </Typography>
        <Typography 
          variant="body1" 
          color="text.secondary"
          sx={{ fontSize: '1rem', lineHeight: 1.6 }}
        >
          Enter alert details as text or use structured key-value pairs. 
          Select a runbook from the dropdown or use the default.
        </Typography>
      </Box>

      <Card 
        elevation={0} 
        sx={{ 
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          overflow: 'visible'
        }}
      >
        <CardContent sx={{ p: 0 }}>

          {/* M3 Alert Messages */}
        {error && (
            <Box sx={{ px: 4, pt: 3 }}>
              <MuiAlert 
                severity="error" 
                sx={{ 
                  borderRadius: 3,
                  '& .MuiAlert-icon': { fontSize: 24 }
                }}
              >
                <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
              {error}
            </Typography>
          </MuiAlert>
            </Box>
        )}

        {success && (
            <Box sx={{ px: 4, pt: 3 }}>
              <MuiAlert 
                severity="success"
                sx={{ 
                  borderRadius: 3,
                  '& .MuiAlert-icon': { fontSize: 24 }
                }}
              >
                <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
              {success}
            </Typography>
          </MuiAlert>
            </Box>
          )}

          {/* M3 Configuration Section */}
          <Box sx={{ px: 4, pt: error || success ? 2 : 4, pb: 3 }}>
            <Typography 
              variant="overline" 
              sx={{ 
                color: 'text.secondary',
                fontWeight: 700,
                letterSpacing: 1.2,
                fontSize: '0.8rem',
                mb: 2,
                display: 'block'
              }}
            >
              Configuration
            </Typography>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <TextField
                select
                fullWidth
                label="Alert Type"
                value={alertType}
                onChange={(e) => setAlertType(e.target.value)}
                required
                helperText="The type of alert for agent selection"
                disabled={availableAlertTypes.length === 0}
                variant="filled"
                sx={{
                  '& .MuiFilledInput-root': {
                    borderRadius: 2,
                    '&:before, &:after': {
                      display: 'none'
                    }
                  }
                }}
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
                onChange={(_, newValue) => {
                  setRunbook(newValue);
                  // Validate runbook URL in real-time
                  if (newValue && !isValidRunbookUrl(newValue, availableRunbooks)) {
                    setRunbookError('Invalid runbook URL. Only GitHub URLs or approved runbooks are allowed.');
                  } else {
                    setRunbookError(null);
                  }
                }}
                options={availableRunbooks}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Runbook"
                    helperText={runbookError || "Select from list or enter custom GitHub URL"}
                    error={!!runbookError}
                    variant="filled"
                    sx={{
                      '& .MuiFilledInput-root': {
                        borderRadius: 2,
                        '&:before, &:after': {
                          display: 'none'
                        }
                      }
                    }}
                  />
                )}
              />
            </Stack>

          </Box>

          {/* M3 Tabs Section */}
          <Box sx={{ px: 4, py: 2, bgcolor: 'rgba(25, 118, 210, 0.04)' }}>
            <Typography 
              variant="overline" 
              sx={{ 
                color: 'text.secondary',
                fontWeight: 700,
                letterSpacing: 1.2,
                fontSize: '0.8rem',
                mb: 2,
                display: 'block'
              }}
            >
              Input Method
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {/* M3 Segmented Buttons */}
              <Box
                onClick={() => setMode(1)}
                sx={{
                  flex: { xs: '1 1 100%', sm: '0 1 auto' },
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 1.5,
                  py: 1.75,
                  px: 4,
                  borderRadius: 1,
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                  bgcolor: mode === 1 ? 'primary.main' : 'transparent',
                  color: mode === 1 ? 'primary.contrastText' : 'text.primary',
                  border: '2px solid',
                  borderColor: mode === 1 ? 'primary.main' : 'grey.300',
                  '&:hover': {
                    bgcolor: mode === 1 ? 'primary.dark' : 'action.hover',
                    borderColor: mode === 1 ? 'primary.dark' : 'grey.400',
                  },
                }}
              >
                <DescriptionIcon sx={{ fontSize: 22 }} />
                <Typography 
                  variant="body1"
                  sx={{ 
                    fontWeight: mode === 1 ? 700 : 600,
                    fontSize: '0.95rem'
                  }}
                >
                  Text
                </Typography>
              </Box>

              <Box
                onClick={() => setMode(0)}
                sx={{
                  flex: { xs: '1 1 100%', sm: '0 1 auto' },
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 1.5,
                  py: 1.75,
                  px: 4,
                  borderRadius: 1,
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                  bgcolor: mode === 0 ? 'primary.main' : 'transparent',
                  color: mode === 0 ? 'primary.contrastText' : 'text.primary',
                  border: '2px solid',
                  borderColor: mode === 0 ? 'primary.main' : 'grey.300',
                  '&:hover': {
                    bgcolor: mode === 0 ? 'primary.dark' : 'action.hover',
                    borderColor: mode === 0 ? 'primary.dark' : 'grey.400',
                  },
                }}
              >
                <TableChartIcon sx={{ fontSize: 22 }} />
                <Typography 
                  variant="body1"
                  sx={{ 
                    fontWeight: mode === 0 ? 700 : 600,
                    fontSize: '0.95rem'
                  }}
                >
                  Structured Input
                </Typography>
              </Box>
            </Box>
          </Box>

          {/* Mode A: Structured Input Form */}
          {mode === 0 && (
            <Box 
              sx={{
                px: 4,
                py: 4,
                animation: 'fadeIn 0.3s ease-in-out',
                '@keyframes fadeIn': {
                  from: { opacity: 0, transform: 'translateY(8px)' },
                  to: { opacity: 1, transform: 'translateY(0)' }
                }
              }}
            >
              {/* M3 Header with Action */}
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 3 }}>
                <Box>
                  <Typography 
                    variant="h6" 
                    sx={{ 
                      fontWeight: 600,
                      mb: 0.5,
                      fontSize: '1.25rem'
                    }}
                  >
                    Alert Data
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Enter structured key-value pairs for your alert data
                  </Typography>
                </Box>
                <Button
                  startIcon={<AddIcon />}
                  onClick={addKeyValuePair}
                  variant="contained"
                  size="large"
                  sx={{
                    borderRadius: 1,
                    textTransform: 'none',
                    fontWeight: 600,
                    px: 3,
                    boxShadow: 1,
                    '&:hover': {
                      boxShadow: 2
                    }
                  }}
                >
                  Add Field
                </Button>
              </Box>

              {/* M3 Field Cards */}
            <Stack spacing={2}>
              {keyValuePairs.map((pair) => (
                  <Paper 
                    key={pair.id}
                    elevation={0}
                    sx={{ 
                  display: 'flex', 
                  alignItems: 'flex-start', 
                  gap: 2,
                      p: 3,
                  borderRadius: 1,
                  border: '1px solid',
                      borderColor: 'divider',
                      bgcolor: 'grey.50',
                      transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&:hover': {
                        borderColor: 'primary.light',
                        bgcolor: 'background.paper',
                        boxShadow: 1
                      }
                    }}
                  >
                  <TextField
                      label="Key"
                    value={pair.key}
                    onChange={(e) => updateKeyValuePair(pair.id, 'key', e.target.value)}
                      placeholder="e.g., cluster, namespace"
                      variant="filled"
                      sx={{ 
                        flex: 1,
                        '& .MuiFilledInput-root': {
                          borderRadius: 2,
                          '&:before, &:after': {
                            display: 'none'
                          }
                        }
                      }}
                  />
                  <TextField
                    label="Value"
                    value={pair.value}
                    onChange={(e) => updateKeyValuePair(pair.id, 'value', e.target.value)}
                      placeholder="Field value"
                      variant="filled"
                      sx={{ 
                        flex: 2,
                        '& .MuiFilledInput-root': {
                          borderRadius: 2,
                          '&:before, &:after': {
                            display: 'none'
                          }
                        }
                      }}
                  />
                  <IconButton
                    onClick={() => removeKeyValuePair(pair.id)}
                      size="large"
                      sx={{
                        color: 'error.main',
                        mt: 1,
                        '&:hover': {
                          bgcolor: 'error.lighter'
                        }
                      }}
                    title="Remove field"
                  >
                    <CloseIcon />
                  </IconButton>
                  </Paper>
              ))}
            </Stack>

              {/* M3 Submit Button */}
              <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid', borderColor: 'divider' }}>
              <Button
                variant="contained"
                size="large"
                  startIcon={loading ? <CircularProgress size={22} color="inherit" /> : <SendIcon />}
                disabled={loading || !!runbookError}
                fullWidth
                  onClick={handleKeyValueSubmit}
                  sx={{
                    py: 2,
                    borderRadius: 1,
                    fontSize: '1rem',
                    fontWeight: 600,
                    textTransform: 'none',
                    boxShadow: 2,
                    '&:hover': {
                      boxShadow: 4
                    }
                  }}
                >
                  {loading ? 'Submitting Alert...' : 'Send Alert'}
                </Button>
              </Box>
            </Box>
          )}

          {/* Mode B: Text Form */}
          {mode === 1 && (
            <Box 
              sx={{
                px: 4,
                py: 4,
                animation: 'fadeIn 0.3s ease-in-out',
                '@keyframes fadeIn': {
                  from: { opacity: 0, transform: 'translateY(8px)' },
                  to: { opacity: 1, transform: 'translateY(0)' }
                }
              }}
            >
              {/* M3 Header */}
              <Box sx={{ mb: 3 }}>
                <Typography 
                  variant="h6" 
                  sx={{ 
                    fontWeight: 600,
                    mb: 0.5,
                    fontSize: '1.25rem'
                  }}
                >
                  Alert Data
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Paste or type your alert details naturally. We'll automatically parse structured data.
                </Typography>
              </Box>

              {/* M3 Text Editor */}
              <Paper 
                elevation={0}
                sx={{ 
                  position: 'relative',
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'grey.50',
                  p: 0.5,
                  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                  '&:hover': {
                    borderColor: 'primary.light',
                    bgcolor: 'background.paper'
                  },
                  '&:focus-within': {
                    borderColor: 'primary.main',
                    bgcolor: 'background.paper',
                    boxShadow: 1
                  }
                }}
              >
                <TextField
                  fullWidth
                  multiline
                  rows={16}
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
                  variant="filled"
                  sx={{ 
                    '& .MuiFilledInput-root': {
                      bgcolor: 'transparent',
                      borderRadius: 2.5,
                      fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                      fontSize: '0.9rem',
                      lineHeight: 1.6,
                      '&:before, &:after': {
                        display: 'none'
                      },
                      '&:hover': {
                        bgcolor: 'transparent'
                      },
                      '&.Mui-focused': {
                        bgcolor: 'transparent'
                      }
                    },
                    '& .MuiInputBase-input': {
                      fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                      '&::placeholder': {
                        opacity: 0.5
                      }
                    }
                  }}
                />
                <Box 
                  sx={{ 
                    position: 'absolute',
                    top: 16,
                    right: 16,
                    bgcolor: 'success.main',
                    color: 'success.contrastText',
                    px: 2,
                    py: 0.75,
                    borderRadius: 2,
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    letterSpacing: 1,
                    pointerEvents: 'none',
                    boxShadow: 1
                  }}
                >
                  AUTO-PARSE
                </Box>
              </Paper>

              {/* M3 Submit Button */}
              <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid', borderColor: 'divider' }}>
                <Button
                  variant="contained"
                  size="large"
                  startIcon={loading ? <CircularProgress size={22} color="inherit" /> : <SendIcon />}
                  disabled={loading || !!runbookError}
                  fullWidth
                  onClick={handleFreeTextSubmit}
                  sx={{
                    py: 2,
                    borderRadius: 1,
                    fontSize: '1rem',
                    fontWeight: 600,
                    textTransform: 'none',
                    boxShadow: 2,
                    '&:hover': {
                      boxShadow: 4
                    }
                  }}
                >
                  {loading ? 'Submitting Alert...' : 'Send Alert'}
              </Button>
              </Box>
            </Box>
          )}
      </CardContent>
    </Card>
    </Box>
  );
};

export default ManualAlertForm;
