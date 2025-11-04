/**
 * Manual Alert submission form component - EP-0018
 * Redesigned with dual-mode input: Text or Structured Key-Value pairs
 * Supports runbook dropdown with GitHub repository integration
 */

import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
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
  TableChart as TableChartIcon,
  InfoOutlined as InfoIcon
} from '@mui/icons-material';

import type { KeyValuePair, ManualAlertFormProps, MCPSelectionConfig } from '../types';
import { apiClient } from '../services/api';
import MCPSelection from './MCPSelection/MCPSelection';

/**
 * Generate a unique ID for key-value pairs
 */
const generateId = () => Math.random().toString(36).substr(2, 9);

/**
 * Default runbook option constant
 */
const DEFAULT_RUNBOOK = 'Default Runbook';

/**
 * Check if text looks like structured data (YAML, JSON, etc.)
 * Complex structured data should be preserved as-is, not parsed line-by-line
 */
const isStructuredData = (text: string): boolean => {
  const trimmed = text.trim();
  
  // Check for JSON
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || 
      (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      JSON.parse(trimmed);
      return true;
    } catch {
      // Not valid JSON, continue checking other formats
    }
  }
  
  // Check for YAML-like indicators:
  // - Indented lines (suggesting nested structure)
  // - List items starting with "-"
  // - Multi-level nesting
  const lines = text.split('\n');
  let hasIndentation = false;
  let hasListItems = false;
  let hasMultipleColons = 0;
  
  for (const line of lines) {
    // Check for indentation (spaces at start)
    if (line.match(/^\s{2,}/)) {
      hasIndentation = true;
    }
    
    // Check for YAML list items
    if (line.trim().match(/^-\s+/)) {
      hasListItems = true;
    }
    
    // Count lines with colons (key: value)
    if (line.includes(':')) {
      hasMultipleColons++;
    }
  }
  
  // If it has indentation, list items, or many colons (suggesting nested YAML/structured data)
  if (hasIndentation || hasListItems || hasMultipleColons > 5) {
    return true;
  }
  
  return false;
};

/**
 * Parse free-text input into key-value pairs
 * - For complex structured data (YAML, JSON, etc.): preserves as-is in 'message' field
 * - For simple text: attempts to parse "Key: Value" or "Key=Value" patterns line by line
 * - Falls back to 'message' field if parsing fails
 */
const parseFreeText = (text: string): { success: boolean; data: Record<string, any> } => {
  // Check if this is structured data that should be preserved as-is
  if (isStructuredData(text)) {
    return {
      success: true,
      data: { message: text }
    };
  }

  const lines = text.split('\n');
  const data: Record<string, any> = {};
  let successCount = 0;
  let failedLines = 0;

  for (const line of lines) {
    const trimmedLine = line.trim();
    if (!trimmedLine) continue;

    // Try parsing "Key: Value" format (but not YAML-like nested structures)
    const colonMatch = trimmedLine.match(/^([^:]+):\s*(.*)$/);
    if (colonMatch && !trimmedLine.startsWith('-')) {
      const key = colonMatch[1].trim();
      const value = colonMatch[2].trim();
      if (key && !key.includes(' ')) { // Simple keys only (no spaces = likely real key)
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
      if (key && !key.includes(' ')) { // Simple keys only
        data[key] = value;
        successCount++;
        continue;
      }
    }
    
    // If we couldn't parse this line, count it as failed
    failedLines++;
  }

  // If we failed to parse more than 30% of non-empty lines, treat as raw message
  const totalLines = lines.filter(l => l.trim()).length;
  if (totalLines > 0 && failedLines / totalLines > 0.3) {
    return {
      success: true,
      data: { message: text }
    };
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
  const location = useLocation();
  const navigate = useNavigate();
  
  // Track if we've already processed resubmit state (prevents re-processing on re-renders)
  const resubmitProcessedRef = useRef(false);
  
  // Default alert type to use (set by resubmit or will use API default)
  const defaultAlertTypeRef = useRef<string | null>(null);
  
  // Re-submission state
  const [sourceSessionId, setSourceSessionId] = useState<string | null>(null);
  const [showResubmitBanner, setShowResubmitBanner] = useState(false);
  
  // Common fields
  const [alertType, setAlertType] = useState('');
  const [runbook, setRunbook] = useState<string | null>(DEFAULT_RUNBOOK);
  const [mcpSelection, setMcpSelection] = useState<MCPSelectionConfig | null>(null);
  
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

  // STEP 1: Process resubmit FIRST - set the default alert type before API loads
  useEffect(() => {
    const state = location.state as any;
    
    // Only process resubmit once (prevents issues with StrictMode and re-renders)
    if (state?.resubmit && state?.alertData && !resubmitProcessedRef.current) {
      resubmitProcessedRef.current = true;
      
      // Set the default alert type for API loading to use
      if (state.alertType) {
        defaultAlertTypeRef.current = state.alertType;
      }
      
      // Set re-submission state
      setSourceSessionId(state.sessionId || null);
      setShowResubmitBanner(true);
      
      // Set runbook
      if (state.runbook) {
        setRunbook(state.runbook);
      }
      
      // Set MCP selection
      if (state.mcpSelection) {
        setMcpSelection(state.mcpSelection);
      }
      
      // Process alert data
      const alertData = state.alertData;
      
      // Filter out meta fields (runbook, alert_type) from the data
      const filteredData = { ...alertData };
      delete filteredData.runbook;
      delete filteredData.alert_type;
      
      // Always use text mode for re-submissions
      setMode(1);
      
      // Special case: if data is just {"message": "text"}, extract the plain text
      const keys = Object.keys(filteredData);
      if (keys.length === 1 && keys[0] === 'message' && typeof filteredData.message === 'string') {
        // Extract just the message text (form will wrap it back when submitting)
        setFreeText(filteredData.message);
      } else {
        // Format the data as JSON for easy editing
        setFreeText(JSON.stringify(filteredData, null, 2));
      }
      
      // Clear location state to prevent re-population on refresh
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location, navigate]);

  // STEP 2: Load available alert types and runbooks from API
  useEffect(() => {
    const loadOptions = async () => {
      try {
        // Load alert types from API
        const alertTypes = await apiClient.getAlertTypes();
        if (Array.isArray(alertTypes)) {
          // Check if we have a default alert type (from resubmit)
          const defaultType = defaultAlertTypeRef.current;
          
          // Ensure default type is in the list
          let finalAlertTypes = alertTypes;
          if (defaultType && !alertTypes.includes(defaultType)) {
            finalAlertTypes = [defaultType, ...alertTypes];
          }
          
          setAvailableAlertTypes(finalAlertTypes);
          
          // Set the alert type (use default if available, otherwise use API default)
          if (defaultType) {
            setAlertType(defaultType);
          } else if (alertTypes.includes('kubernetes')) {
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

      // Add MCP selection if configured
      if (mcpSelection && mcpSelection.servers.length > 0) {
        alertData.mcp = mcpSelection;
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
      setMcpSelection(null);

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

      // Add MCP selection if configured
      if (mcpSelection && mcpSelection.servers.length > 0) {
        alertData.mcp = mcpSelection;
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
      setMcpSelection(null);

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

      {/* Re-submit banner */}
      {showResubmitBanner && sourceSessionId && (
        <Box sx={{ mb: 3, px: 3 }}>
          <MuiAlert 
            severity="info"
            icon={<InfoIcon />}
            onClose={() => setShowResubmitBanner(false)}
            sx={{ 
              borderRadius: 3,
              '& .MuiAlert-icon': { fontSize: 24 }
            }}
          >
            <Typography variant="body2">
              <strong>Pre-filled from previous session:</strong>{' '}
              <code style={{ 
                backgroundColor: 'rgba(0, 0, 0, 0.05)', 
                padding: '2px 6px', 
                borderRadius: '4px',
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}>
                {sourceSessionId.slice(-12)}
              </code>
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              You can modify any fields before submitting.
            </Typography>
          </MuiAlert>
        </Box>
      )}

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

          {/* MCP Server Configuration (Advanced) */}
          <MCPSelection 
            value={mcpSelection}
            onChange={setMcpSelection}
            disabled={loading}
          />

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
                {/* Character and line count */}
                {freeText && (
                  <Box 
                    sx={{ 
                      display: 'flex',
                      justifyContent: 'flex-end',
                      alignItems: 'center',
                      mt: 0.5,
                      px: 1
                    }}
                  >
                    <Typography variant="caption" color="text.secondary">
                      {freeText.length} characters, {freeText.split('\n').length} lines
                    </Typography>
                  </Box>
                )}
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
