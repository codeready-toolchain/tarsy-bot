/**
 * MCP Server/Tool Selection Component
 * 
 * Allows users to customize which MCP servers, tools, and native tools to use
 * for alert processing. Shows default configuration and detects changes.
 * Only sends override config when user modifies the defaults.
 */

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Box,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Card,
  CardContent,
  Typography,
  Checkbox,
  FormControlLabel,
  Button,
  Chip,
  Collapse,
  Stack,
  Alert as MuiAlert,
  CircularProgress,
  Divider,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Settings as SettingsIcon,
  ChevronRight as ChevronRightIcon,
  InfoOutlined as InfoIcon,
  RestartAlt as RestartAltIcon,
} from '@mui/icons-material';

import type { MCPSelectionConfig, MCPServerInfo } from '../../types';
import { apiClient } from '../../services/api';
import { NATIVE_TOOL_NAMES, NATIVE_TOOL_LABELS, NATIVE_TOOL_DESCRIPTIONS, type NativeToolName } from '../../utils/nativeToolsConstants';

interface MCPSelectionProps {
  value: MCPSelectionConfig | undefined;
  onChange: (config: MCPSelectionConfig | undefined) => void;
  disabled?: boolean;
  alertType?: string;  // Optional alert type to load correct defaults
}

/**
 * Deep equality check for MCPSelectionConfig
 */
const configsAreEqual = (a: MCPSelectionConfig | null | undefined, b: MCPSelectionConfig | null | undefined): boolean => {
  if (a === b) return true;
  if (!a || !b) return a === b;
  
  // Compare servers
  if (a.servers.length !== b.servers.length) return false;
  
  const aSorted = [...a.servers].sort((x, y) => x.name.localeCompare(y.name));
  const bSorted = [...b.servers].sort((x, y) => x.name.localeCompare(y.name));
  
  for (let i = 0; i < aSorted.length; i++) {
    if (aSorted[i].name !== bSorted[i].name) return false;
    
    const aTools = aSorted[i].tools;
    const bTools = bSorted[i].tools;
    
    // Both null/undefined = same (all tools selected)
    if (aTools == null && bTools == null) continue;
    // One null/undefined, other is array = different
    if (aTools == null || bTools == null) return false;
    // Both are arrays now - compare them
    if (aTools.length !== bTools.length) return false;
    
    const aToolsSorted = [...aTools].sort();
    const bToolsSorted = [...bTools].sort();
    if (JSON.stringify(aToolsSorted) !== JSON.stringify(bToolsSorted)) return false;
  }
  
  // Compare native_tools
  const aNative = a.native_tools || {};
  const bNative = b.native_tools || {};
  
  return (
    aNative.google_search === bNative.google_search &&
    aNative.code_execution === bNative.code_execution &&
    aNative.url_context === bNative.url_context
  );
};

/**
 * MCPSelection Component
 * 
 * Features:
 * - Loads default configuration from backend
 * - Shows actual configuration state
 * - Detects changes from defaults
 * - Only sends override when changed
 * - Reset to Defaults button
 */
const MCPSelection: React.FC<MCPSelectionProps> = ({ value, onChange, disabled = false, alertType }) => {
  // State for defaults and current config
  const [defaultConfig, setDefaultConfig] = useState<MCPSelectionConfig | null>(null);
  const [currentConfig, setCurrentConfig] = useState<MCPSelectionConfig | null>(null);
  const [hasChanges, setHasChanges] = useState(false);
  
  // State for available servers (for tool details)
  const [availableServers, setAvailableServers] = useState<MCPServerInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // State for UI expansion
  const [expanded, setExpanded] = useState(false);
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());
  const [nativeToolsExpanded, setNativeToolsExpanded] = useState(false);
  
  // Track if component was initialized with a value (e.g., from resubmit)
  const initializedWithValueRef = useRef(value !== undefined);
  
  // Track if defaults have been loaded (to avoid premature onChange calls)
  const defaultsLoadedRef = useRef(false);
  
  // Ref to track the latest alert type
  // Updated whenever alertType prop changes to prevent race conditions
  const latestAlertTypeRef = useRef<string | undefined>(alertType);
  
  // Update ref whenever alertType changes
  useEffect(() => {
    latestAlertTypeRef.current = alertType;
  }, [alertType]);
  
  /**
   * Load defaults and server details for the current alert type
   */
  const loadDefaultsAndServers = useCallback(async () => {
    // Capture the alert type we're requesting for
    const requestAlertType = alertType;
    
    setLoading(true);
    setError(null);
    
    try {
      // Load defaults and servers in parallel
      // Pass alertType to get correct defaults for this alert type's chain
      const [defaults, serversResponse] = await Promise.all([
        apiClient.getDefaultToolsConfig(requestAlertType),
        apiClient.getMCPServers()
      ]);
      
      // Check if alertType changed while we were loading
      // If it did, discard these results (a newer request is active or will fire)
      if (latestAlertTypeRef.current !== requestAlertType) {
        console.debug(`Discarding stale results for alertType="${requestAlertType}"`);
        return;
      }
      
      setDefaultConfig(defaults);
      setAvailableServers(serversResponse.servers);
      
      // Mark that defaults have been loaded
      defaultsLoadedRef.current = true;
      
      // Don't call setCurrentConfig here - let the reconciliation useEffect handle it
      // This preserves incoming value prop overrides
      
      // Reset expanded states when defaults change
      setExpandedServers(new Set());
      setNativeToolsExpanded(false);
    } catch (err: any) {
      // Only set error if this request is still current
      if (latestAlertTypeRef.current === requestAlertType) {
        console.error('Failed to load defaults:', err);
        setError(err.message || 'Failed to load configuration. Please try again.');
      }
    } finally {
      // Always clear loading to prevent stuck state
      setLoading(false);
    }
  }, [alertType]);
  
  // Load defaults and servers on first expansion or when alert type changes
  useEffect(() => {
    if (expanded && !loading && !error) {
      loadDefaultsAndServers();
    }
  }, [expanded, alertType, loadDefaultsAndServers]);
  
  // Reconcile value prop and defaultConfig to set currentConfig
  // Priority: incoming value > defaultConfig > null
  useEffect(() => {
    if (value !== undefined) {
      setCurrentConfig(value);
    } else if (defaultConfig !== null) {
      setCurrentConfig(defaultConfig);
    } else {
      setCurrentConfig(null);
    }
  }, [value, defaultConfig]);
  
  // Detect changes whenever currentConfig changes
  useEffect(() => {
    const changed = !configsAreEqual(currentConfig, defaultConfig);
    setHasChanges(changed);
    
    // Only notify parent after defaults have been loaded at least once
    // This prevents clearing resubmit configs when defaults first load
    if (!defaultsLoadedRef.current) {
      return;
    }
    
    // Notify parent with proper semantics:
    // - undefined = no override, use defaults from agent config
    // - actual config = explicit override (including servers with tools: [])
    //
    // Note: We send the complete config including servers with tools: []
    // The parent/form submission will filter those out before sending to backend
    //
    // Special case: If component was initialized with a value (resubmit), always send
    // the current config, even if it matches defaults. This preserves resubmit configs.
    if (!changed && !initializedWithValueRef.current) {
      // No changes from defaults AND not initialized with value -> don't send override
      onChange(undefined);
    } else {
      // User made changes OR initialized with value -> send the complete override
      onChange(currentConfig || undefined);
    }
  }, [currentConfig, defaultConfig, onChange]);
  
  /**
   * Reset to defaults
   */
  const handleResetToDefaults = () => {
    setCurrentConfig(defaultConfig);
    setExpandedServers(new Set());
    setNativeToolsExpanded(false);
    // Clear the initialized flag so onChange sends undefined (no override)
    initializedWithValueRef.current = false;
  };
  
  /**
   * Normalize tool arrays: preserve semantic meaning
   * - null = all tools from the server
   * - empty array = no tools (server effectively disabled)
   * - array with tools = only those specific tools
   */
  const normalizeServers = (servers: MCPSelectionConfig['servers']): MCPSelectionConfig['servers'] => {
    // No normalization needed - pass through as-is
    return servers;
  };

  /**
   * Handle server selection toggle
   */
  const handleServerToggle = (serverId: string) => {
    if (!currentConfig) return;
    
    const newServers = [...currentConfig.servers];
    const existingIndex = newServers.findIndex(s => s.name === serverId);
    
    if (existingIndex >= 0) {
      // Remove server
      newServers.splice(existingIndex, 1);
      
      // Collapse if expanded
      const newExpanded = new Set(expandedServers);
      newExpanded.delete(serverId);
      setExpandedServers(newExpanded);
    } else {
      // Add server with all tools
      newServers.push({
        name: serverId,
        tools: null  // null = all tools
      });
    }
    
    setCurrentConfig({
      ...currentConfig,
      servers: normalizeServers(newServers)
    });
  };
  
  /**
   * Toggle tool expansion for a server
   */
  const toggleToolExpansion = (serverId: string) => {
    const newExpanded = new Set(expandedServers);
    if (newExpanded.has(serverId)) {
      newExpanded.delete(serverId);
    } else {
      newExpanded.add(serverId);
    }
    setExpandedServers(newExpanded);
  };
  
  /**
   * Handle "All Tools" toggle
   */
  const handleAllToolsToggle = (serverId: string, checked: boolean) => {
    if (!currentConfig) return;
    
    const newServers = currentConfig.servers.map(server => {
      if (server.name === serverId) {
        if (checked) {
          // Checking "All Tools": set to null (all tools from server)
          return {
            ...server,
            tools: null
          };
        } else {
          // Unchecking "All Tools": set to empty array (no tools selected)
          // This gives visual feedback - all individual checkboxes become unchecked
          // User can then check individual tools they want
          return {
            ...server,
            tools: []
          };
        }
      }
      return server;
    });
    
    setCurrentConfig({
      ...currentConfig,
      servers: normalizeServers(newServers)
    });
  };
  
  /**
   * Handle individual tool toggle
   */
  const handleToolToggle = (serverId: string, toolName: string) => {
    if (!currentConfig) return;
    
    const newServers = currentConfig.servers.map(server => {
      if (server.name === serverId) {
        let newTools: string[] | null;
        
        if (server.tools === null) {
          // Was "all tools" - create array with all except this one
          const serverInfo = availableServers.find(s => s.server_id === serverId);
          if (serverInfo) {
            newTools = serverInfo.tools
              .map(t => t.name)
              .filter(t => t !== toolName);
          } else {
            newTools = null;  // No server info, keep as all tools
          }
        } else {
          // Toggle in existing array
          const toolSet = new Set(server.tools);
          if (toolSet.has(toolName)) {
            toolSet.delete(toolName);
          } else {
            toolSet.add(toolName);
          }
          newTools = Array.from(toolSet);
        }
        
        // Allow empty array - user can have server selected with no tools
        // The onChange callback will filter these out when sending to backend
        return { ...server, tools: newTools };
      }
      return server;
    });
    
    setCurrentConfig({
      ...currentConfig,
      servers: normalizeServers(newServers)
    });
  };
  
  /**
   * Handle native tool toggle
   */
  const handleNativeToolToggle = (toolName: NativeToolName) => {
    if (!currentConfig) return;
    
    const currentNativeTools = currentConfig.native_tools || {};
    const newNativeTools = {
      ...currentNativeTools,
      [toolName]: !currentNativeTools[toolName]
    };
    
    setCurrentConfig({
      ...currentConfig,
      native_tools: newNativeTools
    });
  };
  
  /**
   * Check if server is selected
   */
  const isServerSelected = (serverId: string): boolean => {
    return currentConfig?.servers.some(s => s.name === serverId) || false;
  };
  
  /**
   * Check if all tools selected for a server
   */
  const areAllToolsSelected = (serverId: string): boolean => {
    const server = currentConfig?.servers.find(s => s.name === serverId);
    return server?.tools === null;
  };
  
  /**
   * Check if a tool is selected
   */
  const isToolSelected = (serverId: string, toolName: string): boolean => {
    const server = currentConfig?.servers.find(s => s.name === serverId);
    if (!server) return false;
    if (server.tools === null) return true;  // All tools
    if (!server.tools) return false;  // Type guard
    return server.tools.includes(toolName);
  };
  
  /**
   * Check if a server has no tools selected (empty array)
   */
  const hasNoToolsSelected = (serverId: string): boolean => {
    const server = currentConfig?.servers.find(s => s.name === serverId);
    if (!server) return false;
    return Array.isArray(server.tools) && server.tools.length === 0;
  };
  
  /**
   * Get native tool state
   */
  const isNativeToolEnabled = (toolName: NativeToolName): boolean => {
    return currentConfig?.native_tools?.[toolName] || false;
  };
  
  /**
   * Count enabled native tools
   */
  const enabledNativeToolsCount = useMemo(() => {
    return currentConfig?.native_tools 
      ? Object.values(currentConfig.native_tools).filter(Boolean).length 
      : 0;
  }, [currentConfig?.native_tools]);

  return (
    <Box sx={{ px: 4, py: 2 }}>
      <Accordion 
        expanded={expanded}
        onChange={(_, isExpanded) => setExpanded(isExpanded)}
        disabled={disabled}
        sx={{
          boxShadow: expanded ? '0 1px 4px rgba(0, 0, 0, 0.08)' : 'none',
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'rgba(25, 118, 210, 0.04)',
          transition: 'all 0.2s ease-in-out',
          '&:before': { display: 'none' },
          '&:hover': {
            borderColor: 'primary.light',
            bgcolor: 'rgba(25, 118, 210, 0.06)',
          },
        }}
      >
        <AccordionSummary
          expandIcon={<ExpandMoreIcon sx={{ color: 'primary.main' }} />}
          sx={{
            px: 2,
            py: 1.5,
            minHeight: '56px',
            borderRadius: expanded ? '8px 8px 0 0' : '8px',
            bgcolor: 'transparent',
            transition: 'background-color 0.2s ease-in-out',
            '& .MuiAccordionSummary-content': {
              alignItems: 'center',
              gap: 1.5,
            },
            '&:hover': {
              bgcolor: 'rgba(25, 118, 210, 0.06)',
            },
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 36,
              height: 36,
              borderRadius: '8px',
              bgcolor: 'primary.main',
              color: 'white',
            }}
          >
            <SettingsIcon sx={{ fontSize: 20 }} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography 
              variant="subtitle1" 
              sx={{ 
                color: 'primary.main',
                fontWeight: 700,
                fontSize: '0.95rem',
                lineHeight: 1.2,
              }}
            >
              Advanced: Tools Selection
            </Typography>
            <Typography 
              variant="caption" 
              sx={{ 
                color: 'text.secondary',
                fontSize: '0.75rem',
                display: 'block',
                mt: 0.25,
              }}
            >
              Customize tools for this session. Uncheck to use defaults.
            </Typography>
          </Box>
          {/* Status badges */}
          <Stack direction="row" spacing={0.5} sx={{ ml: 1 }}>
            {hasChanges ? (
              <Chip 
                label="Custom"
                size="small"
                color="warning"
                sx={{ 
                  height: 24,
                  fontWeight: 600,
                  '& .MuiChip-label': { px: 1.5 },
                }}
              />
            ) : (
              <Chip 
                label="Default"
                size="small"
                color="success"
                variant="outlined"
                sx={{ 
                  height: 24,
                  fontWeight: 600,
                  '& .MuiChip-label': { px: 1.5 },
                }}
              />
            )}
          </Stack>
        </AccordionSummary>
        
        <AccordionDetails sx={{ px: 2, pt: 2, pb: 2 }}>
          {/* Loading state */}
          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress size={40} />
            </Box>
          )}

          {/* Error state */}
          {error && (
            <MuiAlert 
              severity="error" 
              sx={{ mb: 2, borderRadius: 2 }}
              action={
                <Button color="inherit" size="small" onClick={loadDefaultsAndServers}>
                  Retry
                </Button>
              }
            >
              {error}
            </MuiAlert>
          )}

          {/* Main content */}
          {!loading && !error && defaultConfig && (
            <>
              {/* Info and Reset */}
              <Box sx={{ mb: 3, display: 'flex', gap: 2, alignItems: 'flex-start' }}>
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', flex: 1 }}>
                  <InfoIcon sx={{ color: 'info.main', fontSize: 20, mt: 0.25 }} />
                  <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                    {hasChanges ? (
                      <>
                        <strong style={{ color: '#ed6c02' }}>Custom configuration active.</strong> Your changes will override provider defaults.
                      </>
                    ) : (
                      <>Using provider defaults. Make changes to customize for this session.</>
                    )}
                  </Typography>
                </Box>
                {hasChanges && (
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<RestartAltIcon />}
                    onClick={handleResetToDefaults}
                    disabled={disabled}
                    sx={{
                      textTransform: 'none',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Reset to Defaults
                  </Button>
                )}
              </Box>

              {/* Server cards */}
              <Stack spacing={2}>
                {availableServers.map(server => {
                  const isSelected = isServerSelected(server.server_id);
                  const isToolExpanded = expandedServers.has(server.server_id);
                  const allToolsSelected = areAllToolsSelected(server.server_id);
                  
                  return (
                    <Card 
                      key={server.server_id}
                      elevation={0}
                      sx={{
                        border: '1px solid',
                        borderColor: isSelected ? 'primary.main' : 'divider',
                        borderRadius: 2,
                        bgcolor: isSelected ? 'rgba(25, 118, 210, 0.04)' : 'background.paper',
                        transition: 'all 0.2s',
                      }}
                    >
                      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                        {/* Server header */}
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
                            <FormControlLabel
                              control={
                                <Checkbox
                                  checked={isSelected}
                                  onChange={() => handleServerToggle(server.server_id)}
                                  disabled={disabled}
                                />
                              }
                              label={
                                <Typography variant="body1" sx={{ fontWeight: 600 }}>
                                  {server.server_id}
                                </Typography>
                              }
                              sx={{ m: 0, flex: 1 }}
                            />
                          </Box>
                        </Box>

                        {/* Tool count */}
                        <Typography variant="caption" color="text.secondary" sx={{ ml: 4, display: 'block', mt: 0.5 }}>
                          {server.tools.length} tool{server.tools.length !== 1 ? 's' : ''} available
                        </Typography>

                        {/* Warning when no tools selected */}
                        {isSelected && hasNoToolsSelected(server.server_id) && (
                          <MuiAlert 
                            severity="warning" 
                            sx={{ ml: 4, mt: 1, py: 0.5 }}
                            icon={<InfoIcon fontSize="small" />}
                          >
                            <Typography variant="caption">
                              No tools selected. Select at least one tool, otherwise this MCP server won't be used.
                            </Typography>
                          </MuiAlert>
                        )}

                        {/* Tool selection */}
                        {isSelected && server.tools.length > 0 && (
                          <>
                            <Divider sx={{ my: 1.5, ml: 4 }} />
                            <Button
                              size="small"
                              startIcon={isToolExpanded ? <ExpandMoreIcon /> : <ChevronRightIcon />}
                              onClick={() => toggleToolExpansion(server.server_id)}
                              disabled={disabled}
                              sx={{
                                ml: 4,
                                textTransform: 'none',
                                color: 'primary.main',
                                fontWeight: 600,
                              }}
                            >
                              Select Specific Tools
                            </Button>

                            <Collapse in={isToolExpanded}>
                              <Box 
                                sx={{ 
                                  mt: 2, 
                                  ml: 4,
                                  p: 2, 
                                  bgcolor: 'rgba(0, 0, 0, 0.02)',
                                  borderRadius: 1,
                                  border: '1px solid',
                                  borderColor: 'divider',
                                }}
                              >
                                {/* All tools checkbox */}
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                                  <Checkbox
                                    checked={allToolsSelected}
                                    onChange={(e) => handleAllToolsToggle(server.server_id, e.target.checked)}
                                    disabled={disabled}
                                  />
                                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                    All Tools
                                  </Typography>
                                </Box>

                                <Divider sx={{ mb: 1 }} />

                                {/* Individual tools */}
                                <Stack spacing={0.5} sx={{ maxHeight: 300, overflowY: 'auto' }}>
                                  {server.tools.map(tool => (
                                    <FormControlLabel
                                      key={tool.name}
                                      control={
                                        <Checkbox
                                          checked={isToolSelected(server.server_id, tool.name)}
                                          onChange={() => handleToolToggle(server.server_id, tool.name)}
                                          disabled={disabled}
                                          size="small"
                                        />
                                      }
                                      label={
                                        <Box>
                                          <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                                            {tool.name}
                                          </Typography>
                                          {tool.description && (
                                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                              {tool.description}
                                            </Typography>
                                          )}
                                        </Box>
                                      }
                                      sx={{ m: 0, alignItems: 'flex-start' }}
                                    />
                                  ))}
                                </Stack>
                              </Box>
                            </Collapse>
                          </>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}

                {/* Native Google Tools Section */}
                <Card 
                  elevation={0}
                  sx={{
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    transition: 'all 0.2s',
                  }}
                >
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    {/* Header */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body1" sx={{ fontWeight: 600 }}>
                        Google Native Tools
                      </Typography>
                      <Chip 
                        label="google/gemini"
                        size="small"
                        color="primary"
                        variant="outlined"
                        sx={{ height: 20, fontSize: '0.7rem' }}
                      />
                    </Box>

                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                      {enabledNativeToolsCount} of 3 tools enabled
                    </Typography>

                    {/* Tool selection toggle */}
                    <Divider sx={{ my: 1.5 }} />
                    <Button
                      size="small"
                      startIcon={nativeToolsExpanded ? <ExpandMoreIcon /> : <ChevronRightIcon />}
                      onClick={() => setNativeToolsExpanded(!nativeToolsExpanded)}
                      disabled={disabled}
                      sx={{
                        textTransform: 'none',
                        color: 'primary.main',
                        fontWeight: 600,
                      }}
                    >
                      Configure Tools
                    </Button>

                    <Collapse in={nativeToolsExpanded}>
                      <Box 
                        sx={{ 
                          mt: 2, 
                          p: 2, 
                          bgcolor: 'rgba(0, 0, 0, 0.02)',
                          borderRadius: 1,
                          border: '1px solid',
                          borderColor: 'divider',
                        }}
                      >
                        <Stack spacing={1.5}>
                          <FormControlLabel
                            control={
                              <Checkbox
                                checked={isNativeToolEnabled(NATIVE_TOOL_NAMES.GOOGLE_SEARCH)}
                                onChange={() => handleNativeToolToggle(NATIVE_TOOL_NAMES.GOOGLE_SEARCH)}
                                disabled={disabled}
                                size="small"
                              />
                            }
                            label={
                              <Box>
                                <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                                  {NATIVE_TOOL_LABELS[NATIVE_TOOL_NAMES.GOOGLE_SEARCH]}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  {NATIVE_TOOL_DESCRIPTIONS[NATIVE_TOOL_NAMES.GOOGLE_SEARCH]}
                                </Typography>
                              </Box>
                            }
                            sx={{ m: 0, alignItems: 'flex-start' }}
                          />
                          
                          <FormControlLabel
                            control={
                              <Checkbox
                                checked={isNativeToolEnabled(NATIVE_TOOL_NAMES.CODE_EXECUTION)}
                                onChange={() => handleNativeToolToggle(NATIVE_TOOL_NAMES.CODE_EXECUTION)}
                                disabled={disabled}
                                size="small"
                              />
                            }
                            label={
                              <Box>
                                <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                                  {NATIVE_TOOL_LABELS[NATIVE_TOOL_NAMES.CODE_EXECUTION]}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  {NATIVE_TOOL_DESCRIPTIONS[NATIVE_TOOL_NAMES.CODE_EXECUTION]}
                                </Typography>
                              </Box>
                            }
                            sx={{ m: 0, alignItems: 'flex-start' }}
                          />
                          
                          <FormControlLabel
                            control={
                              <Checkbox
                                checked={isNativeToolEnabled(NATIVE_TOOL_NAMES.URL_CONTEXT)}
                                onChange={() => handleNativeToolToggle(NATIVE_TOOL_NAMES.URL_CONTEXT)}
                                disabled={disabled}
                                size="small"
                              />
                            }
                            label={
                              <Box>
                                <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                                  {NATIVE_TOOL_LABELS[NATIVE_TOOL_NAMES.URL_CONTEXT]}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  {NATIVE_TOOL_DESCRIPTIONS[NATIVE_TOOL_NAMES.URL_CONTEXT]}
                                </Typography>
                              </Box>
                            }
                            sx={{ m: 0, alignItems: 'flex-start' }}
                          />
                        </Stack>
                      </Box>
                    </Collapse>
                  </CardContent>
                </Card>
              </Stack>
            </>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
};

export default MCPSelection;
