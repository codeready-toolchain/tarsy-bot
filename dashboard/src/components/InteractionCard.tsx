import React from 'react';
import {
  Box,
  Button,
  Card,
  CardHeader,
  CardContent,
  Avatar,
  Typography,
  Chip,
} from '@mui/material';
import { useTheme, alpha } from '@mui/material/styles';
import {
  ExpandMore,
  ExpandLess,
  Psychology,
  Build,
  Settings,
} from '@mui/icons-material';
import type { TimelineItem, InteractionDetail } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import {
  getInteractionColor,
  getInteractionBackgroundColor,
} from '../utils/timelineHelpers';
import { isLLMInteraction, isMCPInteraction } from '../utils/typeGuards';
import LLMInteractionPreview from './LLMInteractionPreview';
import MCPInteractionPreview from './MCPInteractionPreview';
import InteractionDetails from './InteractionDetails';

interface InteractionCardProps {
  interaction: TimelineItem | InteractionDetail;
  isExpanded: boolean;
  onToggle: () => void;
}

// Helper to get interaction icon
const getInteractionIcon = (type: string) => {
  switch (type) {
    case 'llm':
    case 'llm_interaction':
      return <Psychology />;
    case 'mcp':
    case 'mcp_communication':
      return <Build />;
    case 'system':
      return <Settings />;
    default:
      return <Settings />;
  }
};

// Helper to get interaction type styles for LLM interactions
const getInteractionTypeStyle = (interaction: TimelineItem | InteractionDetail) => {
  if (interaction.type !== 'llm') return null;
  
  // Use type guard to safely check if details is an LLMInteraction
  if (!isLLMInteraction(interaction.details)) return null;
  
  const interactionType = interaction.details.interaction_type || 'investigation';
  
  switch (interactionType) {
    case 'summarization':
      return {
        label: 'Summarization',
        color: 'warning' as const,
        borderColor: '2px solid rgba(237, 108, 2, 0.5)',
        hoverBorderColor: '2px solid rgba(237, 108, 2, 0.8)'
      };
    case 'final_analysis':
      return {
        label: 'Final Analysis',
        color: 'success' as const,
        borderColor: '2px solid rgba(46, 125, 50, 0.5)',
        hoverBorderColor: '2px solid rgba(46, 125, 50, 0.8)'
      };
    case 'final_analysis_summary':
      return {
        label: 'Executive Summary',
        color: 'info' as const,
        borderColor: '2px solid rgba(2, 136, 209, 0.5)',
        hoverBorderColor: '2px solid rgba(2, 136, 209, 0.8)'
      };
    case 'investigation':
      return {
        label: 'Investigation',
        color: 'primary' as const,
        borderColor: '2px solid rgba(25, 118, 210, 0.5)',
        hoverBorderColor: '2px solid rgba(25, 118, 210, 0.8)'
      };
    default:
      return null;
  }
};

/**
 * Reusable component for displaying a single interaction (LLM, MCP, or System)
 * Used in stage timelines, session-level interactions, and parallel stage tabs
 */
const InteractionCard: React.FC<InteractionCardProps> = ({
  interaction,
  isExpanded,
  onToggle,
}) => {
  const theme = useTheme();
  const typeStyle = getInteractionTypeStyle(interaction);
  const detailsId = `interaction-details-${interaction.timestamp_us}`;

  // Compute color key once based on typeStyle or interaction type
  const colorKey = typeStyle 
    ? typeStyle.color 
    : interaction.type === 'mcp' 
    ? 'secondary' 
    : 'warning';

  return (
    <Card
      elevation={2}
      sx={{ 
        bgcolor: 'background.paper',
        borderRadius: 2,
        overflow: 'hidden',
        transition: 'all 0.2s ease-in-out',
        border: `2px solid ${alpha(theme.palette[colorKey].main, 0.5)}`,
        '&:hover': {
          elevation: 4,
          transform: 'translateY(-1px)',
          border: `2px solid ${theme.palette[colorKey].dark}`,
        }
      }}
    >
      <CardHeader
        avatar={
          <Avatar
            sx={{
              bgcolor: `${getInteractionColor(interaction.type)}.main`,
              color: 'white',
              width: 40,
              height: 40
            }}
          >
            {getInteractionIcon(interaction.type)}
          </Avatar>
        }
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {interaction.step_description}
            </Typography>
            
            {/* Show interaction type for LLM interactions */}
            {typeStyle && (
              <Chip 
                label={typeStyle.label}
                size="small"
                color={typeStyle.color}
                sx={{ fontSize: '0.7rem', height: 22, fontWeight: 600 }}
              />
            )}
            
            {interaction.duration_ms && (
              <Chip 
                label={formatDurationMs(interaction.duration_ms)} 
                size="small" 
                variant="filled"
                color={getInteractionColor(interaction.type)}
                sx={{ fontSize: '0.75rem', height: 24 }}
              />
            )}
          </Box>
        }
        subheader={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              {formatTimestamp(interaction.timestamp_us, 'short')}
            </Typography>
            <Typography variant="body2" sx={{ color: `${getInteractionColor(interaction.type)}.main`, fontWeight: 500 }}>
              • {interaction.type.toUpperCase()}
            </Typography>
          </Box>
        }
        action={null}
        sx={{ 
          pb: interaction.details && !isExpanded ? 2 : 1,
          bgcolor: getInteractionBackgroundColor(interaction.type)
        }}
      />
          
      {/* Expandable interaction details */}
      {interaction.details && (
        <CardContent sx={{ 
          pt: 2,
          bgcolor: 'background.paper'
        }}>
          {/* Show LLM preview when not expanded */}
          {interaction.type === 'llm' && !isExpanded && isLLMInteraction(interaction.details) && (
            <LLMInteractionPreview 
              interaction={interaction.details}
              showFullPreview={true}
            />
          )}
          
          {/* Show MCP preview when not expanded */}
          {interaction.type === 'mcp' && !isExpanded && isMCPInteraction(interaction.details) && (
            <MCPInteractionPreview 
              interaction={interaction.details}
              showFullPreview={true}
            />
          )}
          
          {/* Expand/Collapse button */}
          <Box sx={{ 
            display: 'flex', 
            justifyContent: 'center', 
            mt: 2,
            mb: 1
          }}>
            <Button
              onClick={onToggle}
              aria-expanded={isExpanded}
              aria-controls={detailsId}
              aria-label={isExpanded ? 'Hide full details' : 'Show full details'}
              sx={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 0.5,
                textTransform: 'none',
                py: 0.75,
                px: 1.5,
                borderRadius: 1,
                bgcolor: alpha(theme.palette[colorKey].main, 0.04),
                border: `1px solid ${alpha(theme.palette[colorKey].main, 0.12)}`,
                '&:hover': { 
                  bgcolor: alpha(theme.palette[colorKey].main, 0.08),
                  border: `1px solid ${alpha(theme.palette[colorKey].main, 0.2)}`,
                  '& .expand-text': {
                    textDecoration: 'underline'
                  }
                },
                transition: 'all 0.2s ease-in-out'
              }}
            >
              <Typography 
                className="expand-text"
                variant="body2" 
                sx={{ 
                  color: theme.palette[colorKey].main,
                  fontWeight: 500,
                  fontSize: '0.875rem'
                }}
              >
                {isExpanded ? 'Show Less' : 'Show Full Details'}
              </Typography>
              <Box sx={{ 
                color: theme.palette[colorKey].main,
                display: 'flex',
                alignItems: 'center'
              }}>
                {isExpanded ? <ExpandLess /> : <ExpandMore />}
              </Box>
            </Button>
          </Box>
          
          {/* Full interaction details when expanded */}
          <Box id={detailsId}>
            <InteractionDetails
              type={interaction.type as 'llm' | 'mcp' | 'system'}
              details={interaction.details}
              expanded={isExpanded}
            />
          </Box>
        </CardContent>
      )}
    </Card>
  );
};

export default InteractionCard;

