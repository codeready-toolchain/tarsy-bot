import JsonView from '@uiw/react-json-view';
import {
  Box,
  Typography,
  useTheme,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  IconButton,
  Tabs,
  Tab,
  Button
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UnfoldMoreIcon from '@mui/icons-material/UnfoldMore';
import UnfoldLessIcon from '@mui/icons-material/UnfoldLess';
import { useState } from 'react';

import type { JsonDisplayProps, ParsedContent } from './types';
import {
  highlightYaml,
  parseContent,
  calculateSmartCollapseLevel,
  calculateShortenTextAfterLength,
  isAlreadyFullyExpanded
} from './utils';

/**
 * JsonDisplay component - Enhanced content display with smart parsing
 * 
 * Features:
 * - Automatically detects and parses JSON, YAML, text, and mixed content
 * - Syntax highlighting for YAML
 * - Smart collapse/expand based on content size
 * - Supports MCP tool results with special formatting
 * - Tab interface for mixed content (formatted vs raw)
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

  const handleSectionExpand = (sectionId: string, expanded: boolean) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionId]: expanded
    }));
  };

  const parsedContent = parseContent(data);

  // Helper to get visible section IDs based on active tab
  const getVisibleSectionIds = (): string[] => {
    if (parsedContent.type !== 'mixed' || !parsedContent.sections) {
      return [];
    }
    
    if (activeTab === 0) {
      // Formatted Text tab: return text sections
      return parsedContent.sections
        .filter(s => s.type === 'text')
        .map(s => s.id);
    } else if (activeTab === 1) {
      // Raw Data tab: return json, yaml, code sections
      return parsedContent.sections
        .filter(s => s.type === 'json' || s.type === 'yaml' || s.type === 'code')
        .map(s => s.id);
    } else {
      // Other tabs: return all section IDs
      return parsedContent.sections.map(s => s.id);
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
          key={section.id ?? index}
          expanded={expandedSections[section.id] ?? (!collapsed || index === 0)}
          onChange={(_, expanded) => handleSectionExpand(section.id, expanded)}
          sx={{ mb: 1, border: `1px solid ${theme.palette.divider}` }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
              <Chip 
                label={
                  section.type === 'system-prompt' ? 'System' : 
                  section.type === 'assistant-prompt' ? 'Assistant' : 
                  'User'
                } 
                size="small" 
                color={
                  section.type === 'system-prompt' ? 'secondary' : 
                  section.type === 'assistant-prompt' ? 'success' : 
                  'primary'
                }
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
                  maxHeight: 
                    section.type === 'user-prompt' ? 400 : 
                    section.type === 'assistant-prompt' ? 600 : 
                    200,
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
                  title={`Copy ${
                    section.type === 'system-prompt' ? 'System' : 
                    section.type === 'assistant-prompt' ? 'Assistant' : 
                    'User'
                  } Message`}
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
        key={section.id ?? index}
        expanded={expandedSections[section.id] ?? !collapsed}
        onChange={(_, expanded) => handleSectionExpand(section.id, expanded)}
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
            ) : section.type === 'yaml' ? (
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
                  maxHeight: 600,
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
                dangerouslySetInnerHTML={{ __html: highlightYaml(section.content) }}
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
                  maxHeight: 600,
                  overflow: 'auto',
                  // Enhanced scrollbars for text content
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
                onClick={() => {
                  const newExpandedState = !isFullyExpanded;
                  setIsFullyExpanded(newExpandedState);
                  
                  // Also toggle visible accordions based on active tab
                  const visibleSectionIds = getVisibleSectionIds();
                  if (visibleSectionIds.length > 0) {
                    setExpandedSections(prev => {
                      const updated = { ...prev };
                      if (newExpandedState) {
                        // Expanding: add visible section IDs
                        visibleSectionIds.forEach(id => {
                          updated[id] = true;
                        });
                      } else {
                        // Collapsing: remove visible section IDs, preserve others
                        visibleSectionIds.forEach(id => {
                          delete updated[id];
                        });
                      }
                      return updated;
                    });
                  }
                }}
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
