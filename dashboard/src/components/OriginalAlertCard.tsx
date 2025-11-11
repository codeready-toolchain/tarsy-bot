import { Paper, Typography, Box, Chip, Link, IconButton, Collapse, alpha } from '@mui/material';
import { AccessTime, OpenInNew, ExpandMore, ExpandLess } from '@mui/icons-material';
import { useState } from 'react';
import type { AlertData } from '../types';
import { renderValue, formatKeyName, sortAlertFields, type RenderableValue } from '../utils/dataRenderer';
import ErrorBoundary from './ErrorBoundary';

export interface OriginalAlertCardProps {
  alertData: AlertData;
}

/**
 * Get severity color for alert severity levels (if severity field exists)
 */
const getSeverityColor = (severity: string): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
  switch (severity.toLowerCase()) {
    case 'critical':
      return 'error';
    case 'high':
      return 'warning';
    case 'medium':
      return 'info';
    case 'low':
      return 'success';
    default:
      return 'default';
  }
};

/**
 * Get environment color for different environments (if environment field exists)
 */
const getEnvironmentColor = (environment: string): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
  switch (environment.toLowerCase()) {
    case 'production':
      return 'error';
    case 'staging':
      return 'warning';
    case 'development':
      return 'info';
    default:
      return 'default';
  }
};

/**
 * Component to render individual field values based on their type
 */
const FieldRenderer: React.FC<{ fieldKey: string; renderedValue: RenderableValue }> = ({ fieldKey, renderedValue }) => {
  const [isExpanded, setIsExpanded] = useState(true); // Start expanded by default

  switch (renderedValue.type) {
    case 'url':
      return (
        <Link
          href={renderedValue.displayValue}
          target="_blank"
          rel="noopener noreferrer"
          sx={(theme) => ({ 
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            backgroundColor: fieldKey === 'runbook' ? alpha(theme.palette.info.main, 0.05) : 'grey.50',
            color: fieldKey === 'runbook' ? 'info.main' : 'text.primary',
            p: 1.5, 
            borderRadius: 1,
            fontSize: '0.875rem',
            fontFamily: 'monospace',
            textDecoration: 'none',
            wordBreak: 'break-word',
            '&:hover': {
              backgroundColor: fieldKey === 'runbook' ? alpha(theme.palette.info.main, 0.1) : 'grey.100',
              textDecoration: 'underline'
            }
          })}
        >
          <OpenInNew fontSize="small" />
          {renderedValue.displayValue}
        </Link>
      );

    case 'json':
      return (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <IconButton
              size="small"
              onClick={() => setIsExpanded(!isExpanded)}
              sx={{ mr: 1 }}
            >
              {isExpanded ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
            <Typography variant="caption" color="text.secondary">
              {isExpanded ? 'Hide JSON' : 'Show JSON'}
            </Typography>
          </Box>
          <Collapse in={isExpanded}>
            <Typography
              component="pre"
              sx={{ 
                backgroundColor: 'grey.50', 
                p: 2, 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.825rem',
                lineHeight: 1.6,
                overflowX: 'auto',
                maxHeight: '300px',
                overflowY: 'auto'
              }}
            >
              {renderedValue.displayValue}
            </Typography>
          </Collapse>
        </Box>
      );

    case 'multiline':
      return (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <IconButton
              size="small"
              onClick={() => setIsExpanded(!isExpanded)}
              sx={{ mr: 1 }}
            >
              {isExpanded ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
            <Typography variant="caption" color="text.secondary">
              {isExpanded ? 'Collapse' : 'Expand'} ({renderedValue.displayValue.split('\n').length} lines)
            </Typography>
          </Box>
          <Collapse in={isExpanded}>
            <Typography
              component="pre"
              sx={{ 
                backgroundColor: 'grey.50', 
                p: 1.5, 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.825rem',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                overflowX: 'auto',
                maxHeight: '500px',
                overflowY: 'auto',
                border: '1px solid',
                borderColor: 'grey.300'
              }}
            >
              {renderedValue.displayValue}
            </Typography>
          </Collapse>
          {!isExpanded && (
            <Typography
              component="pre"
              sx={{ 
                backgroundColor: 'grey.50', 
                p: 1.5, 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.825rem',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                overflowX: 'auto',
                maxHeight: '80px',
                overflowY: 'hidden',
                position: 'relative',
                '&::after': {
                  content: '""',
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: '30px',
                  background: 'linear-gradient(to bottom, transparent, rgba(0,0,0,0.05))'
                }
              }}
            >
              {renderedValue.displayValue.split('\n').slice(0, 3).join('\n')}
            </Typography>
          )}
        </Box>
      );

    case 'timestamp':
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AccessTime fontSize="small" sx={{ color: 'text.secondary' }} />
          <Typography variant="body2" sx={{ 
            fontFamily: 'monospace', 
            fontSize: '0.875rem',
            color: 'text.primary',
            backgroundColor: 'grey.50',
            px: 1.5,
            py: 0.5,
            borderRadius: 1
          }}>
            {renderedValue.displayValue}
          </Typography>
        </Box>
      );

    case 'simple':
    default:
      return (
        <Typography variant="body2" sx={{ 
          fontFamily: fieldKey.includes('id') || fieldKey.includes('hash') ? 'monospace' : 'inherit',
          fontSize: '0.875rem',
          backgroundColor: 'grey.50',
          px: 1,
          py: 0.5,
          borderRadius: 0.5,
          wordBreak: 'break-word'
        }}>
          {renderedValue.displayValue}
        </Typography>
      );
  }
};

/**
 * OriginalAlertCard component - Flexible data support
 * Displays any alert data structure dynamically with proper formatting
 */
function OriginalAlertCard({ alertData }: OriginalAlertCardProps) {
  const [isExpanded, setIsExpanded] = useState(true); // Start expanded by default
  const sortedFields = sortAlertFields(alertData);

  // Extract special fields for header if they exist
  const severity = alertData.severity;
  const environment = alertData.environment;
  const alertType = alertData.alert_type;

  // Count total number of fields
  const fieldCount = sortedFields.length;

  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Original Alert Data
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {fieldCount} {fieldCount === 1 ? 'field' : 'fields'}
          </Typography>
          <IconButton
            size="small"
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label={isExpanded ? 'Collapse alert data' : 'Expand alert data'}
            sx={{ 
              transition: 'transform 0.4s',
              transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)'
            }}
          >
            <ExpandMore />
          </IconButton>
        </Box>
      </Box>
      
      <Collapse in={isExpanded} timeout={400}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {/* Alert Header - Show special fields if they exist */}
          <ErrorBoundary 
            componentName="Alert Header"
            fallback={
              <Typography variant="body2" color="error">
                Error displaying alert header information
              </Typography>
            }
          >
            {(severity || environment || alertType) && (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                  {severity && (
                    <Chip 
                      label={String(severity).toUpperCase()} 
                      color={getSeverityColor(String(severity))} 
                      size="small"
                      sx={{ fontWeight: 600 }}
                    />
                  )}
                  {environment && (
                    <Chip 
                      label={String(environment).toUpperCase()} 
                      color={getEnvironmentColor(String(environment))} 
                      size="small"
                      variant="outlined"
                    />
                  )}
                  {alertType && (
                    <Typography variant="body2" color="text.secondary">
                      {String(alertType)}
                    </Typography>
                  )}
                </Box>
              </Box>
            )}
          </ErrorBoundary>

          {/* Dynamic Fields */}
          <ErrorBoundary 
            componentName="Dynamic Alert Fields"
            fallback={
              <Box sx={{ p: 2, border: '1px dashed', borderColor: 'error.main', borderRadius: 1 }}>
                <Typography variant="body2" color="error" gutterBottom>
                  Error displaying alert data fields
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  The alert data structure may be corrupted or contain invalid content.
                  Raw data: {JSON.stringify(alertData).substring(0, 200)}...
                </Typography>
              </Box>
            }
          >
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {sortedFields.map(([key, value]) => {
                try {
                  const renderedValue = renderValue(value, key);
                  const displayKey = formatKeyName(key);

                  return (
                    <ErrorBoundary 
                      key={key}
                      componentName={`Field: ${key}`}
                      fallback={
                        <Box sx={(theme) => ({ p: 1, bgcolor: alpha(theme.palette.error.main, 0.05), border: '1px solid', borderColor: alpha(theme.palette.error.main, 0.2), borderRadius: 1 })}>
                          <Typography variant="caption" color="error">
                            Error rendering field "{key}": {String(value).substring(0, 100)}
                          </Typography>
                        </Box>
                      }
                    >
                      <Box>
                        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                          {displayKey}
                        </Typography>
                        <FieldRenderer fieldKey={key} renderedValue={renderedValue} />
                      </Box>
                    </ErrorBoundary>
                  );
                } catch (error) {
                  // Fallback for individual field rendering errors
                  return (
                    <Box key={key} sx={{ p: 1, bgcolor: 'warning.50', border: '1px solid', borderColor: 'warning.200', borderRadius: 1 }}>
                      <Typography variant="subtitle2" color="warning.dark" gutterBottom>
                        {formatKeyName(key)} (Rendering Error)
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Failed to render this field. Raw value: {String(value).substring(0, 100)}
                        {String(value).length > 100 && '...'}
                      </Typography>
                    </Box>
                  );
                }
            })}
          </Box>
        </ErrorBoundary>
        </Box>
      </Collapse>
    </Paper>
  );
}

export default OriginalAlertCard;