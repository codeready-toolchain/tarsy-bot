/**
 * Native Tools Helpers
 * 
 * Helper functions for displaying native tools in the UI.
 * Provides formatting, icons, colors, and utility functions.
 */

import type { NativeToolsUsage } from '../types';
import SearchIcon from '@mui/icons-material/Search';
import CodeIcon from '@mui/icons-material/Code';
import LinkIcon from '@mui/icons-material/Link';

/**
 * Tool key constants matching backend GoogleNativeTool enum
 */
export const TOOL_KEYS = {
  GOOGLE_SEARCH: 'google_search',
  CODE_EXECUTION: 'code_execution',
  URL_CONTEXT: 'url_context'
} as const;

export type ToolKey = typeof TOOL_KEYS[keyof typeof TOOL_KEYS];

/**
 * Get human-readable display name for a tool
 */
export function getToolDisplayName(toolKey: string): string {
  const names: Record<string, string> = {
    [TOOL_KEYS.GOOGLE_SEARCH]: 'Google Search',
    [TOOL_KEYS.CODE_EXECUTION]: 'Code Execution',
    [TOOL_KEYS.URL_CONTEXT]: 'URL Context'
  };
  return names[toolKey] || toolKey;
}

/**
 * Get Material-UI icon component for a tool
 */
export function getToolIcon(toolKey: string): typeof SearchIcon | typeof CodeIcon | typeof LinkIcon {
  const icons: Record<string, typeof SearchIcon | typeof CodeIcon | typeof LinkIcon> = {
    [TOOL_KEYS.GOOGLE_SEARCH]: SearchIcon,
    [TOOL_KEYS.CODE_EXECUTION]: CodeIcon,
    [TOOL_KEYS.URL_CONTEXT]: LinkIcon
  };
  return icons[toolKey] || SearchIcon;
}

/**
 * Get color for a tool badge
 * 
 * @param toolKey - Tool identifier
 * @param used - Whether the tool was actually used (affects color intensity)
 * @returns MUI color theme key
 */
export function getToolColor(
  toolKey: string, 
  used: boolean = false
): 'default' | 'primary' | 'secondary' | 'success' | 'info' | 'warning' {
  // Base colors for each tool
  const baseColors: Record<string, 'primary' | 'secondary' | 'info'> = {
    [TOOL_KEYS.GOOGLE_SEARCH]: 'primary',
    [TOOL_KEYS.CODE_EXECUTION]: 'secondary',
    [TOOL_KEYS.URL_CONTEXT]: 'info'
  };

  const baseColor = baseColors[toolKey] || 'default';

  // If used, return success color to highlight actual usage
  return used ? 'success' : baseColor;
}

/**
 * Get background color style for tool badge
 * 
 * @param toolKey - Tool identifier
 * @param used - Whether the tool was actually used
 * @returns CSS color value
 */
export function getToolBackgroundColor(toolKey: string, used: boolean = false): string {
  if (used) {
    return 'rgba(46, 125, 50, 0.12)'; // success color with transparency
  }

  const colors: Record<string, string> = {
    [TOOL_KEYS.GOOGLE_SEARCH]: 'rgba(25, 118, 210, 0.08)',
    [TOOL_KEYS.CODE_EXECUTION]: 'rgba(156, 39, 176, 0.08)',
    [TOOL_KEYS.URL_CONTEXT]: 'rgba(2, 136, 209, 0.08)'
  };

  return colors[toolKey] || 'rgba(0, 0, 0, 0.08)';
}

/**
 * Get border color for tool badge
 */
export function getToolBorderColor(toolKey: string, used: boolean = false): string {
  if (used) {
    return 'rgba(46, 125, 50, 0.5)'; // success color
  }

  const colors: Record<string, string> = {
    [TOOL_KEYS.GOOGLE_SEARCH]: 'rgba(25, 118, 210, 0.3)',
    [TOOL_KEYS.CODE_EXECUTION]: 'rgba(156, 39, 176, 0.3)',
    [TOOL_KEYS.URL_CONTEXT]: 'rgba(2, 136, 209, 0.3)'
  };

  return colors[toolKey] || 'rgba(0, 0, 0, 0.23)';
}

/**
 * Check if a specific tool was actually used (has usage data)
 */
export function isToolUsed(usage: NativeToolsUsage | null | undefined, toolKey: string): boolean {
  if (!usage) {
    return false;
  }

  switch (toolKey) {
    case TOOL_KEYS.GOOGLE_SEARCH:
      return !!usage.google_search;
    case TOOL_KEYS.CODE_EXECUTION:
      return !!usage.code_execution;
    case TOOL_KEYS.URL_CONTEXT:
      return !!usage.url_context;
    default:
      return false;
  }
}

/**
 * Get usage count for a tool (for badge display)
 */
export function getToolUsageCount(usage: NativeToolsUsage | null | undefined, toolKey: string): number | null {
  if (!usage) {
    return null;
  }

  switch (toolKey) {
    case TOOL_KEYS.GOOGLE_SEARCH:
      return usage.google_search?.query_count || null;
    case TOOL_KEYS.CODE_EXECUTION:
      return usage.code_execution ? 
        (usage.code_execution.code_blocks + usage.code_execution.output_blocks) : null;
    case TOOL_KEYS.URL_CONTEXT:
      return usage.url_context?.url_count || null;
    default:
      return null;
  }
}

/**
 * Get list of enabled tools from config
 */
export function getEnabledTools(config: Record<string, boolean> | null | undefined): string[] {
  if (!config) {
    return [];
  }

  return Object.entries(config)
    .filter(([_, enabled]) => enabled)
    .map(([key, _]) => key);
}

/**
 * Get usage summary text for a tool
 */
export function getToolUsageSummary(usage: NativeToolsUsage | null | undefined, toolKey: string): string | null {
  if (!usage) {
    return null;
  }

  switch (toolKey) {
    case TOOL_KEYS.GOOGLE_SEARCH:
      if (usage.google_search) {
        const count = usage.google_search.query_count;
        return `${count} ${count === 1 ? 'query' : 'queries'}`;
      }
      return null;

    case TOOL_KEYS.CODE_EXECUTION:
      if (usage.code_execution) {
        const { code_blocks, output_blocks } = usage.code_execution;
        const parts: string[] = [];
        if (code_blocks > 0) parts.push(`${code_blocks} code ${code_blocks === 1 ? 'block' : 'blocks'}`);
        if (output_blocks > 0) parts.push(`${output_blocks} output ${output_blocks === 1 ? 'block' : 'blocks'}`);
        return parts.join(', ');
      }
      return null;

    case TOOL_KEYS.URL_CONTEXT:
      if (usage.url_context) {
        const count = usage.url_context.url_count;
        return `${count} ${count === 1 ? 'URL' : 'URLs'}`;
      }
      return null;

    default:
      return null;
  }
}

