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

  const renderLLMDetails = (llmDetails: LLMInteraction) => (
    <Stack spacing={2}>
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Prompt
          </Typography>
          <CopyButton
            text={llmDetails.prompt}
            variant="icon"
            size="small"
            tooltip="Copy prompt"
          />
        </Box>
                                                    <JsonDisplay data={llmDetails.prompt} />
        </Box>
        
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Response
            </Typography>
            <CopyButton
              text={llmDetails.response}
              variant="icon"
              size="small"
              tooltip="Copy response"
            />
          </Box>
         <JsonDisplay data={llmDetails.response} />
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
      case 'llm':
        const llm = details as LLMInteraction;
        // Parse and format LLM messages nicely
        let formatted = '=== LLM INTERACTION ===\n\n';
        
        // Try to parse the prompt for structured messages
        const prompt = llm.prompt.trim();
        if (prompt.startsWith('[') && prompt.includes('LLMMessage(') && prompt.includes('role=')) {
          // Parse Python LLMMessage objects
          const messageParts = prompt.split('LLMMessage(').slice(1);
          messageParts.forEach((part) => {
            const roleMatch = part.match(/role='([^']+)'/);
            if (!roleMatch) return;
            
            const role = roleMatch[1];
            const contentStartMatch = part.match(/content='(.*)$/s);
            if (!contentStartMatch) return;
            
            let rawContent = contentStartMatch[1];
            let messageContent = '';
            
            // Parse content character by character (same logic as JsonDisplay)
            let i = 0;
            let escapeNext = false;
            
            while (i < rawContent.length) {
              const char = rawContent[i];
              
              if (escapeNext) {
                messageContent += char;
                escapeNext = false;
              } else if (char === '\\') {
                messageContent += char;
                escapeNext = true;
              } else if (char === "'") {
                const nextChars = rawContent.substring(i + 1, i + 5);
                if (nextChars.startsWith(')') || nextChars.match(/^,\s*[a-zA-Z_]+=/) || i === rawContent.length - 1) {
                  break;
                }
                messageContent += char;
              } else {
                messageContent += char;
              }
              i++;
            }
            
            // Clean up escaped characters
            messageContent = messageContent
              .replace(/\\n/g, '\n')
              .replace(/\\'/g, "'")
              .replace(/\\"/g, '"')
              .replace(/\\\\/g, '\\')
              .replace(/\\t/g, '\t');
            
            formatted += `${role.toUpperCase()} MESSAGE:\n`;
            formatted += `${messageContent}\n\n`;
          });
        } else {
          formatted += `PROMPT:\n${llm.prompt}\n\n`;
        }
        
        formatted += `RESPONSE:\n${llm.response}\n\n`;
        formatted += `MODEL: ${llm.model_name}`;
        if (llm.tokens_used) formatted += ` | TOKENS: ${llm.tokens_used}`;
        if (llm.temperature !== undefined) formatted += ` | TEMPERATURE: ${llm.temperature}`;
        
        return formatted;
        
      case 'mcp':
        const mcp = details as MCPInteraction;
        let mcpFormatted = '=== MCP TOOL CALL ===\n\n';
        mcpFormatted += `TOOL: ${mcp.tool_name}\n`;
        mcpFormatted += `SERVER: ${mcp.server_name}\n`;
        if (mcp.execution_time_ms) mcpFormatted += `EXECUTION TIME: ${mcp.execution_time_ms}ms\n`;
        mcpFormatted += `\nPARAMETERS:\n${JSON.stringify(mcp.parameters, null, 2)}\n\n`;
        mcpFormatted += `RESULT:\n${JSON.stringify(mcp.result, null, 2)}`;
        return mcpFormatted;
        
      case 'system':
        const system = details as SystemEvent;
        let systemFormatted = '=== SYSTEM EVENT ===\n\n';
        systemFormatted += `DESCRIPTION:\n${system.description}`;
        if (system.metadata && Object.keys(system.metadata).length > 0) {
          systemFormatted += `\n\nMETADATA:\n${JSON.stringify(system.metadata, null, 2)}`;
        }
        return systemFormatted;
        
      default:
        return '';
    }
  };

  // Get raw text (original function, renamed for clarity)
  const getRawInteractionText = () => {
    switch (type) {
      case 'llm':
        const llm = details as LLMInteraction;
        return `${llm.prompt}\n\n---\n\n${llm.response}`;
      case 'mcp':
        const mcp = details as MCPInteraction;
        return `${mcp.tool_name}(${JSON.stringify(mcp.parameters, null, 2)})\n\n---\n\n${JSON.stringify(mcp.result, null, 2)}`;
      case 'system':
        const system = details as SystemEvent;
        return `${system.description}${system.metadata ? '\n\n' + JSON.stringify(system.metadata, null, 2) : ''}`;
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