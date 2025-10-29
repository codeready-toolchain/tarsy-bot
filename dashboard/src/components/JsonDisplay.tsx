import JsonView from '@uiw/react-json-view';
import { Box, Typography, useTheme, Accordion, AccordionSummary, AccordionDetails, Chip, IconButton, Tabs, Tab, Button } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UnfoldMoreIcon from '@mui/icons-material/UnfoldMore';
import UnfoldLessIcon from '@mui/icons-material/UnfoldLess';
import { useState } from 'react';

interface JsonDisplayProps {
  data: any;
  collapsed?: boolean | number;
  maxHeight?: number;
}

interface ParsedContent {
  type: 'json' | 'python-objects' | 'markdown' | 'mixed' | 'plain-text';
  content: any;
  sections?: Array<{
    title: string;
    type: string;
    content: any;
    raw: string;
  }>;
}

/**
 * Calculate smart collapse level based on JSON content size
 * Returns more conservative expansion for readability
 */
const calculateSmartCollapseLevel = (
  content: any,
  collapsedProp?: boolean | number
): boolean | number => {
  // Only respect explicit false or numeric values
  // Let true fall through to smart sizing
  if (collapsedProp === false) return false;
  if (typeof collapsedProp === 'number') return collapsedProp;
  
  try {
    const jsonString = JSON.stringify(content);
    const size = jsonString.length;
    
    // More conservative thresholds for better readability
    if (size < 300) return false;      // Fully expand tiny JSON (<300 chars)
    if (size < 1000) return 2;         // Show 2 levels for small JSON
    if (size < 3000) return 1;         // Show 1 level for medium JSON
    return 1; // Collapse to 1 level for large JSON
  } catch {
    return 1; // Default to collapsed
  }
};

/**
 * Calculate smart string truncation based on JSON content size
 * Returns number of chars before truncating strings
 */
const calculateShortenTextAfterLength = (content: any): number => {
  try {
    const jsonString = JSON.stringify(content);
    const size = jsonString.length;
    
    // More aggressive truncation for larger content
    if (size < 500) return 0;          // No truncation for tiny JSON
    if (size < 2000) return 200;       // Truncate at 200 chars for small JSON
    if (size < 5000) return 100;       // Truncate at 100 chars for medium JSON
    return 80;                         // Truncate at 80 chars for large JSON
  } catch {
    return 100; // Default truncation
  }
};

/**
 * JsonDisplay component - Enhanced Phase 5
 * Intelligent content parser with support for JSON, Python objects, and mixed content
 */
function JsonDisplay({ data, collapsed = true, maxHeight = 400 }: JsonDisplayProps) {
  const theme = useTheme();
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab] = useState<number>(0);
  const [isFullyExpanded, setIsFullyExpanded] = useState<boolean>(false);
  
  // Debug info for long content
  const contentLength = typeof data === 'string'
    ? data.length
    : (() => { try { return JSON.stringify(data).length; } catch { return String(data).length; } })();
  const showDebugInfo = contentLength > 1000;

  // Enhanced content parser
  const parseContent = (value: any): ParsedContent => {
    if (value === null || value === undefined) {
      return { type: 'plain-text', content: String(value) };
    }

    // Special handling for MCP results that contain YAML/text/JSON content
    if (typeof value === 'object' && value !== null) {
      // Check if this is an MCP result with a nested text/YAML/JSON result
      if ('result' in value && typeof value.result === 'string') {
        const resultContent = value.result.trim();
        
        // First, try to parse as JSON (most common case)
        try {
          const parsedJson = JSON.parse(resultContent);
          
          // Successfully parsed as JSON
          // Check if it's a nested object with multi-line text fields
          if (typeof parsedJson === 'object' && parsedJson !== null) {
            // Recursively find ALL fields that contain multi-line text
            const multiLineFields: Array<{ path: string; fieldName: string; content: string }> = [];
            
            const findMultiLineFields = (obj: any, path: string[] = []) => {
              if (typeof obj === 'string' && obj.length > 200 && obj.includes('\n')) {
                // Found a multi-line text field
                const fieldName = path[path.length - 1] || 'content';
                const fullPath = path.join(' → ');
                multiLineFields.push({ 
                  path: fullPath, 
                  fieldName, 
                  content: obj 
                });
              } else if (Array.isArray(obj)) {
                // Search through array elements
                obj.forEach((item, index) => {
                  findMultiLineFields(item, [...path, `[${index}]`]);
                });
              } else if (typeof obj === 'object' && obj !== null) {
                // Search through object properties
                for (const [key, value] of Object.entries(obj)) {
                  findMultiLineFields(value, [...path, key]);
                }
              }
            };
            
            findMultiLineFields(parsedJson);
            
            if (multiLineFields.length > 0) {
              // Create sections: First the JSON, then each multi-line field formatted
              const sections = [
                {
                  title: 'MCP Tool Result (JSON)',
                  type: 'json',
                  content: parsedJson,
                  raw: JSON.stringify(parsedJson, null, 2)
                }
              ];
              
              // Add a formatted section for each multi-line field
              for (const { path, fieldName, content } of multiLineFields) {
                // Create a readable title from the path
                const title = path 
                  ? `${fieldName.charAt(0).toUpperCase() + fieldName.slice(1)} (Formatted)`
                  : 'Formatted Text';
                
                sections.push({
                  title,
                  type: 'text',
                  content: content,
                  raw: content
                });
              }
              
              return {
                type: 'mixed',
                content: { text: '', sections: [] },
                sections
              };
            }
            
            // Regular JSON object without special formatting
            return {
              type: 'mixed',
              content: { text: '', sections: [] },
              sections: [
                {
                  title: 'MCP Tool Result (JSON)',
                  type: 'json',
                  content: parsedJson,
                  raw: JSON.stringify(parsedJson, null, 2)
                }
              ]
            };
          }
          
          // Parsed JSON is a simple value (string, number, etc.)
          return {
            type: 'mixed',
            content: { text: '', sections: [] },
            sections: [
              {
                title: 'MCP Tool Result',
                type: 'json',
                content: parsedJson,
                raw: JSON.stringify(parsedJson, null, 2)
              }
            ]
          };
        } catch {
          // Not valid JSON (possibly malformed escape sequences), try other formats
        }
        
        // Check if the result contains YAML content
        if (resultContent.includes('apiVersion:') || 
            resultContent.includes('kind:') || 
            resultContent.includes('metadata:') ||
            resultContent.includes('\n') && (resultContent.includes(':') || resultContent.includes('-'))) {
          
          // This looks like YAML - format it nicely
          return {
            type: 'mixed',
            content: { text: '', sections: [] },
            sections: [
              {
                title: 'MCP Tool Result (YAML)',
                type: 'yaml',
                content: resultContent,
                raw: resultContent
              }
            ]
          };
        }
        
        // Check if it's other structured text content
        if (resultContent.length > 50 && (resultContent.includes('\n') || resultContent.includes('\t'))) {
          return {
            type: 'mixed',
            content: { text: '', sections: [] },
            sections: [
              {
                title: 'MCP Tool Result (Text)',
                type: 'text',
                content: resultContent,
                raw: resultContent
              }
            ]
          };
        }
      }
      
      // Fall through to normal JSON handling for other objects
    }

    if (typeof value === 'string') {
      // Try to detect and parse different content types
      const content = value.trim();
      
      // Check for Python list/object representations
      if (content.startsWith('[') && content.includes('LLMMessage(') && content.includes('role=')) {
        return parsePythonLLMMessages(content);
      }
      
      // Check for pure JSON
      try {
        const parsed = JSON.parse(content);
        if (typeof parsed === 'object') {
          return { type: 'json', content: parsed };
        }
      } catch {
        // Not pure JSON, continue parsing
      }
      
      // Check for mixed content with JSON snippets
      const jsonMatches = content.match(/```json\s*([\s\S]*?)\s*```/g);
      const codeMatches = content.match(/```\w*\s*([\s\S]*?)\s*```/g);
      
      if (jsonMatches || codeMatches || content.includes('##') || content.includes('**')) {
        return parseMixedContent(content);
      }
      
      // Try to parse as JSON one more time for edge cases
      try {
        const parsed = JSON.parse(content);
        return { type: 'json', content: parsed };
      } catch {
        return { type: 'plain-text', content };
      }
    }

    // Handle objects directly
    return { type: 'json', content: value };
  };

  // Parse Python LLMMessage objects
  const parsePythonLLMMessages = (content: string): ParsedContent => {
    try {
      const messages: Array<{ role: string; content: string }> = [];

      // Use a more robust approach: split by LLMMessage and parse each separately
      const messageParts = content.split('LLMMessage(').slice(1); // Remove empty first element
      
      messageParts.forEach((part) => {
        // Find the role
        const roleMatch = part.match(/role='([^']+)'/);
        if (!roleMatch) {
          return;
        }
        
        const role = roleMatch[1];
        
        // For content, we need to be more careful about finding the end
        // Look for content=' and then find the matching closing quote
        const contentStartMatch = part.match(/content='(.*)$/s);
        if (!contentStartMatch) {
          return;
        }
        
        let rawContent = contentStartMatch[1];
        let messageContent = '';
        
        // The content ends when we hit ')' that's not escaped and not inside nested quotes
        // This is tricky, so let's use a character-by-character approach
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
            // This might be the end of the content
            // Look ahead to see if we have ')' or ', ' next
            const nextChars = rawContent.substring(i + 1, i + 5);
            if (nextChars.startsWith(')') || nextChars.match(/^,\s*[a-zA-Z_]+=/) || i === rawContent.length - 1) {
              // This is likely the end of content
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
          content: messageContent
        });
      });

      if (messages.length > 0) {
        const sections = messages.map((msg) => ({
          title: `${msg.role.charAt(0).toUpperCase() + msg.role.slice(1)} Message`,
          type: msg.role === 'system' ? 'system-prompt' : 'user-prompt',
          content: msg.content,
          raw: `Role: ${msg.role}\n\n${msg.content}`
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

  // Parse mixed content with JSON snippets, markdown, etc.
  const parseMixedContent = (content: string): ParsedContent => {
    const sections = [];
    let remainingContent = content;
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
          raw: jsonMatch[1]
        });
        sectionIndex++;
        remainingContent = remainingContent.replace(jsonMatch[0], `[JSON_BLOCK_${sectionIndex}]`);
      } catch {
        // Invalid JSON, skip
      }
    }

    // Extract other code blocks
    const codeRegex = /```(\w*)\s*([\s\S]*?)\s*```/g;
    let codeMatch;
    while ((codeMatch = codeRegex.exec(content)) !== null) {
      if (codeMatch[1] !== 'json') { // Skip JSON blocks (already handled above)
        sections.push({
          title: `${codeMatch[1] || 'Code'} Block ${sectionIndex + 1}`,
          type: 'code',
          content: codeMatch[2],
          raw: codeMatch[2]
        });
        sectionIndex++;
        remainingContent = remainingContent.replace(codeMatch[0], `[CODE_BLOCK_${sectionIndex}]`);
      }
    }

    // If we found structured sections, return mixed content
    if (sections.length > 0) {
      return {
        type: 'mixed',
        content: { text: remainingContent, sections },
        sections
      };
    }

    // Check if it's markdown-like
    if (content.includes('##') || content.includes('**') || content.includes('- ')) {
      return { type: 'markdown', content };
    }

    return { type: 'plain-text', content };
  };

  const handleSectionExpand = (sectionId: string) => {
    setExpandedSections(prev => {
      const current = prev[sectionId] ?? true;
      return { ...prev, [sectionId]: !current };
    });
  };

  const parsedContent = parseContent(data);

  // Check if JSON content is already fully expanded (nothing to collapse/expand)
  const isAlreadyFullyExpanded = (content: any): boolean => {
    try {
      const jsonString = JSON.stringify(content);
      const size = jsonString.length;
      // If content is tiny (<300 chars), it's already fully shown
      // This matches the threshold in calculateSmartCollapseLevel
      return size < 300;
    } catch {
      return false;
    }
  };

  // Determine if expand/collapse is useful (only for JSON content that has something to expand)
  const hasExpandableContent = (() => {
    if (parsedContent.type === 'json') {
      return !isAlreadyFullyExpanded(parsedContent.content);
    }
    if (parsedContent.type === 'mixed' && parsedContent.sections) {
      // Check if any JSON section has something to expand
      return parsedContent.sections.some(s => 
        s.type === 'json' && !isAlreadyFullyExpanded(s.content)
      );
    }
    return false;
  })();

  // Render based on content type
  const renderContent = () => {
    switch (parsedContent.type) {
      case 'python-objects':
        return renderPythonObjects(parsedContent);
      case 'mixed':
        return renderMixedContent(parsedContent);
      case 'json':
        return renderJsonContent(parsedContent.content);
      case 'markdown':
        return renderMarkdownContent(parsedContent.content);
      default:
        return renderPlainText(parsedContent.content);
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
      
      {parsed.sections?.map((section, index) => (
        <Accordion
          key={index}
          expanded={expandedSections[section.title] ?? index === 0}
          onChange={() => handleSectionExpand(section.title)}
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
                {section.content.length.toLocaleString()} chars
              </Typography>
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Box sx={{ position: 'relative' }}>
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
                  maxHeight: section.type === 'user-prompt' ? 400 : 200,
                  overflow: 'auto',
                  // Enhanced scrollbars
                  '&::-webkit-scrollbar': {
                    width: '8px',
                  },
                  '&::-webkit-scrollbar-track': {
                    backgroundColor: theme.palette.grey[100],
                    borderRadius: '4px',
                  },
                  '&::-webkit-scrollbar-thumb': {
                    backgroundColor: theme.palette.grey[400],
                    borderRadius: '4px',
                    '&:hover': {
                      backgroundColor: theme.palette.primary.main,
                    },
                  },
                }}
              >
                {section.content}
              </Box>
              
              {/* Individual Copy Button */}
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
                    const text = typeof section.raw === 'string' ? section.raw : String(section.content);
                    navigator.clipboard?.writeText(text).catch(() => {/* no-op */});
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
      ))}
    </Box>
  );

  const renderMixedContent = (parsed: ParsedContent) => {
    // Clean up the main text by removing placeholder markers
    const cleanMainText = (text: string) => {
      return text
        .replace(/\[JSON_BLOCK_\d+\]/g, '')
        .replace(/\[CODE_BLOCK_\d+\]/g, '')
        .replace(/\n\n+/g, '\n\n') // Remove extra newlines
        .trim();
    };

    const mainText = typeof parsed.content === 'object' ? parsed.content.text : parsed.content;
    const cleanedText = cleanMainText(mainText);

    // Separate sections by type
    const formattedTextSections = parsed.sections?.filter(s => s.type === 'text') || [];
    const rawDataSections = parsed.sections?.filter(s => s.type === 'json' || s.type === 'yaml' || s.type === 'code') || [];
    
    // Determine if we should show tabs (only if there are formatted text sections)
    const shouldShowTabs = formattedTextSections.length > 0;

    // Helper function to render a section accordion
    const renderSectionAccordion = (section: any, index: number) => (
      <Accordion
        key={index}
        expanded={expandedSections[section.title] ?? true}
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
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ position: 'relative' }}>
            {section.type === 'json' ? (
              <JsonView 
                value={section.content}
                collapsed={isFullyExpanded ? false : calculateSmartCollapseLevel(section.content, collapsed)}
                displayDataTypes={false}
                displayObjectSize={false}
                enableClipboard={false}
                shortenTextAfterLength={isFullyExpanded ? 0 : calculateShortenTextAfterLength(section.content)}
                style={{
                  backgroundColor: theme.palette.grey[50],
                  padding: theme.spacing(1),
                  wordBreak: 'break-word',
                  overflowWrap: 'break-word',
                  whiteSpace: 'normal',
                  overflow: 'auto',
                  maxWidth: '100%',
                }}
              />
            ) : (
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
                  maxHeight: section.type === 'yaml' ? 500 : maxHeight / 2,
                  overflow: 'auto',
                  // Enhanced scrollbars for YAML content
                  '&::-webkit-scrollbar': {
                    width: '8px',
                  },
                  '&::-webkit-scrollbar-track': {
                    backgroundColor: theme.palette.grey[100],
                    borderRadius: '4px',
                  },
                  '&::-webkit-scrollbar-thumb': {
                    backgroundColor: theme.palette.grey[400],
                    borderRadius: '4px',
                    '&:hover': {
                      backgroundColor: theme.palette.primary.main,
                    },
                  },
                }}
              >
                {section.content}
              </Box>
            )}
            
            {/* Individual Copy Button for each section */}
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
                  const text = typeof section.raw === 'string' ? section.raw : String(section.content);
                  navigator.clipboard?.writeText(text).catch(() => {/* no-op */});
                }}
                sx={{ 
                  p: 0.5,
                  '&:hover': {
                    backgroundColor: theme.palette.primary.main,
                    color: 'white',
                  }
                }}
                title={`Copy ${section.type === 'yaml' ? 'YAML' : section.type.toUpperCase()} Content`}
              >
                <ContentCopyIcon fontSize="small" />
              </IconButton>
            </Box>
          </Box>
        </AccordionDetails>
      </Accordion>
    );

    // Render without tabs if no formatted text sections
    if (!shouldShowTabs) {
      return (
        <Box>
          <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip label="Mixed Content" size="small" color="info" variant="outlined" />
            <Typography variant="caption" color="text.secondary">
              {parsed.sections?.length} structured block{parsed.sections?.length !== 1 ? 's' : ''}
            </Typography>
          </Box>

          {/* Main text content - only show if there's meaningful content after cleanup */}
          {cleanedText && cleanedText.length > 20 && (
            <Box 
              component="pre" 
              sx={{ 
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                m: 0,
                mb: 2,
                p: 2,
                bgcolor: theme.palette.grey[50],
                borderRadius: 1,
                border: `1px solid ${theme.palette.divider}`,
                maxHeight: maxHeight / 2,
                overflow: 'auto',
              }}
            >
              {cleanedText}
            </Box>
          )}

          {/* All sections as accordions */}
          {parsed.sections?.map((section, index) => renderSectionAccordion(section, index))}
        </Box>
      );
    }

    // Render with tabs when formatted text sections exist
    return (
      <Box>
        <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Chip label="Mixed Content" size="small" color="info" variant="outlined" />
          <Typography variant="caption" color="text.secondary">
            {formattedTextSections.length} formatted • {rawDataSections.length} raw
          </Typography>
        </Box>

        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
          <Tabs 
            value={activeTab} 
            onChange={(_, newValue) => setActiveTab(newValue)}
            aria-label="tool result tabs"
          >
            <Tab label="Formatted Text" id="tab-0" aria-controls="tabpanel-0" />
            <Tab label="Raw Data" id="tab-1" aria-controls="tabpanel-1" />
          </Tabs>
        </Box>

        {/* Tab Panel 0: Formatted Text */}
        <Box
          role="tabpanel"
          hidden={activeTab !== 0}
          id="tabpanel-0"
          aria-labelledby="tab-0"
        >
          {activeTab === 0 && (
            <Box>
              {formattedTextSections.map((section, index) => renderSectionAccordion(section, index))}
            </Box>
          )}
        </Box>

        {/* Tab Panel 1: Raw Data */}
        <Box
          role="tabpanel"
          hidden={activeTab !== 1}
          id="tabpanel-1"
          aria-labelledby="tab-1"
        >
          {activeTab === 1 && (
            <Box>
              {rawDataSections.map((section, index) => renderSectionAccordion(section, index))}
            </Box>
          )}
        </Box>
      </Box>
    );
  };

  const renderJsonContent = (content: any) => {
    const effectiveCollapsed = isFullyExpanded ? false : calculateSmartCollapseLevel(content, collapsed);
    const effectiveShortenText = isFullyExpanded ? 0 : calculateShortenTextAfterLength(content);
    
    return (
      <Box sx={{ 
        maxWidth: '100%',
        overflow: 'hidden',
        '& .w-rjv': {
          backgroundColor: `${theme.palette.grey[50]} !important`,
          borderRadius: theme.shape.borderRadius,
          border: `1px solid ${theme.palette.divider}`,
          fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace !important',
          fontSize: '0.875rem !important',
          maxHeight: maxHeight,
          overflow: 'auto',
          maxWidth: '100%',
          wordBreak: 'break-word',
          overflowWrap: 'break-word',
        }
      }}>
        <JsonView 
          value={content}
          collapsed={effectiveCollapsed}
          displayDataTypes={false}
          displayObjectSize={false}
          enableClipboard={false}
          shortenTextAfterLength={effectiveShortenText}
          style={{
            backgroundColor: theme.palette.grey[50],
            padding: theme.spacing(2),
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
            whiteSpace: 'normal',
            overflow: 'auto',
            maxWidth: '100%',
          }}
        />
      </Box>
    );
  };

  const renderMarkdownContent = (content: string) => (
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
        maxHeight: maxHeight,
        overflow: 'auto',
        '& strong': { fontWeight: 600 },
        '& em': { fontStyle: 'italic' },
      }}
    >
      {content}
    </Box>
  );

  const renderPlainText = (content: string) => (
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
        maxHeight: maxHeight,
        overflow: 'auto',
      }}
    >
      {content}
    </Box>
  );

  return (
    <Box sx={{ 
      maxWidth: '100%',
      overflow: 'hidden',
      wordBreak: 'break-word',
      overflowWrap: 'break-word',
    }}>
      {/* Header with debug info and expand/collapse button */}
      {(showDebugInfo || hasExpandableContent) && (
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          mb: 1,
          gap: 2
        }}>
          {showDebugInfo && (
            <Typography variant="caption" color="text.secondary">
              Content length: {contentLength.toLocaleString()} characters • Scrollable area
            </Typography>
          )}
          {hasExpandableContent && (
            <Box sx={{ marginLeft: 'auto' }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={isFullyExpanded ? <UnfoldLessIcon /> : <UnfoldMoreIcon />}
                onClick={() => setIsFullyExpanded(!isFullyExpanded)}
                sx={{ 
                  textTransform: 'none',
                  fontSize: '0.75rem',
                  py: 0.25,
                  px: 1,
                }}
              >
                {isFullyExpanded ? 'Collapse All' : 'Expand All'}
              </Button>
            </Box>
          )}
        </Box>
      )}
      {renderContent()}
    </Box>
  );
}

export default JsonDisplay; 