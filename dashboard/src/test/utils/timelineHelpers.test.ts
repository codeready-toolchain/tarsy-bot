/**
 * Tests for timelineHelpers utility functions
 * Testing formatting and color mapping logic
 */

import { describe, it, expect, vi } from 'vitest';
import {
  getStageStatusColor,
  getInteractionColor,
  isToolList,
  formatInteractionForCopy,
  formatStageForCopy,
  getStageStatusIcon,
  getInteractionBackgroundColor,
} from '../../utils/timelineHelpers';
import type { TimelineItem, LLMInteraction, MCPInteraction, StageExecution } from '../../types';

// Mock timestamp and conversationParser utilities
vi.mock('../../utils/timestamp', () => ({
  formatTimestamp: vi.fn((_timestamp: number, format: string) => {
    if (format === 'absolute') return '2024-01-15 10:30:45';
    return '2 hours ago';
  }),
  formatDurationMs: vi.fn((ms: number) => `${ms}ms`),
}));

vi.mock('../../utils/conversationParser', () => ({
  getMessages: vi.fn((llmDetails: any) => {
    if (llmDetails.messages) return llmDetails.messages;
    return [];
  }),
}));

describe('timelineHelpers', () => {
  describe('getStageStatusColor', () => {
    it('should return success for completed status', () => {
      expect(getStageStatusColor('completed')).toBe('success');
    });

    it('should return error for failed status', () => {
      expect(getStageStatusColor('failed')).toBe('error');
    });

    it('should return primary for active status', () => {
      expect(getStageStatusColor('active')).toBe('primary');
    });

    it('should return warning for pending status', () => {
      expect(getStageStatusColor('pending')).toBe('warning');
    });

    it('should return default for unknown status', () => {
      expect(getStageStatusColor('unknown')).toBe('default');
      expect(getStageStatusColor('')).toBe('default');
    });

    it('should handle case sensitivity', () => {
      expect(getStageStatusColor('COMPLETED')).toBe('default');
      expect(getStageStatusColor('Completed')).toBe('default');
    });
  });

  describe('getInteractionColor', () => {
    it('should return primary for llm type', () => {
      expect(getInteractionColor('llm')).toBe('primary');
    });

    it('should return secondary for mcp type', () => {
      expect(getInteractionColor('mcp')).toBe('secondary');
    });

    it('should return warning for system type', () => {
      expect(getInteractionColor('system')).toBe('warning');
    });

    it('should return primary for unknown type', () => {
      expect(getInteractionColor('unknown')).toBe('primary');
      expect(getInteractionColor('')).toBe('primary');
    });
  });

  describe('isToolList', () => {
    it('should return true for tool_list communication type', () => {
      const mcp: MCPInteraction = {
        communication_type: 'tool_list',
        server_name: 'test',
        success: true,
      };
      expect(isToolList(mcp)).toBe(true);
    });

    it('should return true for tool_call with list_tools name', () => {
      const mcp: MCPInteraction = {
        communication_type: 'tool_call',
        tool_name: 'list_tools',
        server_name: 'test',
        success: true,
      };
      expect(isToolList(mcp)).toBe(true);
    });

    it('should return false for regular tool calls', () => {
      const mcp: MCPInteraction = {
        communication_type: 'tool_call',
        tool_name: 'get_data',
        server_name: 'test',
        success: true,
      };
      expect(isToolList(mcp)).toBe(false);
    });

    it('should return false for other communication types', () => {
      const mcp: MCPInteraction = {
        communication_type: 'resource_read',
        server_name: 'test',
        success: true,
      };
      expect(isToolList(mcp)).toBe(false);
    });
  });

  describe('formatInteractionForCopy', () => {
    it('should format basic LLM interaction', () => {
      const interaction = {
        id: 'int-1',
        type: 'llm',
        step_description: 'Test LLM call',
        timestamp_us: 1705315845000000,
        duration_ms: 1500,
        details: {
          interaction_type: 'investigation',
          model_name: 'gpt-4',
          messages: [
            { role: 'user', content: 'Hello' },
            { role: 'assistant', content: 'Hi there' },
          ],
          success: true,
          total_tokens: 100,
          temperature: 0.7,
        } as LLMInteraction,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Test LLM call');
      expect(formatted).toContain('Type: LLM');
      expect(formatted).toContain('Model: gpt-4');
      expect(formatted).toContain('USER:');
      expect(formatted).toContain('Hello');
      expect(formatted).toContain('ASSISTANT:');
      expect(formatted).toContain('Hi there');
      expect(formatted).toContain('Tokens Used: 100');
      expect(formatted).toContain('Temperature: 0.7');
    });

    it('should format LLM interaction with summarization type', () => {
      const interaction = {
        id: 'int-1',
        type: 'llm',
        step_description: 'Summarization',
        timestamp_us: 1705315845000000,
        details: {
          model_name: 'gpt-4',
          interaction_type: 'summarization',
          mcp_event_id: 'mcp-123',
          messages: [],
          success: true,
        } as any,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Interaction Type: Summarization');
      expect(formatted).toContain('MCP Event: mcp-123');
    });

    it('should format LLM interaction with final_analysis type', () => {
      const interaction = {
        id: 'int-1',
        type: 'llm',
        step_description: 'Final Analysis',
        timestamp_us: 1705315845000000,
        details: {
          model_name: 'gpt-4',
          interaction_type: 'final_analysis',
          messages: [],
          success: true,
        } as any,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Interaction Type: Final Analysis');
    });

    it('should format failed LLM interaction', () => {
      const interaction = {
        id: 'int-1',
        type: 'llm',
        step_description: 'Failed call',
        timestamp_us: 1705315845000000,
        details: {
          interaction_type: 'investigation',
          model_name: 'gpt-4',
          messages: [],
          success: false,
          error_message: 'Rate limit exceeded',
        } as any,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('ERROR: Rate limit exceeded');
    });

    it('should format LLM with no messages', () => {
      const interaction = {
        id: 'int-1',
        type: 'llm',
        step_description: 'Empty call',
        timestamp_us: 1705315845000000,
        details: {
          interaction_type: 'investigation',
          model_name: 'gpt-4',
          messages: [],
          success: true,
        } as any,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Conversation: No messages available');
    });

    it('should format MCP tool call interaction', () => {
      const interaction = {
        id: 'int-1',
        type: 'mcp',
        step_description: 'Tool call',
        timestamp_us: 1705315845000000,
        details: {
          server_name: 'test-server',
          communication_type: 'tool_call',
          tool_name: 'get_data',
          tool_arguments: { id: '123' },
          tool_result: { status: 'success', data: 'result' },
          success: true,
        } as MCPInteraction,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Server: test-server');
      expect(formatted).toContain('Communication Type: tool_call');
      expect(formatted).toContain('Tool: get_data');
      expect(formatted).toContain('--- PARAMETERS ---');
      expect(formatted).toContain('"id": "123"');
      expect(formatted).toContain('--- RESULT ---');
      expect(formatted).toContain('"status": "success"');
    });

    it('should format MCP tool list interaction', () => {
      const interaction = {
        id: 'int-1',
        type: 'mcp',
        step_description: 'List tools',
        timestamp_us: 1705315845000000,
        details: {
          server_name: 'test-server',
          communication_type: 'tool_list',
          available_tools: [
            { name: 'tool1', description: 'Tool 1' },
            { name: 'tool2', description: 'Tool 2' },
          ],
          success: true,
        } as MCPInteraction,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Tool: list_tools');
      expect(formatted).toContain('--- AVAILABLE TOOLS ---');
      expect(formatted).toContain('tool1');
      expect(formatted).toContain('tool2');
    });

    it('should handle MCP with no parameters', () => {
      const interaction = {
        id: 'int-1',
        type: 'mcp',
        step_description: 'Tool call',
        timestamp_us: 1705315845000000,
        details: {
          server_name: 'test-server',
          communication_type: 'tool_call',
          tool_name: 'get_all',
          success: true,
        } as MCPInteraction,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Parameters: None');
    });

    it('should handle interaction without details', () => {
      const interaction = {
        id: 'int-1',
        type: 'llm',
        step_description: 'Test',
        timestamp_us: 1705315845000000,
      } as any as TimelineItem;

      const formatted = formatInteractionForCopy(interaction);
      expect(formatted).toContain('Test');
      expect(formatted).toContain('Type: LLM');
    });
  });

  describe('formatStageForCopy', () => {
    it('should format complete stage with interactions', () => {
      const stage = {
        id: 'stage-1',
        stage_name: 'Investigation',
        agent: 'kubernetes',
        status: 'completed',
        started_at_us: 1705315845000000,
        duration_ms: 5000,
      } as any as StageExecution;

      const interactions = [
        {
          id: 'int-1',
          type: 'llm',
          step_description: 'Test',
          timestamp_us: 1705315845000000,
          details: {
            model_name: 'gpt-4',
            messages: [],
            success: true,
          } as any,
        } as any as TimelineItem,
      ];

      const formatted = formatStageForCopy(stage, 0, interactions);
      expect(formatted).toContain('STAGE 1: INVESTIGATION');
      expect(formatted).toContain('Agent: kubernetes');
      expect(formatted).toContain('Status: COMPLETED');
      expect(formatted).toContain('Interactions: 1');
      expect(formatted).toContain('--- INTERACTIONS ---');
      expect(formatted).toContain('INTERACTION 1');
    });

    it('should format stage with error', () => {
      const stage = {
        id: 'stage-1',
        stage_name: 'Investigation',
        agent: 'kubernetes',
        status: 'failed',
        error_message: 'Connection timeout',
      } as any as StageExecution;

      const formatted = formatStageForCopy(stage, 0, []);
      expect(formatted).toContain('Error: Connection timeout');
    });

    it('should format stage with no interactions', () => {
      const stage = {
        id: 'stage-1',
        stage_name: 'Investigation',
        agent: 'kubernetes',
        status: 'pending',
      } as any as StageExecution;

      const formatted = formatStageForCopy(stage, 2, []);
      expect(formatted).toContain('STAGE 3');
      expect(formatted).toContain('No interactions recorded for this stage');
    });

    it('should format multiple interactions in stage', () => {
      const stage = {
        id: 'stage-1',
        stage_name: 'Investigation',
        agent: 'kubernetes',
        status: 'completed',
      } as any as StageExecution;

      const interactions = [
        {
          id: 'int-1',
          type: 'llm',
          step_description: 'First',
          timestamp_us: 1705315845000000,
        } as any as TimelineItem,
        {
          id: 'int-2',
          type: 'mcp',
          step_description: 'Second',
          timestamp_us: 1705315846000000,
        } as any as TimelineItem,
      ];

      const formatted = formatStageForCopy(stage, 0, interactions);
      expect(formatted).toContain('Interactions: 2');
      expect(formatted).toContain('INTERACTION 1');
      expect(formatted).toContain('INTERACTION 2');
    });
  });

  describe('getStageStatusIcon', () => {
    it('should return checkmark for completed', () => {
      expect(getStageStatusIcon('completed')).toBe('✓');
    });

    it('should return X for failed', () => {
      expect(getStageStatusIcon('failed')).toBe('✗');
    });

    it('should return wrench for active', () => {
      expect(getStageStatusIcon('active')).toBe('🔧');
    });

    it('should return pause for pending', () => {
      expect(getStageStatusIcon('pending')).toBe('⏸');
    });

    it('should return pause for unknown', () => {
      expect(getStageStatusIcon('unknown')).toBe('⏸');
    });
  });

  describe('getInteractionBackgroundColor', () => {
    it('should return light blue for llm', () => {
      expect(getInteractionBackgroundColor('llm')).toBe('#f0f8ff');
    });

    it('should return light purple for mcp', () => {
      expect(getInteractionBackgroundColor('mcp')).toBe('#f5f0fa');
    });

    it('should return light yellow for system', () => {
      expect(getInteractionBackgroundColor('system')).toBe('#fef9e7');
    });

    it('should return light gray for unknown', () => {
      expect(getInteractionBackgroundColor('unknown')).toBe('#f5f5f5');
      expect(getInteractionBackgroundColor('')).toBe('#f5f5f5');
    });

    it('should return consistent colors', () => {
      // Test multiple calls return same color
      const color1 = getInteractionBackgroundColor('llm');
      const color2 = getInteractionBackgroundColor('llm');
      expect(color1).toBe(color2);
    });
  });
});

