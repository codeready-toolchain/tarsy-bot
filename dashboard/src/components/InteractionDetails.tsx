import { memo } from 'react';
import { 
  Box, 
  Typography, 
  Collapse, 
  Divider,
  Stack
} from '@mui/material';
import type { LLMInteraction, MCPInteraction, SystemEvent } from '../types';
import CopyButton from './CopyButton';
import JsonDisplay from './JsonDisplay';

interface InteractionDetailsProps {
  type: 'llm' | 'mcp' | 'system';
  details: LLMInteraction | MCPInteraction | SystemEvent;
  expanded?: boolean;
}

/**
 * InteractionDetails component - Phase 5
 * Expandable detailed view of LLM/MCP interactions with copy functionality
 */
function InteractionDetails({ 
  type, 
  details, 
  expanded = false
}: InteractionDetailsProps) {

  const extractSystemUserFromRequest = (llm: LLMInteraction) => {
    const systemMsg = llm.request_json?.messages?.find((m: any) => m?.role === 'system');
    const userMsg = llm.request_json?.messages?.find((m: any) => m?.role === 'user');
    return {
      system: typeof systemMsg?.content === 'string' ? systemMsg.content : JSON.stringify(systemMsg?.content ?? ''),
      user: typeof userMsg?.content === 'string' ? userMsg.content : JSON.stringify(userMsg?.content ?? ''),
    };
  };

  const extractResponseText = (llm: LLMInteraction) => {
    const choice = llm.response_json?.choices?.[0];
    const content = choice?.message?.content;
    if (typeof content === 'string') return content;
    if (content !== undefined) return JSON.stringify(content);
    return '';
  };

  const renderLLMDetails = (llmDetails: LLMInteraction) => (
    <Stack spacing={2}>
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Prompt
          </Typography>
          <CopyButton
            text={(() => {
              const { system, user } = extractSystemUserFromRequest(llmDetails);
              if (system || user) {
                return `System:\n${system}\n\nUser:\n${user}`;
              }
              return '';
            })()}
            variant="icon"
            size="small"
            tooltip="Copy prompt"
          />
        </Box>
        {(() => {
          const { system, user } = extractSystemUserFromRequest(llmDetails);
          if (system || user) {
            return (
              <Stack spacing={2}>
                {system && (
                  <Box>
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
                          bgcolor: 'secondary.main',
                          color: 'secondary.contrastText',
                          borderRadius: 1,
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          letterSpacing: '0.5px'
                        }}>
                          System
                        </Box>
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                        {system.length.toLocaleString()} chars
                      </Typography>
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
                        maxHeight: 200,
                        overflow: 'auto'
                      }}
                    >
                      {system}
                    </Typography>
                  </Box>
                )}
                {user && (
                  <Box>
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
                          bgcolor: 'primary.main',
                          color: 'primary.contrastText',
                          borderRadius: 1,
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          letterSpacing: '0.5px'
                        }}>
                          User
                        </Box>
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                        {user.length.toLocaleString()} chars
                      </Typography>
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
                        maxHeight: 200,
                        overflow: 'auto'
                      }}
                    >
                      {user}
                    </Typography>
                  </Box>
                )}
              </Stack>
            );
          }
          return null;
        })()}
        </Box>
        
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box sx={{
                px: 1,
                py: 0.5,
                bgcolor: 'success.main',
                color: 'success.contrastText',
                borderRadius: 1,
                fontSize: '0.75rem',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                Response
              </Box>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                {extractResponseText(llmDetails).length.toLocaleString()} chars
              </Typography>
              <CopyButton
                text={extractResponseText(llmDetails)}
                variant="icon"
                size="small"
                tooltip="Copy response"
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
              maxHeight: 300,
              overflow: 'auto'
            }}
          >
            {extractResponseText(llmDetails)}
          </Typography>
      </Box>

      {/* Model metadata */}
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          Model Information
        </Typography>
        <Stack direction="row" spacing={2} flexWrap="wrap">
          <Typography variant="body2" color="text.secondary">
            <strong>Model:</strong> {llmDetails.model_name}
          </Typography>
          {llmDetails.tokens_used && (
            <Typography variant="body2" color="text.secondary">
              <strong>Tokens:</strong> {llmDetails.tokens_used.toLocaleString()}
            </Typography>
          )}
          {llmDetails.temperature !== undefined && (
            <Typography variant="body2" color="text.secondary">
              <strong>Temperature:</strong> {llmDetails.temperature}
            </Typography>
          )}
        </Stack>
      </Box>
    </Stack>
  );

  const renderMCPDetails = (mcpDetails: MCPInteraction) => (
    <Stack spacing={2}>
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
          {Object.keys(mcpDetails.parameters).length > 0 && (
            <JsonDisplay data={mcpDetails.parameters} collapsed={1} />
          )}
        </Box>
      </Box>
      
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Result
          </Typography>
          <CopyButton
            text={JSON.stringify(mcpDetails.result, null, 2)}
            variant="icon"
            size="small"
            tooltip="Copy result"
          />
        </Box>
        <JsonDisplay data={mcpDetails.result} collapsed={1} />
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
          {mcpDetails.execution_time_ms && (
            <Typography variant="body2" color="text.secondary">
              <strong>Execution Time:</strong> {mcpDetails.execution_time_ms}ms
            </Typography>
          )}
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
        // Parse and format LLM messages nicely
        let formatted = '=== LLM INTERACTION ===\n\n';
        
        // New JSON-first formatting
        if (llm.request_json?.messages?.length) {
          const system = llm.request_json.messages.find((m: any) => m?.role === 'system');
          const user = llm.request_json.messages.find((m: any) => m?.role === 'user');
          if (system) {
            const s = typeof system.content === 'string' ? system.content : JSON.stringify(system.content);
            formatted += `SYSTEM:\n${s}\n\n`;
          }
          if (user) {
            const u = typeof user.content === 'string' ? user.content : JSON.stringify(user.content);
            formatted += `USER:\n${u}\n\n`;
          }
        }

        const resp = extractResponseText(llm);
        formatted += `RESPONSE:\n${resp}\n\n`;
        formatted += `MODEL: ${llm.model_name}`;
        if (llm.tokens_used) formatted += ` | TOKENS: ${llm.tokens_used}`;
        if (llm.temperature !== undefined) formatted += ` | TEMPERATURE: ${llm.temperature}`;
        
        return formatted;
      }
      case 'mcp': {
        const mcp = details as MCPInteraction;
        let mcpFormatted = '=== MCP TOOL CALL ===\n\n';
        mcpFormatted += `TOOL: ${mcp.tool_name}\n`;
        mcpFormatted += `SERVER: ${mcp.server_name}\n`;
        if (mcp.execution_time_ms) mcpFormatted += `EXECUTION TIME: ${mcp.execution_time_ms}ms\n`;
        mcpFormatted += `\nPARAMETERS:\n${JSON.stringify(mcp.parameters, null, 2)}\n\n`;
        mcpFormatted += `RESULT:\n${JSON.stringify(mcp.result, null, 2)}`;
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
        const system = llm.request_json?.messages?.find((m: any) => m?.role === 'system');
        const user = llm.request_json?.messages?.find((m: any) => m?.role === 'user');
        const s = system ? (typeof system.content === 'string' ? system.content : JSON.stringify(system.content)) : '';
        const u = user ? (typeof user.content === 'string' ? user.content : JSON.stringify(user.content)) : '';
        const choice = llm.response_json?.choices?.[0];
        const resp = choice?.message?.content ?? '';
        const respStr = typeof resp === 'string' ? resp : JSON.stringify(resp);
        return `${s}${u ? '\n\n' + u : ''}\n\n---\n\n${respStr}`;
      }
      case 'mcp': {
        const mcp = details as MCPInteraction;
        return `${mcp.tool_name}(${JSON.stringify(mcp.parameters, null, 2)})\n\n---\n\n${JSON.stringify(mcp.result, null, 2)}`;
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