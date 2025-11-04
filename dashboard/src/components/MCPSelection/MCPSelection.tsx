/**
 * MCP Server/Tool Selection Component
 * 
 * Allows users to optionally select which MCP servers and specific tools to use
 * for alert processing, overriding default agent configurations.
 */

import { useState, useEffect } from 'react';
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
  Clear as ClearIcon,
  ChevronRight as ChevronRightIcon,
  InfoOutlined as InfoIcon,
} from '@mui/icons-material';

import type { MCPSelectionConfig, MCPServerInfo } from '../../types';
import { apiClient } from '../../services/api';

interface MCPSelectionProps {
  value: MCPSelectionConfig | null;
  onChange: (config: MCPSelectionConfig | null) => void;
  disabled?: boolean;
}

/**
 * MCPSelection Component
 * 
 * Features:
 * - Collapsible "Advanced Options" section
 * - Fetch and display available MCP servers
 * - Allow server selection with checkboxes
 * - Expandable tool selection per server
 * - "All Tools" or specific tool selection
 * - Clear selection button
 */
const MCPSelection: React.FC<MCPSelectionProps> = ({ value, onChange, disabled = false }) => {
  // State for available servers from API
  const [availableServers, setAvailableServers] = useState<MCPServerInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // State for UI expansion
  const [expanded, setExpanded] = useState(false);
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());
  
  // State for selections
  const [selectedServers, setSelectedServers] = useState<Set<string>>(new Set());
  const [serverToolSelections, setServerToolSelections] = useState<Map<string, Set<string> | null>>(new Map());

  // Load available servers on mount
  useEffect(() => {
    if (expanded && availableServers.length === 0 && !loading && !error) {
      loadServers();
    }
  }, [expanded]);

  // Sync internal state with external value
  useEffect(() => {
    if (value && value.servers.length > 0) {
      const newSelectedServers = new Set<string>();
      const newServerToolSelections = new Map<string, Set<string> | null>();
      
      value.servers.forEach(server => {
        newSelectedServers.add(server.name);
        if (server.tools === null || server.tools === undefined) {
          // Null/undefined = all tools explicitly selected
          newServerToolSelections.set(server.name, null);
        } else if (server.tools.length === 0) {
          // Empty array = no tools selected yet (will default to all)
          newServerToolSelections.set(server.name, new Set());
        } else {
          // Specific tools selected
          newServerToolSelections.set(server.name, new Set(server.tools));
        }
      });
      
      setSelectedServers(newSelectedServers);
      setServerToolSelections(newServerToolSelections);
    } else {
      setSelectedServers(new Set());
      setServerToolSelections(new Map());
    }
  }, [value]);

  /**
   * Load available MCP servers from API
   */
  const loadServers = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await apiClient.getMCPServers();
      setAvailableServers(response.servers);
    } catch (err: any) {
      console.error('Failed to load MCP servers:', err);
      setError(err.message || 'Failed to load MCP servers. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Build MCPSelectionConfig from provided state
   * - null = all tools explicitly selected
   * - empty array = no specific tools selected (backend interprets as all tools by default)
   * - array with items = specific tools selected
   */
  const buildMCPConfig = (
    servers: Set<string>,
    toolSelections: Map<string, Set<string> | null>
  ): MCPSelectionConfig | null => {
    if (servers.size === 0) {
      return null;
    }
    
    const serverList = Array.from(servers).map(serverId => {
      const toolSelection = toolSelections.get(serverId);
      
      // Preserve the distinction between null and empty
      let tools: string[] | null = null;
      if (toolSelection === null || toolSelection === undefined) {
        // Explicitly all tools selected (or not set)
        tools = null;
      } else if (toolSelection.size === 0) {
        // No tools selected yet - send empty array (backend will use all tools by default)
        tools = [];
      } else {
        // Specific tools selected
        tools = Array.from(toolSelection);
      }
      
      return {
        name: serverId,
        tools,
      };
    });
    
    return { servers: serverList };
  };

  /**
   * Handle server selection toggle
   */
  const handleServerToggle = (serverId: string) => {
    const newSelectedServers = new Set(selectedServers);
    const newServerToolSelections = new Map(serverToolSelections);
    
    if (newSelectedServers.has(serverId)) {
      // Deselect server
      newSelectedServers.delete(serverId);
      newServerToolSelections.delete(serverId);
      
      // Collapse tool selection if expanded
      const newExpandedServers = new Set(expandedServers);
      newExpandedServers.delete(serverId);
      setExpandedServers(newExpandedServers);
    } else {
      // Select server (default to all tools)
      newSelectedServers.add(serverId);
      // Set to null (all tools)
      newServerToolSelections.set(serverId, null);
    }
    
    // Update state
    setSelectedServers(newSelectedServers);
    setServerToolSelections(newServerToolSelections);
    
    // Update parent with new config (using new state values)
    const newConfig = buildMCPConfig(newSelectedServers, newServerToolSelections);
    onChange(newConfig);
  };

  /**
   * Toggle tool selection expansion for a server
   */
  const toggleToolExpansion = (serverId: string) => {
    const newExpandedServers = new Set(expandedServers);
    
    if (newExpandedServers.has(serverId)) {
      newExpandedServers.delete(serverId);
    } else {
      newExpandedServers.add(serverId);
    }
    
    setExpandedServers(newExpandedServers);
  };

  /**
   * Handle "All Tools" toggle for a server
   * Checked = all tools (null), Unchecked = no tools selected yet (empty set)
   */
  const handleAllToolsToggle = (serverId: string, checked: boolean) => {
    const newServerToolSelections = new Map(serverToolSelections);
    
    if (checked) {
      // Select all tools - set to null
      newServerToolSelections.set(serverId, null);
    } else {
      // Uncheck "All" - start with empty set (user can now select specific tools)
      newServerToolSelections.set(serverId, new Set());
    }
    
    // Update state
    setServerToolSelections(newServerToolSelections);
    
    // Update parent with new config (using new state values)
    const newConfig = buildMCPConfig(selectedServers, newServerToolSelections);
    onChange(newConfig);
  };

  /**
   * Handle individual tool toggle
   */
  const handleToolToggle = (serverId: string, toolName: string) => {
    const newServerToolSelections = new Map(serverToolSelections);
    let toolSet = serverToolSelections.get(serverId);
    
    // If currently null (all tools), create a set with all tools except the one being toggled
    if (toolSet === null) {
      const server = availableServers.find(s => s.server_id === serverId);
      if (server) {
        toolSet = new Set(server.tools.map(t => t.name).filter(t => t !== toolName));
      }
    } else {
      // Toggle the specific tool
      toolSet = new Set(toolSet);
      if (toolSet.has(toolName)) {
        toolSet.delete(toolName);
      } else {
        toolSet.add(toolName);
      }
    }
    
    newServerToolSelections.set(serverId, toolSet);
    
    // Update state
    setServerToolSelections(newServerToolSelections);
    
    // Update parent with new config (using new state values)
    const newConfig = buildMCPConfig(selectedServers, newServerToolSelections);
    onChange(newConfig);
  };

  /**
   * Clear all selections
   */
  const clearSelection = () => {
    setSelectedServers(new Set());
    setServerToolSelections(new Map());
    setExpandedServers(new Set());
    onChange(null);
  };

  /**
   * Check if a specific tool is selected
   */
  const isToolSelected = (serverId: string, toolName: string): boolean => {
    const toolSelection = serverToolSelections.get(serverId);
    
    if (toolSelection === null) {
      // All tools selected
      return true;
    }
    
    return toolSelection?.has(toolName) || false;
  };

  /**
   * Check if all tools are selected for a server
   */
  const areAllToolsSelected = (serverId: string): boolean => {
    const toolSelection = serverToolSelections.get(serverId);
    return toolSelection === null;
  };

  return (
    <Box sx={{ px: 4, py: 2, bgcolor: 'rgba(156, 39, 176, 0.04)' }}>
      <Accordion 
        expanded={expanded}
        onChange={(_, isExpanded) => setExpanded(isExpanded)}
        disabled={disabled}
        sx={{
          boxShadow: 'none',
          '&:before': { display: 'none' },
          bgcolor: 'transparent',
        }}
      >
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          sx={{
            px: 0,
            minHeight: '48px',
            '& .MuiAccordionSummary-content': {
              alignItems: 'center',
              gap: 1,
            },
          }}
        >
          <SettingsIcon sx={{ color: 'primary.main', fontSize: 22 }} />
          <Typography 
            variant="overline" 
            sx={{ 
              color: 'text.secondary',
              fontWeight: 700,
              letterSpacing: 1.2,
              fontSize: '0.8rem',
            }}
          >
            Advanced: MCP Server Selection
          </Typography>
          {selectedServers.size > 0 && (
            <Chip 
              label={`${selectedServers.size} server${selectedServers.size > 1 ? 's' : ''} selected`}
              size="small"
              color="primary"
              sx={{ ml: 1, height: 22 }}
            />
          )}
        </AccordionSummary>
        
        <AccordionDetails sx={{ px: 0, pt: 2 }}>
          {/* Info text */}
          <Box sx={{ mb: 3, display: 'flex', gap: 1, alignItems: 'flex-start' }}>
            <InfoIcon sx={{ color: 'info.main', fontSize: 20, mt: 0.25 }} />
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                Select which MCP servers and tools to use for alert processing.
              </Typography>
              <Typography variant="body2" sx={{ lineHeight: 1.6, mt: 0.5, fontWeight: 500, color: 'primary.main' }}>
                {selectedServers.size === 0 ? (
                  <>💡 No servers selected: Default MCP servers for this alert type will be used.</>
                ) : (
                  <>✓ {selectedServers.size} server{selectedServers.size > 1 ? 's' : ''} configured</>
                )}
              </Typography>
            </Box>
          </Box>

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
                <Button color="inherit" size="small" onClick={loadServers}>
                  Retry
                </Button>
              }
            >
              {error}
            </MuiAlert>
          )}

          {/* No servers available */}
          {!loading && !error && availableServers.length === 0 && (
            <MuiAlert severity="info" sx={{ borderRadius: 2 }}>
              No MCP servers configured. Default agent settings will be used.
            </MuiAlert>
          )}

          {/* Server cards */}
          {!loading && !error && availableServers.length > 0 && (
            <Stack spacing={2}>
              {availableServers.map(server => {
                const isSelected = selectedServers.has(server.server_id);
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
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Typography variant="body1" sx={{ fontWeight: 600 }}>
                                  {server.server_id}
                                </Typography>
                                <Chip 
                                  label={server.server_type}
                                  size="small"
                                  color="primary"
                                  variant="outlined"
                                  sx={{ height: 20, fontSize: '0.7rem' }}
                                />
                              </Box>
                            }
                            sx={{ m: 0, flex: 1 }}
                          />
                        </Box>
                      </Box>

                      {/* Tool count */}
                      <Typography variant="caption" color="text.secondary" sx={{ ml: 4, display: 'block', mt: 0.5 }}>
                        {server.tools.length} tool{server.tools.length !== 1 ? 's' : ''} available
                      </Typography>

                      {/* Tool selection toggle button */}
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

                          {/* Tool selection area */}
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
                              {/* All tools checkbox - inline with label */}
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
                              
                              {/* Show info when no specific tools selected (empty set, not null) */}
                              {(() => {
                                const toolSelection = serverToolSelections.get(server.server_id);
                                const isEmptySet = toolSelection !== null && toolSelection !== undefined && toolSelection.size === 0;
                                return isEmptySet && (
                                  <MuiAlert 
                                    severity="info" 
                                    sx={{ 
                                      mb: 1, 
                                      fontSize: '0.75rem',
                                      py: 0.5,
                                      '& .MuiAlert-icon': {
                                        fontSize: '1rem',
                                      }
                                    }}
                                  >
                                    No specific tools selected - all tools will be used by default
                                  </MuiAlert>
                                );
                              })()}

                              <Divider sx={{ mb: 1 }} />

                              {/* Individual tool checkboxes */}
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

              {/* Clear selection button */}
              {selectedServers.size > 0 && (
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
                  <Button
                    variant="outlined"
                    color="secondary"
                    startIcon={<ClearIcon />}
                    onClick={clearSelection}
                    disabled={disabled}
                    sx={{
                      textTransform: 'none',
                      borderRadius: 1,
                    }}
                  >
                    Clear Selection
                  </Button>
                </Box>
              )}
            </Stack>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
};

export default MCPSelection;

