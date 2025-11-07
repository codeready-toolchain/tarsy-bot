import { describe, it, expect } from 'vitest';
import { parseSessionChatFlow, getChatFlowStats, type ChatFlowItemData } from '../../utils/chatFlowParser';
import type { DetailedSession } from '../../types';

describe('chatFlowParser', () => {
  describe('parseSessionChatFlow', () => {
    it('should parse empty session with no stages', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [],
      } as any;

      const result = parseSessionChatFlow(session);

      expect(result).toEqual([]);
    });

    it('should add stage start markers for each stage', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'Stage 1',
            agent: 'agent-1',
            started_at_us: 1000000,
            llm_interactions: [],
            mcp_communications: [],
          },
          {
            stage_name: 'Stage 2',
            agent: 'agent-2',
            started_at_us: 2000000,
            llm_interactions: [],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      expect(result).toHaveLength(2);
      expect(result[0]).toEqual({
        type: 'stage_start',
        timestamp_us: 1000000,
        stageName: 'Stage 1',
        stageAgent: 'agent-1',
      });
      expect(result[1]).toEqual({
        type: 'stage_start',
        timestamp_us: 2000000,
        stageName: 'Stage 2',
        stageAgent: 'agent-2',
      });
    });

    it('should parse user messages from chat stages', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'chat-stage',
            agent: 'chat-agent',
            started_at_us: 1000000,
            chat_user_message: {
              message_id: 'msg-1',
              content: 'What is the issue?',
              author: 'john@example.com',
              created_at_us: 1000500,
            },
            llm_interactions: [],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      expect(result).toHaveLength(2);
      expect(result[0].type).toBe('stage_start');
      expect(result[1]).toEqual({
        type: 'user_message',
        timestamp_us: 1000500,
        content: 'What is the issue?',
        author: 'john@example.com',
        messageId: 'msg-1',
      });
    });

    it('should adjust user message timestamp to be after stage start', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'chat-stage',
            agent: 'chat-agent',
            started_at_us: 2000000,
            chat_user_message: {
              message_id: 'msg-1',
              content: 'Question',
              author: 'user',
              created_at_us: 1000000, // Before stage start!
            },
            llm_interactions: [],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const stageStart = result.find(item => item.type === 'stage_start');
      const userMessage = result.find(item => item.type === 'user_message');

      expect(userMessage?.timestamp_us).toBe(2000001); // stage start + 1
      expect(userMessage?.timestamp_us).toBeGreaterThan(stageStart!.timestamp_us);
    });

    it('should parse investigation thoughts from LLM interactions', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'investigation',
            agent: 'investigator',
            started_at_us: 1000000,
            llm_interactions: [
              {
                timestamp_us: 1500000,
                details: {
                  interaction_type: 'investigation',
                  messages: [
                    {
                      role: 'assistant',
                      content: 'Thought: I need to check the logs',
                    },
                  ],
                },
              },
            ],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const thought = result.find(item => item.type === 'thought');
      expect(thought).toBeDefined();
      expect(thought?.content).toBe('I need to check the logs');
      expect(thought?.timestamp_us).toBe(1500000);
    });

    it('should parse final analysis with both thought and final answer', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'analysis',
            agent: 'analyzer',
            started_at_us: 1000000,
            llm_interactions: [
              {
                timestamp_us: 1500000,
                details: {
                  interaction_type: 'final_analysis',
                  messages: [
                    {
                      role: 'assistant',
                      content: 'Thought: Let me summarize\nFinal Answer: The root cause is X',
                    },
                  ],
                },
              },
            ],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const thought = result.find(item => item.type === 'thought');
      const finalAnswer = result.find(item => item.type === 'final_answer');

      expect(thought).toBeDefined();
      expect(thought?.content).toBe('Let me summarize');
      expect(finalAnswer).toBeDefined();
      expect(finalAnswer?.content).toBe('The root cause is X');
      // Final answer should come after thought
      expect(finalAnswer?.timestamp_us).toBe(1500001);
    });

    it('should parse summarization interactions', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'stage',
            agent: 'agent',
            started_at_us: 1000000,
            llm_interactions: [
              {
                timestamp_us: 1500000,
                details: {
                  interaction_type: 'summarization',
                  mcp_event_id: 'mcp-123',
                  messages: [
                    {
                      role: 'assistant',
                      content: 'Summary of the tool call result',
                    },
                  ],
                },
              },
            ],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const summary = result.find(item => item.type === 'summarization');
      expect(summary).toBeDefined();
      expect(summary?.content).toBe('Summary of the tool call result');
      expect(summary?.mcp_event_id).toBe('mcp-123');
    });

    it('should parse MCP tool calls', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'stage',
            agent: 'agent',
            started_at_us: 1000000,
            llm_interactions: [],
            mcp_communications: [
              {
                event_id: 'mcp-1',
                timestamp_us: 1500000,
                duration_ms: 123,
                details: {
                  communication_type: 'tool_call',
                  tool_name: 'kubectl_get_pods',
                  tool_arguments: { namespace: 'default' },
                  tool_result: { pods: [] },
                  server_name: 'kubernetes',
                  success: true,
                },
              },
            ],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const toolCall = result.find(item => item.type === 'tool_call');
      expect(toolCall).toBeDefined();
      expect(toolCall).toMatchObject({
        type: 'tool_call',
        timestamp_us: 1500000,
        toolName: 'kubectl_get_pods',
        toolArguments: { namespace: 'default' },
        toolResult: { pods: [] },
        serverName: 'kubernetes',
        success: true,
        duration_ms: 123,
        mcp_event_id: 'mcp-1',
      });
    });

    it('should filter out non-tool_call MCP communications', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'stage',
            agent: 'agent',
            started_at_us: 1000000,
            llm_interactions: [],
            mcp_communications: [
              {
                event_id: 'mcp-1',
                timestamp_us: 1500000,
                details: {
                  communication_type: 'initialization',
                  server_name: 'kubernetes',
                },
              },
              {
                event_id: 'mcp-2',
                timestamp_us: 1600000,
                details: {
                  communication_type: 'tool_call',
                  tool_name: 'get_pods',
                  server_name: 'kubernetes',
                },
              },
            ],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const toolCalls = result.filter(item => item.type === 'tool_call');
      expect(toolCalls).toHaveLength(1);
      expect(toolCalls[0].toolName).toBe('get_pods');
    });

    it('should sort all items chronologically across stages', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'Stage 1',
            agent: 'agent-1',
            started_at_us: 1000000,
            llm_interactions: [
              {
                timestamp_us: 1500000,
                details: {
                  interaction_type: 'investigation',
                  messages: [{ role: 'assistant', content: 'Thought: First thought' }],
                },
              },
            ],
            mcp_communications: [],
          },
          {
            stage_name: 'Stage 2',
            agent: 'agent-2',
            started_at_us: 1200000, // Earlier than first stage's interaction!
            llm_interactions: [
              {
                timestamp_us: 1300000,
                details: {
                  interaction_type: 'investigation',
                  messages: [{ role: 'assistant', content: 'Thought: Second thought' }],
                },
              },
            ],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      // Extract timestamps to verify ordering
      const timestamps = result.map(item => item.timestamp_us);
      const sortedTimestamps = [...timestamps].sort((a, b) => a - b);

      expect(timestamps).toEqual(sortedTimestamps);
    });

    it('should handle stages with missing timestamps', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'Stage 1',
            agent: 'agent-1',
            started_at_us: null, // Missing timestamp
            llm_interactions: [],
            mcp_communications: [],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      expect(result).toHaveLength(1);
      expect(result[0].type).toBe('stage_start');
      expect(result[0].timestamp_us).toBeGreaterThan(0);
    });

    it('should handle failed MCP tool calls', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'stage',
            agent: 'agent',
            started_at_us: 1000000,
            llm_interactions: [],
            mcp_communications: [
              {
                event_id: 'mcp-fail',
                timestamp_us: 1500000,
                details: {
                  communication_type: 'tool_call',
                  tool_name: 'failing_tool',
                  tool_arguments: {},
                  server_name: 'server',
                  success: false,
                  error_message: 'Connection timeout',
                },
              },
            ],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const toolCall = result.find(item => item.type === 'tool_call');
      expect(toolCall).toBeDefined();
      expect(toolCall?.success).toBe(false);
      expect(toolCall?.errorMessage).toBe('Connection timeout');
    });

    it('should use fallback event_id if id is not present', () => {
      const session: DetailedSession = {
        session_id: 'session-1',
        stages: [
          {
            stage_name: 'stage',
            agent: 'agent',
            started_at_us: 1000000,
            llm_interactions: [],
            mcp_communications: [
              {
                id: 'legacy-id',
                timestamp_us: 1500000,
                details: {
                  communication_type: 'tool_call',
                  tool_name: 'tool',
                  server_name: 'server',
                },
              } as any,
            ],
          },
        ],
      } as any;

      const result = parseSessionChatFlow(session);

      const toolCall = result.find(item => item.type === 'tool_call');
      expect(toolCall?.mcp_event_id).toBe('legacy-id');
    });
  });

  describe('getChatFlowStats', () => {
    it('should return correct statistics for empty flow', () => {
      const stats = getChatFlowStats([]);

      expect(stats).toEqual({
        totalItems: 0,
        thoughtsCount: 0,
        toolCallsCount: 0,
        finalAnswersCount: 0,
        successfulToolCalls: 0,
      });
    });

    it('should count different item types correctly', () => {
      const items: ChatFlowItemData[] = [
        { type: 'stage_start', timestamp_us: 1000, stageName: 'S1', stageAgent: 'A1' },
        { type: 'thought', timestamp_us: 1001, content: 'T1' },
        { type: 'thought', timestamp_us: 1002, content: 'T2' },
        { type: 'tool_call', timestamp_us: 1003, toolName: 'tool1', success: true },
        { type: 'tool_call', timestamp_us: 1004, toolName: 'tool2', success: false },
        { type: 'final_answer', timestamp_us: 1005, content: 'Answer' },
      ];

      const stats = getChatFlowStats(items);

      expect(stats).toEqual({
        totalItems: 6,
        thoughtsCount: 2,
        toolCallsCount: 2,
        finalAnswersCount: 1,
        successfulToolCalls: 1,
      });
    });

    it('should count user messages and summarizations', () => {
      const items: ChatFlowItemData[] = [
        { type: 'user_message', timestamp_us: 1000, content: 'Question', author: 'user' },
        { type: 'summarization', timestamp_us: 1001, content: 'Summary' },
      ];

      const stats = getChatFlowStats(items);

      expect(stats.totalItems).toBe(2);
      // These types are not explicitly counted in the stats but contribute to total
      expect(stats.thoughtsCount).toBe(0);
      expect(stats.toolCallsCount).toBe(0);
    });

    it('should handle tool calls with undefined success as unsuccessful', () => {
      const items: ChatFlowItemData[] = [
        { type: 'tool_call', timestamp_us: 1000, toolName: 'tool1' }, // No success field (undefined)
        { type: 'tool_call', timestamp_us: 1001, toolName: 'tool2', success: true },
        { type: 'tool_call', timestamp_us: 1002, toolName: 'tool3', success: false },
      ];

      const stats = getChatFlowStats(items);

      // Undefined success is falsy, so only explicitly true counts as successful
      expect(stats.toolCallsCount).toBe(3);
      expect(stats.successfulToolCalls).toBe(1);
    });
  });
});
