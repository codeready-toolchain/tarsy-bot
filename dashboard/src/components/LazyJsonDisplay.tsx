import { useState, useMemo, lazy, Suspense, memo } from 'react';
import { 
  Box, 
  Typography, 
  useTheme, 
  Accordion, 
  AccordionSummary, 
  AccordionDetails, 
  Chip, 
  IconButton,
  Button,
  CircularProgress,
  Alert
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import VisibilityIcon from '@mui/icons-material/Visibility';

// Lazy load the heavy JsonView component
const JsonView = lazy(() => import('@uiw/react-json-view'));

interface LazyJsonDisplayProps {
  data: any;
  collapsed?: boolean | number;
  maxHeight?: number;
  maxContentLength?: number; // New prop to control when to use lazy loading
}

interface ParsedContent {
  type: 'json' | 'python-objects' | 'markdown' | 'mixed' | 'plain-text';
  content: any;
  sections?: Array<{
    title: string;
    type: string;
    content: any;
    raw: string;
    size: number; // Add size information
  }>;
}

// Loading skeleton for JSON view
const JsonSkeleton = () => (
  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 2 }}>
    <CircularProgress size={16} />
    <Typography variant="body2" color="text.secondary">
      Loading JSON content...
    </Typography>
  </Box>
);

/**
 * LazyJsonDisplay component - Performance Optimized
 * Only renders heavy JSON content when needed and provides smart truncation
 */
function LazyJsonDisplay({ 
  data, 
  collapsed = true, 
  maxHeight = 400, 
  maxContentLength = 10000 
}: LazyJsonDisplayProps) {
  const theme = useTheme();
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  
  // Calculate content size
  const contentSize = useMemo(() => {
    try {
      const json = JSON.stringify(data);
      if (json === undefined) {
        // JSON.stringify returned undefined, use fallback
        const fallback = String(data);
        return (fallback ?? "").length;
      }
      return json.length;
    } catch (error) {
      // Unserializable data, estimate size from string representation
      const fallback = String(data);
      return (fallback ?? "").length;
    }
  }, [data]);
  
  const isLargeContent = contentSize > maxContentLength;
  
  // Show debug info for large content
  const showDebugInfo = contentSize > 1000;

  // Enhanced content parser with size awareness
  const parsedContent = useMemo((): ParsedContent => {
    if (data === null || data === undefined) {
      return { type: 'plain-text', content: String(data) };
    }

    // For very large content, provide a simpler parsing approach
    if (isLargeContent) {
      return {
        type: 'json',
        content: data,
        sections: [{
          title: 'Large Content',
          type: 'json',
          content: data,
          raw: (() => {
            try {
              const json = JSON.stringify(data);
              return json ?? '[undefined - not serializable]';
            } catch (error) {
              // Provide informative fallback for unserializable data
              const errorMsg = error instanceof Error ? error.message : 'unknown error';
              return `[unserializable data: ${errorMsg}]\n\nFallback representation:\n${String(data).slice(0, 500)}${String(data).length > 500 ? '...' : ''}`;
            }
          })(),
          size: contentSize
        }]
      };
    }

    // Handle MCP results with nested content
    if (typeof data === 'object' && data !== null) {
      if ('result' in data && typeof data.result === 'string') {
        const resultContent = data.result.trim();
        
        if (resultContent.includes('apiVersion:') || 
            resultContent.includes('kind:') || 
            resultContent.includes('metadata:') ||
            (resultContent.includes('\n') && (resultContent.includes(':') || resultContent.includes('-')))) {
          
          return {
            type: 'mixed',
            content: { text: '', sections: [] },
            sections: [{
              title: 'MCP Tool Result (YAML)',
              type: 'yaml',
              content: resultContent,
              raw: resultContent,
              size: resultContent.length
            }]
          };
        }
        
        if (resultContent.length > 50 && (resultContent.includes('\n') || resultContent.includes('\t'))) {
          return {
            type: 'mixed',
            content: { text: '', sections: [] },
            sections: [{
              title: 'MCP Tool Result (Text)',
              type: 'text',
              content: resultContent,
              raw: resultContent,
              size: resultContent.length
            }]
          };
        }
      }
    }

    if (typeof data === 'string') {
      const content = data.trim();
      
      // Check for Python LLM messages
      if (content.startsWith('[') && content.includes('LLMMessage(') && content.includes('role=')) {
        return parsePythonLLMMessages(content);
      }
      
      // Try JSON parsing
      try {
        const parsed = JSON.parse(content);
        if (typeof parsed === 'object') {
          return { type: 'json', content: parsed };
        }
      } catch {
        // Not JSON, continue
      }
      
      // Check for mixed content
      const jsonMatches = content.match(/```json\s*([\s\S]*?)\s*```/g);
      const codeMatches = content.match(/```\w*\s*([\s\S]*?)\s*```/g);
      
      if (jsonMatches || codeMatches || content.includes('##') || content.includes('**')) {
        return parseMixedContent(content);
      }
      
      return { type: 'plain-text', content };
    }

    return { type: 'json', content: data };
  }, [data, isLargeContent, contentSize]);

  // Parse Python LLM messages with size tracking
  const parsePythonLLMMessages = (content: string): ParsedContent => {
    try {
      const messages: Array<{ role: string; content: string; size: number }> = [];
      const messageParts = content.split('LLMMessage(').slice(1);
      
      messageParts.forEach((part) => {
        const roleMatch = part.match(/role='([^']+)'/);
        if (!roleMatch) return;
        
        const role = roleMatch[1];
        const contentStartMatch = part.match(/content='(.*)$/s);
        if (!contentStartMatch) return;
        
        let rawContent = contentStartMatch[1];
        let messageContent = '';
        
        // Parse content (simplified for performance)
        let i = 0;
        let escapeNext = false;
        
        while (i < rawContent.length && i < 50000) { // Limit parsing for performance
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
        
        messages.push({
          role,
          content: messageContent,
          size: messageContent.length
        });
      });

      if (messages.length > 0) {
        const sections = messages.map((msg) => ({
          title: `${msg.role.charAt(0).toUpperCase() + msg.role.slice(1)} Message`,
          type: msg.role === 'system' ? 'system-prompt' : 'user-prompt',
          content: msg.content,
          raw: `Role: ${msg.role}\n\n${msg.content}`,
          size: msg.size
        }));

        return {
          type: 'python-objects',
          content: messages,
          sections
        };
      }
    } catch (error) {
      console.warn('Failed to parse Python LLMMessage objects:', error);
    }

    return { type: 'plain-text', content };
  };

  // Parse mixed content with size tracking
  const parseMixedContent = (content: string): ParsedContent => {
    const sections = [];
    let sectionIndex = 0;

    // Extract JSON code blocks
    const jsonRegex = /```json\s*([\s\S]*?)\s*```/g;
    let jsonMatch;
    while ((jsonMatch = jsonRegex.exec(content)) !== null) {
      try {
        const jsonContent = JSON.parse(jsonMatch[1]);
        sections.push({
          title: `JSON Block ${sectionIndex + 1}`,
          type: 'json',
          content: jsonContent,
          raw: jsonMatch[1],
          size: jsonMatch[1].length
        });
        sectionIndex++;
      } catch {
        // Invalid JSON, skip
      }
    }

    // Extract other code blocks
    const codeRegex = /```(\w*)\s*([\s\S]*?)\s*```/g;
    let codeMatch;
    while ((codeMatch = codeRegex.exec(content)) !== null) {
      if (codeMatch[1] !== 'json') {
        sections.push({
          title: `${codeMatch[1] || 'Code'} Block ${sectionIndex + 1}`,
          type: 'code',
          content: codeMatch[2],
          raw: codeMatch[2],
          size: codeMatch[2].length
        });
        sectionIndex++;
      }
    }

    if (sections.length > 0) {
      return {
        type: 'mixed',
        content: { text: content, sections },
        sections
      };
    }

    return { type: 'plain-text', content };
  };

  const handleSectionExpand = (sectionId: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionId]: !prev[sectionId]
    }));
  };

  // Truncated content display
  const TruncatedContentDisplay = memo(({ content, maxChars = 1000 }: { content: string; maxChars?: number }) => {
    const [showFull, setShowFull] = useState(false);
    const isTruncated = content.length > maxChars;
    const displayContent = showFull || !isTruncated ? content : content.substring(0, maxChars) + '...';

    return (
      <Box>
        <Box 
          component="pre" 
          sx={{ 
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            m: 0,
            p: 2,
            bgcolor: theme.palette.grey[50],
            borderRadius: 1,
            border: `1px solid ${theme.palette.divider}`,
            maxHeight: showFull ? 'none' : Math.min(maxHeight, 400),
            overflow: 'auto',
          }}
        >
          {displayContent}
        </Box>
        {isTruncated && (
          <Box sx={{ mt: 1, display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small"
              onClick={() => setShowFull(!showFull)}
              startIcon={<VisibilityIcon />}
            >
              {showFull ? 'Show Less' : `Show Full Content (+${(content.length - maxChars).toLocaleString()} chars)`}
            </Button>
          </Box>
        )}
      </Box>
    );
  });

  // Lazy JSON renderer
  const LazyJsonRenderer = memo(({ content }: { content: any }) => {
    const [shouldRender, setShouldRender] = useState(!isLargeContent);

    if (!shouldRender) {
      return (
        <Box sx={{ p: 2, textAlign: 'center' }}>
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="body2" gutterBottom>
              Large JSON content ({contentSize.toLocaleString()} characters)
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Click below to render the interactive JSON view. This may take a moment for large content.
            </Typography>
          </Alert>
          <Button
            variant="outlined"
            onClick={() => setShouldRender(true)}
            startIcon={<VisibilityIcon />}
          >
            Render JSON View
          </Button>
        </Box>
      );
    }

    return (
      <Suspense fallback={<JsonSkeleton />}>
        <Box sx={{ 
          '& .w-rjv': {
            backgroundColor: `${theme.palette.grey[50]} !important`,
            borderRadius: theme.shape.borderRadius,
            border: `1px solid ${theme.palette.divider}`,
            fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace !important',
            fontSize: '0.875rem !important',
            maxHeight: maxHeight,
            overflow: 'auto',
          }
        }}>
          <JsonView 
            value={content}
            collapsed={collapsed}
            displayDataTypes={false}
            displayObjectSize={false}
            enableClipboard={false}
            style={{
              backgroundColor: theme.palette.grey[50],
              padding: theme.spacing(2),
            }}
          />
        </Box>
      </Suspense>
    );
  });

  // Render based on content type
  const renderContent = () => {
    switch (parsedContent.type) {
      case 'python-objects':
        return renderPythonObjects(parsedContent);
      case 'mixed':
        return renderMixedContent(parsedContent);
      case 'json':
        return <LazyJsonRenderer content={parsedContent.content} />;
      case 'markdown':
        return <TruncatedContentDisplay content={parsedContent.content} maxChars={2000} />;
      default:
        return <TruncatedContentDisplay content={parsedContent.content} maxChars={1000} />;
    }
  };

  const renderPythonObjects = (parsed: ParsedContent) => (
    <Box>
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Chip label="LLM Messages" size="small" color="primary" variant="outlined" />
        <Typography variant="caption" color="text.secondary">
          {parsed.sections?.length} message{parsed.sections?.length !== 1 ? 's' : ''}
        </Typography>
      </Box>
      
      {parsed.sections?.map((section, index) => {
        const sectionId = section.title;
        const isLargeSection = section.size > 2000;
        
        return (
          <Accordion
            key={index}
            expanded={expandedSections[sectionId] ?? (index === 0 && !isLargeSection)}
            onChange={() => handleSectionExpand(sectionId)}
            sx={{ mb: 1, border: `1px solid ${theme.palette.divider}` }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
                <Chip 
                  label={section.type === 'system-prompt' ? 'System' : 'User'} 
                  size="small" 
                  color={section.type === 'system-prompt' ? 'secondary' : 'primary'}
                  variant="filled"
                />
                <Typography variant="subtitle2" sx={{ flex: 1 }}>
                  {section.title}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                  {section.size.toLocaleString()} chars
                  {isLargeSection && ' (large)'}
                </Typography>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ position: 'relative' }}>
                <TruncatedContentDisplay 
                  content={section.content} 
                  maxChars={isLargeSection ? 3000 : 1500}
                />
                
                <Box sx={{ 
                  position: 'absolute', 
                  top: 8, 
                  right: 8, 
                  zIndex: 1,
                  backgroundColor: 'rgba(255, 255, 255, 0.9)',
                  borderRadius: 1,
                  backdropFilter: 'blur(4px)'
                }}>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigator.clipboard.writeText(section.content);
                    }}
                    sx={{ 
                      p: 0.5,
                      '&:hover': {
                        backgroundColor: theme.palette.primary.main,
                        color: 'white',
                      }
                    }}
                    title={`Copy ${section.type === 'system-prompt' ? 'System' : 'User'} Message`}
                  >
                    <ContentCopyIcon fontSize="small" />
                  </IconButton>
                </Box>
              </Box>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Box>
  );

  const renderMixedContent = (parsed: ParsedContent) => {
    const mainText = typeof parsed.content === 'object' ? parsed.content.text : parsed.content;
    
    return (
      <Box>
        <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Chip label="Mixed Content" size="small" color="info" variant="outlined" />
          <Typography variant="caption" color="text.secondary">
            {parsed.sections?.length} structured block{parsed.sections?.length !== 1 ? 's' : ''}
          </Typography>
        </Box>

        {/* Only show main text if meaningful */}
        {mainText && mainText.length > 50 && (
          <TruncatedContentDisplay content={mainText} maxChars={1000} />
        )}

        {/* Structured sections */}
        {parsed.sections?.map((section, index) => (
          <Accordion
            key={index}
            expanded={expandedSections[section.title] ?? false}
            onChange={() => handleSectionExpand(section.title)}
            sx={{ mb: 1, border: `1px solid ${theme.palette.divider}` }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip 
                  label={section.type.toUpperCase()} 
                  size="small" 
                  color={
                    section.type === 'json' ? 'success' : 
                    section.type === 'yaml' ? 'info' : 
                    'default'
                  }
                  variant="outlined"
                />
                <Typography variant="subtitle2">{section.title}</Typography>
                <Typography variant="caption" color="text.secondary">
                  ({section.size.toLocaleString()} chars)
                </Typography>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ position: 'relative' }}>
                {section.type === 'json' ? (
                  <LazyJsonRenderer content={section.content} />
                ) : (
                  <TruncatedContentDisplay content={section.content} maxChars={2000} />
                )}
                
                <Box sx={{ 
                  position: 'absolute', 
                  top: 8, 
                  right: 8, 
                  zIndex: 1,
                  backgroundColor: 'rgba(255, 255, 255, 0.9)',
                  borderRadius: 1,
                  backdropFilter: 'blur(4px)'
                }}>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigator.clipboard.writeText(section.raw);
                    }}
                    sx={{ 
                      p: 0.5,
                      '&:hover': {
                        backgroundColor: theme.palette.primary.main,
                        color: 'white',
                      }
                    }}
                    title={`Copy ${section.type.toUpperCase()} Content`}
                  >
                    <ContentCopyIcon fontSize="small" />
                  </IconButton>
                </Box>
              </Box>
            </AccordionDetails>
          </Accordion>
        ))}
      </Box>
    );
  };

  return (
    <Box>
      {showDebugInfo && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          Content size: {contentSize.toLocaleString()} characters
          {isLargeContent && ' (large content - optimized rendering)'}
        </Typography>
      )}
      {renderContent()}
    </Box>
  );
}

export default memo(LazyJsonDisplay);
