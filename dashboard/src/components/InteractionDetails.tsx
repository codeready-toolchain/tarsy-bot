import { memo } from 'react';
import { 
  Box, 
  Typography, 
  Collapse, 
  Divider,
  Stack
} from '@mui/material';
import type { LLMInteraction, MCPInteraction, SystemEvent, LLMMessage } from '../types';
import CopyButton from './CopyButton';
import JsonDisplay from './JsonDisplay';
import TokenUsageDisplay from './TokenUsageDisplay';

interface InteractionDetailsProps {
  type: 'llm' | 'mcp' | 'system';
  details: LLMInteraction | MCPInteraction | SystemEvent;
  expanded?: boolean;
}

/**
 * InteractionDetails component
 * Expandable detailed view of LLM/MCP interactions with copy functionality
 */
function InteractionDetails({ 
  type, 
  details, 
  expanded = false
}: InteractionDetailsProps) {

  // Helper function to check if an MCP interaction is a tool list operation
  const isToolList = (mcpDetails: MCPInteraction): boolean => {
    return mcpDetails.communication_type === 'tool_list' || 
           (mcpDetails.communication_type === 'tool_call' && mcpDetails.tool_name === 'list_tools');
  };

  // Helper to get messages array from either new conversation or legacy messages field
  const getMessages = (llm: LLMInteraction): LLMMessage[] => {
    // Try new conversation field first (EP-0014)
    if (llm.conversation?.messages) {
      return llm.conversation.messages;
    }
    // Fall back to legacy messages field for backward compatibility
    if (llm.messages) {
      return llm.messages;
    }
    return [];
  };

  // Function to render all conversation messages in sequence
  const renderConversationMessages = (llm: LLMInteraction) => {
    const messages = getMessages(llm);
    
    if (messages.length === 0) {
      return null;
    }

    // Helper function to get message-specific styling
    const getMessageStyle = (role: string) => {
      switch (role) {
        case 'system':
          return {
            bgcolor: 'secondary.main',
            color: 'secondary.contrastText',
            label: 'System'
          };
        case 'user':
          return {
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            label: 'User'
          };
        case 'assistant':
          return {
            bgcolor: 'success.main',
            color: 'success.contrastText',
            label: 'Assistant'
          };
        default:
          return {
            bgcolor: 'grey.500',
            color: 'common.white',
            label: role.charAt(0).toUpperCase() + role.slice(1)
          };
      }
    };

    return (
      <Stack spacing={2}>
        {messages.map((message, index) => {
          const style = getMessageStyle(message.role);
          const content = typeof message.content === 'string' ? message.content : 
                         (message.content == null || message.content === '') ? '' :
                         JSON.stringify(message.content);
          
          return (
            <Box key={index}>
              <Box sx={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                mb: 1
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{
                    px: 1,
                    py: 0.5,
                    bgcolor: style.bgcolor,
                    color: style.color,
                    borderRadius: 1,
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px'
                  }}>
                    {style.label}
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                    {content.length.toLocaleString()} chars
                  </Typography>
                  <CopyButton
                    text={content}
                    variant="icon"
                    size="small"
                    tooltip={`Copy ${style.label.toLowerCase()} message`}
                  />
                </Box>
              </Box>
              <Typography 
                variant="body2" 
                sx={{ 
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  p: 1.5,
                  bgcolor: 'grey.50',
                  borderRadius: 1,
                  border: 1,
                  borderColor: 'divider',
                  maxHeight: message.role === 'system' ? 200 : (message.role === 'assistant' ? 300 : 200),
                  overflow: 'auto'
                }}
              >
                {content}
              </Typography>
            </Box>
          );
        })}
      </Stack>
    );
  };

  const renderLLMDetails = (llmDetails: LLMInteraction) => {
    // EP-0010: Check if this is a failed interaction
    const isFailed = llmDetails.success === false;
    
    return (
      <Stack spacing={2}>
        {/* Show error section first for failed interactions */}
        {isFailed && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Box sx={{
                  px: 1,
                  py: 0.5,
                  bgcolor: 'error.main',
                  color: 'error.contrastText',
                  borderRadius: 1,
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px'
                }}>
                  Error
                </Box>
              </Box>
              <CopyButton
                text={llmDetails.error_message || 'LLM request failed - no response received'}
                variant="icon"
                size="small"
                tooltip="Copy error message"
              />
            </Box>
            <Typography 
              variant="body2" 
              sx={{ 
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                p: 1.5,
                bgcolor: 'grey.50',
                borderRadius: 1,
                border: 1,
                borderColor: 'error.main',
                color: 'error.main',
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}
            >
              {llmDetails.error_message || 'LLM request failed - no response received'}
            </Typography>
          </Box>
        )}

        {/* EP-0014: Show conversation messages in sequence */}
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Conversation
            </Typography>
            <CopyButton
              text={(() => {
                const messages = getMessages(llmDetails);
                if (messages.length === 0) return '';
                
                let conversation = `=== LLM CONVERSATION ===\n\n`;
                messages.forEach((message) => {
                  const role = message.role.toUpperCase();
                  const content = typeof message.content === 'string' ? message.content : 
                                 (message.content == null || message.content === '') ? '' :
                                 JSON.stringify(message.content);
                  conversation += `${role}:\n${content}\n\n`;
                });
                
                conversation += `--- METADATA ---\n`;
                conversation += `Model: ${llmDetails.model_name}\n`;
                if (llmDetails.total_tokens) {
                  conversation += `Tokens: ${llmDetails.total_tokens.toLocaleString()}\n`;
                }
                if (llmDetails.temperature !== undefined) {
                  conversation += `Temperature: ${llmDetails.temperature}\n`;
                }
                
                return conversation;
              })()}
              variant="icon"
              size="small"
              tooltip="Copy entire conversation"
            />
          </Box>
          {/* Render all conversation messages */}
          {renderConversationMessages(llmDetails)}
        </Box>

      {/* Model metadata */}
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          Model Information
        </Typography>
        <Stack direction="row" spacing={2} flexWrap="wrap" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            <strong>Model:</strong> {llmDetails.model_name}
          </Typography>
          {llmDetails.temperature !== undefined && (
            <Typography variant="body2" color="text.secondary">
              <strong>Temperature:</strong> {llmDetails.temperature}
            </Typography>
          )}
        </Stack>
        
        {/* EP-0009: Compact token usage display for space efficiency */}
        {(llmDetails.total_tokens || llmDetails.input_tokens || llmDetails.output_tokens) && (
          <Box sx={{ mt: 1.5 }}>
            <TokenUsageDisplay
              tokenData={{
                input_tokens: llmDetails.input_tokens,
                output_tokens: llmDetails.output_tokens,
                total_tokens: llmDetails.total_tokens
              }}
              variant="compact"
              size="small"
              showBreakdown={true}
              label="Tokens"
              color="info"
            />
          </Box>
        )}
      </Box>
    </Stack>
  );
};

  const renderMCPDetails = (mcpDetails: MCPInteraction) => (
    <Stack spacing={2}>
      {/* Only show Tool Call section for actual tool calls, not tool lists */}
      {!isToolList(mcpDetails) && (
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Tool Call
            </Typography>
            <CopyButton
              text={`${mcpDetails.tool_name}(${JSON.stringify(mcpDetails.parameters, null, 2)})`}
              variant="icon"
              size="small"
              tooltip="Copy tool call"
            />
          </Box>
          <Box>
            <Typography 
              variant="body2" 
              sx={{ 
                fontFamily: 'monospace', 
                fontSize: '0.875rem',
                fontWeight: 600,
                mb: 1,
                p: 1,
                bgcolor: 'grey.100',
                borderRadius: 1
              }}
            >
              {mcpDetails.tool_name}
            </Typography>
            {mcpDetails.parameters && Object.keys(mcpDetails.parameters).length > 0 && (
              <JsonDisplay data={mcpDetails.parameters} collapsed={1} />
            )}
          </Box>
        </Box>
      )}
      
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              {isToolList(mcpDetails) ? 'Available Tools' : 'Result'}
            </Typography>
            {isToolList(mcpDetails) && mcpDetails.available_tools && (
              <Typography variant="caption" color="text.secondary" sx={{ 
                bgcolor: 'primary.main', 
                color: 'primary.contrastText', 
                px: 1, 
                py: 0.25, 
                borderRadius: 1,
                fontWeight: 600,
                fontSize: '0.75rem'
              }}>
                {(() => {
                  // Count total tools across all servers
                  let totalTools = 0;
                  Object.values(mcpDetails.available_tools).forEach((tools: any) => {
                    if (Array.isArray(tools)) {
                      totalTools += tools.length;
                    }
                  });
                  return `${totalTools} tools`;
                })()}
              </Typography>
            )}
          </Box>
          <CopyButton
            text={JSON.stringify(
              isToolList(mcpDetails)
                ? mcpDetails.available_tools 
                : mcpDetails.result, 
              null, 2
            )}
            variant="icon"
            size="small"
            tooltip={isToolList(mcpDetails) ? 'Copy available tools' : 'Copy result'}
          />
        </Box>
        <JsonDisplay 
          data={isToolList(mcpDetails) ? mcpDetails.available_tools : mcpDetails.result} 
          collapsed={isToolList(mcpDetails) ? false : 1}
          maxHeight={800}
        />
      </Box>

      {/* MCP metadata */}
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          Tool Information
        </Typography>
        <Stack direction="row" spacing={2} flexWrap="wrap">
          <Typography variant="body2" color="text.secondary">
            <strong>Server:</strong> {mcpDetails.server_name}
          </Typography>
          {/* execution_time_ms removed in EP-0010 */}
        </Stack>
      </Box>
    </Stack>
  );

  const renderSystemDetails = (systemDetails: SystemEvent) => (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          Event Description
        </Typography>
        <JsonDisplay data={systemDetails.description} />
      </Box>

      {systemDetails.metadata && Object.keys(systemDetails.metadata).length > 0 && (
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Metadata
            </Typography>
            <CopyButton
              text={JSON.stringify(systemDetails.metadata, null, 2)}
              variant="icon"
              size="small"
              tooltip="Copy metadata"
            />
          </Box>
          <JsonDisplay data={systemDetails.metadata} collapsed={1} />
        </Box>
      )}
    </Stack>
  );

  const renderDetails = () => {
    switch (type) {
      case 'llm':
        return renderLLMDetails(details as LLMInteraction);
      case 'mcp':
        return renderMCPDetails(details as MCPInteraction);
      case 'system':
        return renderSystemDetails(details as SystemEvent);
      default:
        return (
          <Typography variant="body2" color="text.secondary">
            No details available for this interaction type.
          </Typography>
        );
    }
  };

  // Get formatted, human-readable text using the same parsing logic as display
  const getFormattedInteractionText = () => {
    switch (type) {
      case 'llm': {
        const llm = details as LLMInteraction;
        const messages = getMessages(llm);
        let conversation = '=== LLM CONVERSATION ===\n\n';
        messages.forEach((message) => {
          const role = message.role.toUpperCase();
          const content =
            typeof message.content === 'string'
              ? message.content
              : message.content == null || message.content === ''
              ? ''
              : JSON.stringify(message.content);
          conversation += `${role}:\n${content}\n\n`;
        });
        conversation += `MODEL: ${llm.model_name}`;
        if (llm.total_tokens) conversation += ` | TOKENS: ${llm.total_tokens}`;
        if (llm.temperature !== undefined) conversation += ` | TEMPERATURE: ${llm.temperature}`;
        return conversation;
      }
      case 'mcp': {
        const mcp = details as MCPInteraction;
        let mcpFormatted = isToolList(mcp)
          ? '=== MCP TOOL LIST ===\n\n' 
          : '=== MCP TOOL CALL ===\n\n';
        
        if (isToolList(mcp)) {
          mcpFormatted += `SERVER: ${mcp.server_name}\n`;
          // execution_time_ms removed in EP-0010
          mcpFormatted += `\nAVAILABLE TOOLS:\n${JSON.stringify(mcp.available_tools, null, 2)}`;
        } else {
          mcpFormatted += `TOOL: ${mcp.tool_name}\n`;
          mcpFormatted += `SERVER: ${mcp.server_name}\n`;
          // execution_time_ms removed in EP-0010
          mcpFormatted += `\nPARAMETERS:\n${JSON.stringify(mcp.parameters, null, 2)}\n\n`;
          mcpFormatted += `RESULT:\n${JSON.stringify(mcp.result, null, 2)}`;
        }
        return mcpFormatted;
      }
      case 'system': {
        const system = details as SystemEvent;
        let systemFormatted = '=== SYSTEM EVENT ===\n\n';
        systemFormatted += `DESCRIPTION:\n${system.description}`;
        if (system.metadata && Object.keys(system.metadata).length > 0) {
          systemFormatted += `\n\nMETADATA:\n${JSON.stringify(system.metadata, null, 2)}`;
        }
        return systemFormatted;
      }
      default:
        return '';
    }
  };

  // Get raw text (original function, renamed for clarity)
  const getRawInteractionText = () => {
    switch (type) {
      case 'llm': {
        const llm = details as LLMInteraction;
        const messages = getMessages(llm);
        const system = messages.find((m: any) => m?.role === 'system');
        const user = messages.find((m: any) => m?.role === 'user');
        const s = system ? (typeof system.content === 'string' ? system.content : 
                          (system.content == null || system.content === '') ? '' : 
                          JSON.stringify(system.content)) : '';
        const u = user ? (typeof user.content === 'string' ? user.content : 
                         (user.content == null || user.content === '') ? '' : 
                         JSON.stringify(user.content)) : '';
        // Use the same logic as extractResponseText() and formatInteractionForCopy()
        const assistant = messages.find((m: any) => m?.role === 'assistant');
        let respStr = '';
        if (assistant && assistant.content) {
          if (typeof assistant.content === 'string') {
            respStr = assistant.content;
          } else {
            respStr = JSON.stringify(assistant.content);
          }
        }
        return `${s}${u ? '\n\n' + u : ''}${respStr ? '\n\n---\n\n' + respStr : ''}`;
      }
      case 'mcp': {
        const mcp = details as MCPInteraction;
        if (isToolList(mcp)) {
          return `Tool List from ${mcp.server_name}\n\n---\n\n${JSON.stringify(mcp.available_tools, null, 2)}`;
        } else {
          return `${mcp.tool_name}(${JSON.stringify(mcp.parameters, null, 2)})\n\n---\n\n${JSON.stringify(mcp.result, null, 2)}`;
        }
      }
      case 'system': {
        const system = details as SystemEvent;
        return `${system.description}${system.metadata ? '\n\n' + JSON.stringify(system.metadata, null, 2) : ''}`;
      }
      default:
        return '';
    }
  };

  return (
    <Collapse in={expanded}>
      <Box sx={{ pt: 1 }}>
        <Divider sx={{ mb: 2 }} />
        {renderDetails()}
        <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-start' }}>
          <CopyButton
            text={getFormattedInteractionText()}
            size="small"
            label="Copy All Details"
            tooltip="Copy all interaction details in formatted, human-readable format"
          />
          <CopyButton
            text={getRawInteractionText()}
            size="small"
            label="Copy Raw Text"
            tooltip="Copy raw interaction data (unformatted)"
            buttonVariant="text"
          />
        </Box>
      </Box>
    </Collapse>
  );
}

export default memo(InteractionDetails); 