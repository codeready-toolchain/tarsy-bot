import React from 'react';
import {
  Box,
  Card,
  CardHeader,
  CardContent,
  Avatar,
  Typography,
  Chip,
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  Psychology,
  Build,
  Settings,
} from '@mui/icons-material';
import type { TimelineItem, LLMInteraction, MCPInteraction, InteractionDetail } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import {
  getInteractionColor,
  getInteractionBackgroundColor,
} from '../utils/timelineHelpers';
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
  
  const llmDetails = interaction.details as LLMInteraction;
  const interactionType = llmDetails?.interaction_type || 'investigation';
  
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
  const typeStyle = getInteractionTypeStyle(interaction);

  return (
    <Card
      elevation={2}
      sx={{ 
        bgcolor: 'background.paper',
        borderRadius: 2,
        overflow: 'hidden',
        transition: 'all 0.2s ease-in-out',
        border: (() => {
          if (typeStyle) return typeStyle.borderColor;
          if (interaction.type === 'mcp') return '2px solid #ce93d8';
          return '2px solid #ffcc02';
        })(),
        '&:hover': {
          elevation: 4,
          transform: 'translateY(-1px)',
          border: (() => {
            if (typeStyle) return typeStyle.hoverBorderColor;
            if (interaction.type === 'mcp') return '2px solid #ba68c8';
            return '2px solid #ffa000';
          })()
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
          {interaction.type === 'llm' && !isExpanded && (
            <LLMInteractionPreview 
              interaction={interaction.details as LLMInteraction}
              showFullPreview={true}
            />
          )}
          
          {/* Show MCP preview when not expanded */}
          {interaction.type === 'mcp' && !isExpanded && (
            <MCPInteractionPreview 
              interaction={interaction.details as MCPInteraction}
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
            <Box 
              onClick={onToggle}
              sx={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 0.5,
                cursor: 'pointer',
                py: 0.75,
                px: 1.5,
                borderRadius: 1,
                bgcolor: interaction.type === 'llm' 
                  ? 'rgba(25, 118, 210, 0.04)' 
                  : interaction.type === 'mcp'
                  ? 'rgba(156, 39, 176, 0.04)'
                  : 'rgba(255, 152, 0, 0.04)',
                border: interaction.type === 'llm' 
                  ? '1px solid rgba(25, 118, 210, 0.12)' 
                  : interaction.type === 'mcp'
                  ? '1px solid rgba(156, 39, 176, 0.12)'
                  : '1px solid rgba(255, 152, 0, 0.12)',
                '&:hover': { 
                  bgcolor: interaction.type === 'llm' 
                    ? 'rgba(25, 118, 210, 0.08)' 
                    : interaction.type === 'mcp'
                    ? 'rgba(156, 39, 176, 0.08)'
                    : 'rgba(255, 152, 0, 0.08)',
                  border: interaction.type === 'llm' 
                    ? '1px solid rgba(25, 118, 210, 0.2)' 
                    : interaction.type === 'mcp'
                    ? '1px solid rgba(156, 39, 176, 0.2)'
                    : '1px solid rgba(255, 152, 0, 0.2)',
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
                  color: interaction.type === 'llm' 
                    ? '#1976d2' 
                    : interaction.type === 'mcp'
                    ? '#9c27b0'
                    : '#f57c00',
                  fontWeight: 500,
                  fontSize: '0.875rem'
                }}
              >
                {isExpanded ? 'Show Less' : 'Show Full Details'}
              </Typography>
              <Box sx={{ 
                color: interaction.type === 'llm' 
                  ? '#1976d2' 
                  : interaction.type === 'mcp'
                  ? '#9c27b0'
                  : '#f57c00',
                display: 'flex',
                alignItems: 'center'
              }}>
                {isExpanded ? <ExpandLess /> : <ExpandMore />}
              </Box>
            </Box>
          </Box>
          
          {/* Full interaction details when expanded */}
          <InteractionDetails
            type={interaction.type as 'llm' | 'mcp' | 'system'}
            details={interaction.details}
            expanded={isExpanded}
          />
        </CardContent>
      )}
    </Card>
  );
};

export default InteractionCard;

