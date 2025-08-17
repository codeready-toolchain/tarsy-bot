import React, { useState, lazy, Suspense, memo } from 'react';
import { 
  Box, 
  Typography, 
  Collapse, 
  Divider,
  Stack,
  CircularProgress,
  Alert,
  Skeleton
} from '@mui/material';
import type { LLMInteraction, MCPInteraction, SystemEvent } from '../types';

// Lazy load the heavy components
const CopyButton = lazy(() => import('./CopyButton'));
const LazyJsonDisplay = lazy(() => import('./LazyJsonDisplay'));

interface LazyInteractionDetailsProps {
  type: 'llm' | 'mcp' | 'system';
  details: LLMInteraction | MCPInteraction | SystemEvent;
  expanded?: boolean;
}

// Enhanced loading fallback component with glowing skeleton effect
const DetailsSkeleton = ({ type = 'llm' }: { type?: 'llm' | 'mcp' | 'system' }) => (
  <Box sx={{ p: 2 }}>
    {/* Loading indicator with text */}
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
      <CircularProgress size={16} />
      <Typography variant="body2" color="text.secondary">
        Loading interaction details...
      </Typography>
    </Box>
    
    {/* Skeleton structure based on interaction type */}
    <Stack spacing={2}>
      {type === 'llm' && (
        <>
          {/* System section skeleton */}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Skeleton variant="rectangular" width={60} height={20} sx={{ borderRadius: 1 }} />
              <Skeleton variant="text" width={80} height={16} />
            </Box>
            <Skeleton variant="rectangular" width="100%" height={120} sx={{ borderRadius: 1 }} />
          </Box>
          
          {/* User section skeleton */}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Skeleton variant="rectangular" width={45} height={20} sx={{ borderRadius: 1 }} />
              <Skeleton variant="text" width={80} height={16} />
            </Box>
            <Skeleton variant="rectangular" width="100%" height={80} sx={{ borderRadius: 1 }} />
          </Box>
          
          {/* Response section skeleton */}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Skeleton variant="rectangular" width={70} height={20} sx={{ borderRadius: 1 }} />
              <Skeleton variant="text" width={90} height={16} />
            </Box>
            <Skeleton variant="rectangular" width="100%" height={200} sx={{ borderRadius: 1 }} />
          </Box>
          
          {/* Model metadata skeleton */}
          <Box>
            <Skeleton variant="text" width={150} height={20} sx={{ mb: 1 }} />
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <Skeleton variant="text" width={120} height={16} />
              <Skeleton variant="text" width={100} height={16} />
              <Skeleton variant="text" width={90} height={16} />
            </Box>
          </Box>
        </>
      )}
      
      {type === 'mcp' && (
        <>
          {/* Tool call skeleton */}
          <Box>
            <Skeleton variant="text" width={100} height={20} sx={{ mb: 1 }} />
            <Skeleton variant="text" width={150} height={16} sx={{ mb: 1 }} />
            <Skeleton variant="rectangular" width="100%" height={100} sx={{ borderRadius: 1 }} />
          </Box>
          
          {/* Result skeleton */}
          <Box>
            <Skeleton variant="text" width={80} height={20} sx={{ mb: 1 }} />
            <Skeleton variant="rectangular" width="100%" height={150} sx={{ borderRadius: 1 }} />
          </Box>
          
          {/* Tool metadata skeleton */}
          <Box>
            <Skeleton variant="text" width={130} height={20} sx={{ mb: 1 }} />
            <Skeleton variant="text" width={180} height={16} />
          </Box>
        </>
      )}
      
      {type === 'system' && (
        <>
          {/* Event description skeleton */}
          <Box>
            <Skeleton variant="text" width={140} height={20} sx={{ mb: 1 }} />
            <Skeleton variant="rectangular" width="100%" height={100} sx={{ borderRadius: 1 }} />
          </Box>
          
          {/* Metadata skeleton */}
          <Box>
            <Skeleton variant="text" width={100} height={20} sx={{ mb: 1 }} />
            <Skeleton variant="rectangular" width="100%" height={80} sx={{ borderRadius: 1 }} />
          </Box>
        </>
      )}
      
      {/* Copy buttons skeleton */}
      <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-start' }}>
        <Skeleton variant="rectangular" width={120} height={32} sx={{ borderRadius: 1 }} />
        <Skeleton variant="rectangular" width={100} height={32} sx={{ borderRadius: 1 }} />
      </Box>
    </Stack>
  </Box>
);

// Error boundary component
const DetailsErrorFallback = ({ error }: { error: Error }) => (
  <Alert severity="warning" sx={{ m: 1 }}>
    <Typography variant="body2">
      Failed to load interaction details: {error.message}
    </Typography>
  </Alert>
);

/**
 * LazyInteractionDetails component - Performance Optimized
 * Only renders and processes content when expanded to improve performance
 */
function LazyInteractionDetails({ 
  type, 
  details, 
  expanded = false
}: LazyInteractionDetailsProps) {
  const [hasBeenExpanded, setHasBeenExpanded] = useState(false);
  // Track loading state to ensure skeleton shows for minimum duration
  const [isLoading, setIsLoading] = useState(false);
  const [showContent, setShowContent] = useState(false);

  // Track if this component has ever been expanded to avoid re-processing
  React.useEffect(() => {
    if (expanded && !hasBeenExpanded) {
      setHasBeenExpanded(true);
      setIsLoading(true);
      setShowContent(false);
      
      // Ensure skeleton shows for at least 300ms for better UX
      const timer = setTimeout(() => {
        setShowContent(true);
        setIsLoading(false);
      }, 300);
      
      return () => clearTimeout(timer);
    } else if (expanded && hasBeenExpanded) {
      // If already expanded before, show content immediately
      setShowContent(true);
      setIsLoading(false);
    }
  }, [expanded, hasBeenExpanded]);

  // Don't process any content until expanded
  if (!expanded && !hasBeenExpanded) {
    return (
      <Collapse in={false}>
        <Box sx={{ pt: 1 }}>
          <Divider sx={{ mb: 2 }} />
          <DetailsSkeleton type={type} />
        </Box>
      </Collapse>
    );
  }

  return (
    <Collapse in={expanded}>
      <Box sx={{ pt: 2 }}>
        {(isLoading || !showContent) ? (
          <DetailsSkeleton type={type} />
        ) : (
          <Suspense fallback={<DetailsSkeleton type={type} />}>
            <LazyDetailsRenderer
              type={type}
              details={details}
            />
          </Suspense>
        )}
      </Box>
    </Collapse>
  );
}

// Separate component for the actual details rendering
const LazyDetailsRenderer = memo(({ 
  type, 
  details
}: Omit<LazyInteractionDetailsProps, 'expanded'>) => {
  // Helper functions (same as original)
  const extractSystemUserFromRequest = (llm: LLMInteraction) => {
    const systemMsg = llm.messages?.find((m: any) => m?.role === 'system');
    const userMsg = llm.messages?.find((m: any) => m?.role === 'user');
    return {
      system: typeof systemMsg?.content === 'string' ? systemMsg.content : 
              (systemMsg?.content == null || systemMsg?.content === '') ? '' : 
              JSON.stringify(systemMsg.content),
      user: typeof userMsg?.content === 'string' ? userMsg.content : 
            (userMsg?.content == null || userMsg?.content === '') ? '' : 
            JSON.stringify(userMsg.content),
    };
  };

  const extractResponseText = (llm: LLMInteraction) => {
    const assistantMsg = llm.messages?.find((m: any) => m?.role === 'assistant');
    if (assistantMsg && assistantMsg.content) {
      if (typeof assistantMsg.content === 'string') return assistantMsg.content;
      return JSON.stringify(assistantMsg.content);
    }
    return '';
  };

  const isToolList = (mcpDetails: MCPInteraction): boolean => {
    return mcpDetails.communication_type === 'tool_list' || 
           (mcpDetails.communication_type === 'tool_call' && mcpDetails.tool_name === 'list_tools');
  };



  const renderLLMDetails = (llmDetails: LLMInteraction) => {
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
              <Suspense fallback={<CircularProgress size={16} />}>
                <CopyButton
                  text={llmDetails.error_message || 'LLM request failed - no response received'}
                  variant="icon"
                  size="small"
                  tooltip="Copy error message"
                />
              </Suspense>
            </Box>
            <Typography 
              variant="body2" 
              sx={{ 
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                p: 1.5,
                bgcolor: 'error.50',
                borderRadius: 1,
                color: 'error.main',
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                maxHeight: 200,
                overflow: 'auto'
              }}
            >
              {llmDetails.error_message || 'LLM request failed - no response received'}
            </Typography>
          </Box>
        )}

        {/* System and User prompts as separate sections */}
        {(() => {
          const { system, user } = extractSystemUserFromRequest(llmDetails);
          if (system || user) {
            return (
              <Stack spacing={2}>
                {system && (
                  <Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
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
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                          {system.length.toLocaleString()} chars
                        </Typography>
                        <Suspense fallback={<CircularProgress size={16} />}>
                          <CopyButton
                            text={system}
                            variant="icon"
                            size="small"
                            tooltip="Copy system prompt"
                          />
                        </Suspense>
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
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
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
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                          {user.length.toLocaleString()} chars
                        </Typography>
                        <Suspense fallback={<CircularProgress size={16} />}>
                          <CopyButton
                            text={user}
                            variant="icon"
                            size="small"
                            tooltip="Copy user prompt"
                          />
                        </Suspense>
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
        
        {/* Response section (only for successful interactions) */}
        {!isFailed && (() => {
          const responseText = extractResponseText(llmDetails);
          if (responseText) {
            return (
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
                      {responseText.length.toLocaleString()} chars
                    </Typography>
                    <Suspense fallback={<CircularProgress size={16} />}>
                      <CopyButton
                        text={responseText}
                        variant="icon"
                        size="small"
                        tooltip="Copy response"
                      />
                    </Suspense>
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
                    maxHeight: 300,
                    overflow: 'auto'
                  }}
                >
                  {responseText}
                </Typography>
              </Box>
            );
          }
        })()}

        {/* Model metadata */}
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
            Model Information
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            <Typography variant="body2" color="text.secondary">
              <strong>Model:</strong> {llmDetails.model_name}
            </Typography>
            {llmDetails.total_tokens && (
              <Typography variant="body2" color="text.secondary">
                <strong>Tokens:</strong> {llmDetails.total_tokens.toLocaleString()}
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
  };

  const renderMCPDetails = (mcpDetails: MCPInteraction) => (
    <Stack spacing={2}>
      {/* Tool Call section */}
      {!isToolList(mcpDetails) && (
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Tool Call
            </Typography>
            <Suspense fallback={<CircularProgress size={16} />}>
              <CopyButton
                text={`${mcpDetails.tool_name}(${JSON.stringify(mcpDetails.parameters, null, 2)})`}
                variant="icon"
                size="small"
                tooltip="Copy tool call"
              />
            </Suspense>
          </Box>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 1 }}>
            {mcpDetails.tool_name}
          </Typography>
          {mcpDetails.parameters && Object.keys(mcpDetails.parameters).length > 0 && (
            <Suspense fallback={<CircularProgress size={20} />}>
              <LazyJsonDisplay data={mcpDetails.parameters} collapsed={1} maxHeight={400} />
            </Suspense>
          )}
        </Box>
      )}
      
      {/* Result section with lazy loading */}
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            {isToolList(mcpDetails) ? 'Available Tools' : 'Result'}
          </Typography>
          <Suspense fallback={<CircularProgress size={16} />}>
            <CopyButton
              text={JSON.stringify(
                isToolList(mcpDetails) ? mcpDetails.available_tools : mcpDetails.result, 
                null, 2
              )}
              variant="icon"
              size="small"
              tooltip={isToolList(mcpDetails) ? 'Copy available tools' : 'Copy result'}
            />
          </Suspense>
        </Box>
        <Suspense fallback={<CircularProgress size={20} />}>
          <LazyJsonDisplay 
            data={isToolList(mcpDetails) ? mcpDetails.available_tools : mcpDetails.result} 
            collapsed={isToolList(mcpDetails) ? false : 1}
            maxHeight={600}
          />
        </Suspense>
      </Box>

      {/* MCP metadata */}
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          Tool Information
        </Typography>
        <Typography variant="body2" color="text.secondary">
          <strong>Server:</strong> {mcpDetails.server_name}
        </Typography>
      </Box>
    </Stack>
  );

  const renderSystemDetails = (systemDetails: SystemEvent) => (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
          Event Description
        </Typography>
        <Typography 
          variant="body2" 
          sx={{ 
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            p: 1.5,
            bgcolor: 'grey.50',
            borderRadius: 1,
            maxHeight: 200,
            overflow: 'auto'
          }}
        >
          {typeof systemDetails.description === 'string' ? systemDetails.description : JSON.stringify(systemDetails.description)}
        </Typography>
      </Box>

      {systemDetails.metadata && Object.keys(systemDetails.metadata).length > 0 && (
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Metadata
            </Typography>
            <Suspense fallback={<CircularProgress size={16} />}>
              <CopyButton
                text={JSON.stringify(systemDetails.metadata, null, 2)}
                variant="icon"
                size="small"
                tooltip="Copy metadata"
              />
            </Suspense>
          </Box>
          <Suspense fallback={<CircularProgress size={20} />}>
            <LazyJsonDisplay data={systemDetails.metadata} collapsed={1} />
          </Suspense>
        </Box>
      )}
    </Stack>
  );

  const renderDetails = () => {
    try {
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
    } catch (error) {
      return <DetailsErrorFallback error={error as Error} />;
    }
  };

  // Create formatted text for copying based on interaction type
  const getFormattedCopyText = () => {
    switch (type) {
      case 'llm': {
        const llmDetails = details as LLMInteraction;
        const { system, user } = extractSystemUserFromRequest(llmDetails);
        const responseText = extractResponseText(llmDetails);
        
        let conversation = `=== LLM CONVERSATION ===\n\n`;
        
        if (system) {
          conversation += `SYSTEM:\n${system}\n\n`;
        }
        
        if (user) {
          conversation += `USER:\n${user}\n\n`;
        }
        
        if (llmDetails.success === false) {
          conversation += `ERROR:\n${llmDetails.error_message || 'LLM request failed - no response received'}\n\n`;
        } else if (responseText) {
          conversation += `ASSISTANT:\n${responseText}\n\n`;
        }
        
        conversation += `--- METADATA ---\n`;
        conversation += `Model: ${llmDetails.model_name}\n`;
        if (llmDetails.total_tokens) {
          conversation += `Tokens: ${llmDetails.total_tokens.toLocaleString()}\n`;
        }
        if (llmDetails.temperature !== undefined) {
          conversation += `Temperature: ${llmDetails.temperature}\n`;
        }
        
        return conversation;
      }
        
      case 'mcp': {
        const mcpDetails = details as MCPInteraction;
        let mcpText = `=== MCP INTERACTION ===\n\n`;
        mcpText += `TOOL: ${mcpDetails.tool_name || 'Unknown'}\n\n`;
        
        if (mcpDetails.parameters && Object.keys(mcpDetails.parameters).length > 0) {
          mcpText += `PARAMETERS:\n${JSON.stringify(mcpDetails.parameters, null, 2)}\n\n`;
        }
        
        if (mcpDetails.result) {
          mcpText += `RESULT:\n${typeof mcpDetails.result === 'string' ? mcpDetails.result : JSON.stringify(mcpDetails.result, null, 2)}\n\n`;
        }
        
        mcpText += `--- METADATA ---\n`;
        mcpText += `Server: ${mcpDetails.server_name}\n`;
        mcpText += `Communication Type: ${mcpDetails.communication_type}\n`;
        mcpText += `Success: ${mcpDetails.success}\n`;
        
        return mcpText;
      }
        
      case 'system': {
        const systemDetails = details as SystemEvent;
        let systemText = `=== SYSTEM EVENT ===\n\n`;
        systemText += `DESCRIPTION:\n${typeof systemDetails.description === 'string' ? systemDetails.description : JSON.stringify(systemDetails.description)}\n\n`;
        
        if (systemDetails.metadata && Object.keys(systemDetails.metadata).length > 0) {
          systemText += `METADATA:\n${JSON.stringify(systemDetails.metadata, null, 2)}\n`;
        }
        
        return systemText;
      }
        
      default: {
        return `=== ${(type as string).toUpperCase()} INTERACTION ===\n\n${JSON.stringify(details, null, 2)}`;
      }
    }
  };

  return (
    <>
      {renderDetails()}
      <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-start' }}>
        <Suspense fallback={<CircularProgress size={20} />}>
          <CopyButton
            text={getFormattedCopyText()}
            size="small"
            label={type === 'llm' ? "Copy Conversation" : "Copy All Details"}
            tooltip={type === 'llm' ? "Copy full conversation (prompts + response)" : "Copy all interaction details"}
          />
        </Suspense>
        <Suspense fallback={<CircularProgress size={20} />}>
          <CopyButton
            text={JSON.stringify(details, null, 2)}
            size="small"
            label="Copy Raw Text"
            tooltip="Copy raw interaction data (unformatted JSON)"
            buttonVariant="text"
          />
        </Suspense>
      </Box>
    </>
  );
});

export default memo(LazyInteractionDetails);
