import { describe, it, expect } from 'vitest'
import { parseSessionChatFlow, getChatFlowStats } from '../../utils/chatFlowParser'
import type { DetailedSession } from '../../types'

describe('chatFlowParser - Summarization Support', () => {
  it('should parse summarization interactions with mcp_event_id', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-sum-1',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 3000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-sum-1',
        stage_id: 'analysis',
        stage_index: 0,
        stage_name: 'Analysis Stage',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [
          // Tool call investigation
          {
            event_id: 'llm-1',
            type: 'llm',
            timestamp_us: 1100000,
            duration_ms: 500,
            step_description: 'Investigating',
            details: {
              model_name: 'test-model',
              interaction_type: 'investigation',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Thought: I need to check the pods.\n\nAction: get_pods\nAction Input: {}'
                }]
              },
              success: true,
              total_tokens: 100,
              input_tokens: 40,
              output_tokens: 60,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          // Summarization interaction
          {
            event_id: 'llm-2',
            type: 'llm',
            timestamp_us: 1200000,
            duration_ms: 300,
            step_description: 'Summarizing tool result',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-1', // Links to the tool call being summarized
              conversation: {
                messages: [
                  {
                    role: 'user',
                    content: 'Summarize the following tool result: ...'
                  },
                  {
                    role: 'assistant',
                    content: 'The get_pods tool returned a list of 5 pods running in the default namespace. All pods are in a healthy state with no crashes reported.'
                  }
                ]
              },
              success: true,
              total_tokens: 80,
              input_tokens: 30,
              output_tokens: 50,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          }
        ],
        mcp_communications: [{
          event_id: 'mcp-1',
          type: 'mcp',
          timestamp_us: 1150000,
          duration_ms: 200,
          step_description: 'Get pods',
          details: {
            tool_name: 'get_pods',
            server_name: 'kubernetes-server',
            communication_type: 'tool_call',
            parameters: { namespace: 'default' },
            result: { pods: ['pod-1', 'pod-2', 'pod-3', 'pod-4', 'pod-5'] },
            available_tools: {},
            success: true,
            error_message: null
          }
        }],
        total_interactions: 3,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 2,
        mcp_communication_count: 1,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 3,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 2000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should have: stage_start, thought, tool_call, summarization (in chronological order)
    expect(chatFlow.length).toBe(4)

    // Verify stage start
    expect(chatFlow[0].type).toBe('stage_start')
    expect(chatFlow[0].stageName).toBe('Analysis Stage')

    // Verify thought
    const thoughtItem = chatFlow.find(item => item.type === 'thought')
    expect(thoughtItem).toBeDefined()
    expect(thoughtItem!.content).toContain('I need to check the pods')

    // Verify tool call
    const toolCallItem = chatFlow.find(item => item.type === 'tool_call')
    expect(toolCallItem).toBeDefined()
    expect(toolCallItem!.toolName).toBe('get_pods')
    expect(toolCallItem!.success).toBe(true)

    // Verify summarization
    const summarizationItem = chatFlow.find(item => item.type === 'summarization')
    expect(summarizationItem).toBeDefined()
    expect(summarizationItem!.content).toContain('The get_pods tool returned')
    expect(summarizationItem!.content).toContain('5 pods running')
    expect(summarizationItem!.mcp_event_id).toBe('mcp-1')

    // Verify chronological ordering (timestamps should be ascending)
    for (let i = 1; i < chatFlow.length; i++) {
      expect(chatFlow[i].timestamp_us).toBeGreaterThanOrEqual(chatFlow[i - 1].timestamp_us)
    }
  })

  it('should handle summarization without mcp_event_id', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-sum-2',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 2000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-sum-2',
        stage_id: 'analysis',
        stage_index: 0,
        stage_name: 'Analysis Stage',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [{
          event_id: 'llm-1',
          type: 'llm',
          timestamp_us: 1100000,
          duration_ms: 300,
          step_description: 'Summarizing',
          details: {
            model_name: 'test-model',
            interaction_type: 'summarization',
            // No mcp_event_id
            conversation: {
              messages: [{
                role: 'assistant',
                content: 'This is a general summary without linking to a specific tool call.'
              }]
            },
            success: true,
            total_tokens: 50,
            input_tokens: 20,
            output_tokens: 30,
            temperature: null,
            error_message: null,
            tool_calls: null,
            tool_results: null
          }
        }],
        mcp_communications: [],
        total_interactions: 1,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 1,
        mcp_communication_count: 0,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 1,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 1000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should have: stage_start and summarization
    expect(chatFlow.length).toBe(2)

    const summarizationItem = chatFlow.find(item => item.type === 'summarization')
    expect(summarizationItem).toBeDefined()
    expect(summarizationItem!.content).toContain('general summary')
    expect(summarizationItem!.mcp_event_id).toBeUndefined()
  })

  it('should skip summarization with empty or missing content', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-sum-3',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 2000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-sum-3',
        stage_id: 'analysis',
        stage_index: 0,
        stage_name: 'Analysis Stage',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [
          // Empty content
          {
            event_id: 'llm-1',
            type: 'llm',
            timestamp_us: 1100000,
            duration_ms: 100,
            step_description: 'Empty summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: ''
                }]
              },
              success: true,
              total_tokens: 10,
              input_tokens: 5,
              output_tokens: 5,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          // No messages
          {
            event_id: 'llm-2',
            type: 'llm',
            timestamp_us: 1200000,
            duration_ms: 100,
            step_description: 'No messages',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              conversation: {
                messages: []
              },
              success: true,
              total_tokens: 10,
              input_tokens: 5,
              output_tokens: 5,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          }
        ],
        mcp_communications: [],
        total_interactions: 2,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 2,
        mcp_communication_count: 0,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 2,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 1000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should only have stage_start (no summarization items)
    expect(chatFlow.length).toBe(1)
    expect(chatFlow[0].type).toBe('stage_start')
    expect(chatFlow.find(item => item.type === 'summarization')).toBeUndefined()
  })

  it('should handle multiple summarizations in chronological order', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-sum-4',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 4000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-sum-4',
        stage_id: 'analysis',
        stage_index: 0,
        stage_name: 'Multi-Tool Stage',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 4000000,
        duration_ms: 3000,
        llm_interactions: [
          {
            event_id: 'llm-1',
            type: 'llm',
            timestamp_us: 1100000,
            duration_ms: 200,
            step_description: 'First summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-1',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Summary of first tool call.'
                }]
              },
              success: true,
              total_tokens: 30,
              input_tokens: 15,
              output_tokens: 15,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          {
            event_id: 'llm-2',
            type: 'llm',
            timestamp_us: 1300000,
            duration_ms: 200,
            step_description: 'Second summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-2',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Summary of second tool call.'
                }]
              },
              success: true,
              total_tokens: 30,
              input_tokens: 15,
              output_tokens: 15,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          {
            event_id: 'llm-3',
            type: 'llm',
            timestamp_us: 1500000,
            duration_ms: 200,
            step_description: 'Third summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-3',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Summary of third tool call.'
                }]
              },
              success: true,
              total_tokens: 30,
              input_tokens: 15,
              output_tokens: 15,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          }
        ],
        mcp_communications: [
          {
            event_id: 'mcp-1',
            type: 'mcp',
            timestamp_us: 1050000,
            duration_ms: 100,
            step_description: 'First tool',
            details: {
              tool_name: 'tool_1',
              server_name: 'server-1',
              communication_type: 'tool_call',
              parameters: {},
              result: { data: 'result1' },
              available_tools: {},
              success: true,
              error_message: null
            }
          },
          {
            event_id: 'mcp-2',
            type: 'mcp',
            timestamp_us: 1250000,
            duration_ms: 100,
            step_description: 'Second tool',
            details: {
              tool_name: 'tool_2',
              server_name: 'server-1',
              communication_type: 'tool_call',
              parameters: {},
              result: { data: 'result2' },
              available_tools: {},
              success: true,
              error_message: null
            }
          },
          {
            event_id: 'mcp-3',
            type: 'mcp',
            timestamp_us: 1450000,
            duration_ms: 100,
            step_description: 'Third tool',
            details: {
              tool_name: 'tool_3',
              server_name: 'server-1',
              communication_type: 'tool_call',
              parameters: {},
              result: { data: 'result3' },
              available_tools: {},
              success: true,
              error_message: null
            }
          }
        ],
        total_interactions: 6,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 3,
        mcp_communication_count: 3,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 6,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 3000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should have: stage_start + 3 tool_calls + 3 summarizations = 7 items
    expect(chatFlow.length).toBe(7)

    // Verify all summarizations are present
    const summarizations = chatFlow.filter(item => item.type === 'summarization')
    expect(summarizations.length).toBe(3)

    // Verify each summarization has correct mcp_event_id
    expect(summarizations[0].mcp_event_id).toBe('mcp-1')
    expect(summarizations[1].mcp_event_id).toBe('mcp-2')
    expect(summarizations[2].mcp_event_id).toBe('mcp-3')

    // Verify chronological order
    for (let i = 1; i < chatFlow.length; i++) {
      expect(chatFlow[i].timestamp_us).toBeGreaterThanOrEqual(chatFlow[i - 1].timestamp_us)
    }

    // Verify each tool call is followed by its summarization (due to timestamps)
    // Tool 1 (1050000) -> Summarization 1 (1100000)
    // Tool 2 (1250000) -> Summarization 2 (1300000)
    // Tool 3 (1450000) -> Summarization 3 (1500000)
    const toolCall1Index = chatFlow.findIndex(item => item.type === 'tool_call' && item.toolName === 'tool_1')
    const sum1Index = chatFlow.findIndex(item => item.type === 'summarization' && item.mcp_event_id === 'mcp-1')
    expect(sum1Index).toBeGreaterThan(toolCall1Index)

    const toolCall2Index = chatFlow.findIndex(item => item.type === 'tool_call' && item.toolName === 'tool_2')
    const sum2Index = chatFlow.findIndex(item => item.type === 'summarization' && item.mcp_event_id === 'mcp-2')
    expect(sum2Index).toBeGreaterThan(toolCall2Index)

    const toolCall3Index = chatFlow.findIndex(item => item.type === 'tool_call' && item.toolName === 'tool_3')
    const sum3Index = chatFlow.findIndex(item => item.type === 'summarization' && item.mcp_event_id === 'mcp-3')
    expect(sum3Index).toBeGreaterThan(toolCall3Index)
  })

  it('should handle sessions with mixed interaction types including summarization', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-sum-5',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 3000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-sum-5',
        stage_id: 'mixed',
        stage_index: 0,
        stage_name: 'Mixed Stage',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 3000000,
        duration_ms: 2000,
        llm_interactions: [
          // Investigation
          {
            event_id: 'llm-1',
            type: 'llm',
            timestamp_us: 1100000,
            duration_ms: 200,
            step_description: 'Investigation',
            details: {
              model_name: 'test-model',
              interaction_type: 'investigation',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Thought: I need to investigate.\n\nAction: tool_1\nAction Input: {}'
                }]
              },
              success: true,
              total_tokens: 50,
              input_tokens: 20,
              output_tokens: 30,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          // Summarization
          {
            event_id: 'llm-2',
            type: 'llm',
            timestamp_us: 1300000,
            duration_ms: 150,
            step_description: 'Summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-1',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'The tool returned success.'
                }]
              },
              success: true,
              total_tokens: 30,
              input_tokens: 15,
              output_tokens: 15,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          // Final analysis
          {
            event_id: 'llm-3',
            type: 'llm',
            timestamp_us: 1400000,
            duration_ms: 200,
            step_description: 'Final analysis',
            details: {
              model_name: 'test-model',
              interaction_type: 'final_analysis',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Thought: Based on the investigation.\n\nFinal Answer: Everything is working correctly.'
                }]
              },
              success: true,
              total_tokens: 60,
              input_tokens: 25,
              output_tokens: 35,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          }
        ],
        mcp_communications: [{
          event_id: 'mcp-1',
          type: 'mcp',
          timestamp_us: 1200000,
          duration_ms: 100,
          step_description: 'Tool call',
          details: {
            tool_name: 'tool_1',
            server_name: 'server-1',
            communication_type: 'tool_call',
            parameters: {},
            result: { status: 'success' },
            available_tools: {},
            success: true,
            error_message: null
          }
        }],
        total_interactions: 4,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 3,
        mcp_communication_count: 1,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 4,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 2000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should have: stage_start, thought, tool_call, summarization, thought, final_answer = 6 items
    expect(chatFlow.length).toBe(6)

    // Verify all types are present
    expect(chatFlow.filter(item => item.type === 'stage_start').length).toBe(1)
    expect(chatFlow.filter(item => item.type === 'thought').length).toBe(2)
    expect(chatFlow.filter(item => item.type === 'tool_call').length).toBe(1)
    expect(chatFlow.filter(item => item.type === 'summarization').length).toBe(1)
    expect(chatFlow.filter(item => item.type === 'final_answer').length).toBe(1)

    // Verify summarization links to correct tool call
    const summarization = chatFlow.find(item => item.type === 'summarization')
    expect(summarization!.mcp_event_id).toBe('mcp-1')
  })
})

describe('chatFlowParser - Integration with Existing Features', () => {
  it('should maintain chronological order with thoughts, tool calls, and summarizations', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-chrono',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 2000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-chrono',
        stage_id: 'chrono',
        stage_index: 0,
        stage_name: 'Chronological Test',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [
          {
            event_id: 'llm-1',
            type: 'llm',
            timestamp_us: 1000100, // Very early
            duration_ms: 100,
            step_description: 'First thought',
            details: {
              model_name: 'test-model',
              interaction_type: 'investigation',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Thought: First thought'
                }]
              },
              success: true,
              total_tokens: 20,
              input_tokens: 10,
              output_tokens: 10,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          {
            event_id: 'llm-2',
            type: 'llm',
            timestamp_us: 1000300, // After tool call
            duration_ms: 100,
            step_description: 'Summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-1',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Tool completed successfully'
                }]
              },
              success: true,
              total_tokens: 20,
              input_tokens: 10,
              output_tokens: 10,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          {
            event_id: 'llm-3',
            type: 'llm',
            timestamp_us: 1000400, // After summarization
            duration_ms: 100,
            step_description: 'Second thought',
            details: {
              model_name: 'test-model',
              interaction_type: 'investigation',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Thought: Second thought'
                }]
              },
              success: true,
              total_tokens: 20,
              input_tokens: 10,
              output_tokens: 10,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          }
        ],
        mcp_communications: [{
          event_id: 'mcp-1',
          type: 'mcp',
          timestamp_us: 1000200, // Between first thought and summarization
          duration_ms: 50,
          step_description: 'Tool call',
          details: {
            tool_name: 'test_tool',
            server_name: 'test-server',
            communication_type: 'tool_call',
            parameters: {},
            result: { success: true },
            available_tools: {},
            success: true,
            error_message: null
          }
        }],
        total_interactions: 4,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 3,
        mcp_communication_count: 1,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 4,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 1000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should be in exact chronological order
    const expectedOrder = [
      'stage_start',  // 1000000
      'thought',      // 1000100 - First thought
      'tool_call',    // 1000200 - Tool call
      'summarization', // 1000300 - Summarization
      'thought'       // 1000400 - Second thought
    ]

    expect(chatFlow.length).toBe(5)
    chatFlow.forEach((item, index) => {
      expect(item.type).toBe(expectedOrder[index])
    })

    // Verify timestamps are ascending
    for (let i = 1; i < chatFlow.length; i++) {
      expect(chatFlow[i].timestamp_us).toBeGreaterThanOrEqual(chatFlow[i - 1].timestamp_us)
    }
  })

  it('should correctly use last assistant message for summarization even when user message is last', () => {
    // Regression test: ensures we use the computed lastAssistantMessage
    // instead of messages[messages.length - 1] which could pick a user message
    const mockSession: DetailedSession = {
      session_id: 'test-session-user-last',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 2000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-user-last',
        stage_id: 'user-last',
        stage_index: 0,
        stage_name: 'Edge Case Test',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [{
          event_id: 'llm-1',
          type: 'llm',
          timestamp_us: 1100000,
          duration_ms: 200,
          step_description: 'Summarization with trailing user message',
          details: {
            model_name: 'test-model',
            interaction_type: 'summarization',
            mcp_event_id: 'mcp-1',
            conversation: {
              messages: [
                {
                  role: 'user',
                  content: 'Summarize this tool result: ...'
                },
                {
                  role: 'assistant',
                  content: 'The tool successfully completed and returned the expected results.'
                },
                {
                  role: 'user',
                  content: 'Some trailing user message'
                }
              ]
            },
            success: true,
            total_tokens: 50,
            input_tokens: 20,
            output_tokens: 30,
            temperature: null,
            error_message: null,
            tool_calls: null,
            tool_results: null
          }
        }],
        mcp_communications: [{
          event_id: 'mcp-1',
          type: 'mcp',
          timestamp_us: 1050000,
          duration_ms: 100,
          step_description: 'Tool call',
          details: {
            tool_name: 'test_tool',
            server_name: 'test-server',
            communication_type: 'tool_call',
            parameters: {},
            result: { success: true },
            available_tools: {},
            success: true,
            error_message: null
          }
        }],
        total_interactions: 2,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 1,
        mcp_communication_count: 1,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 2,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 1000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)

    // Should have: stage_start, tool_call, summarization
    expect(chatFlow.length).toBe(3)

    const summarization = chatFlow.find(item => item.type === 'summarization')
    expect(summarization).toBeDefined()
    
    // Should use the assistant message content, not the trailing user message
    expect(summarization!.content).toBe('The tool successfully completed and returned the expected results.')
    expect(summarization!.content).not.toContain('trailing user message')
    expect(summarization!.mcp_event_id).toBe('mcp-1')
  })

  it('should work correctly with getChatFlowStats (no summarization count)', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-stats',
      alert_type: 'TestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 2000000,
      alert_data: {},
      stages: [{
        execution_id: 'stage-1',
        session_id: 'test-session-stats',
        stage_id: 'stats',
        stage_index: 0,
        stage_name: 'Stats Test',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [
          {
            event_id: 'llm-1',
            type: 'llm',
            timestamp_us: 1100000,
            duration_ms: 100,
            step_description: 'Thought',
            details: {
              model_name: 'test-model',
              interaction_type: 'investigation',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Thought: Thinking'
                }]
              },
              success: true,
              total_tokens: 20,
              input_tokens: 10,
              output_tokens: 10,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          {
            event_id: 'llm-2',
            type: 'llm',
            timestamp_us: 1300000,
            duration_ms: 100,
            step_description: 'Summarization',
            details: {
              model_name: 'test-model',
              interaction_type: 'summarization',
              mcp_event_id: 'mcp-1',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Summary'
                }]
              },
              success: true,
              total_tokens: 20,
              input_tokens: 10,
              output_tokens: 10,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          },
          {
            event_id: 'llm-3',
            type: 'llm',
            timestamp_us: 1400000,
            duration_ms: 100,
            step_description: 'Final',
            details: {
              model_name: 'test-model',
              interaction_type: 'final_analysis',
              conversation: {
                messages: [{
                  role: 'assistant',
                  content: 'Final Answer: Done'
                }]
              },
              success: true,
              total_tokens: 20,
              input_tokens: 10,
              output_tokens: 10,
              temperature: null,
              error_message: null,
              tool_calls: null,
              tool_results: null
            }
          }
        ],
        mcp_communications: [{
          event_id: 'mcp-1',
          type: 'mcp',
          timestamp_us: 1200000,
          duration_ms: 50,
          step_description: 'Tool call',
          details: {
            tool_name: 'tool_1',
            server_name: 'test-server',
            communication_type: 'tool_call',
            parameters: {},
            result: { success: true },
            available_tools: {},
            success: true,
            error_message: null
          }
        }],
        total_interactions: 4,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 3,
        mcp_communication_count: 1,
        stage_input_tokens: null,
        stage_output_tokens: null,
        stage_total_tokens: null
      }],
      total_interactions: 4,
      final_analysis: null,
      session_metadata: {},
      chain_definition: null,
      current_stage_id: null,
      current_stage_index: 0,
      chain_id: null,
      session_input_tokens: null,
      session_output_tokens: null,
      session_total_tokens: null,
      duration_ms: 1000,
      created_at: null,
      updated_at: null,
      chronological_interactions: []
    } as unknown as DetailedSession

    const chatFlow = parseSessionChatFlow(mockSession)
    const stats = getChatFlowStats(chatFlow)

    // Note: getChatFlowStats doesn't include summarization count (by design)
    // It's not a core stat for the current implementation
    expect(stats.totalItems).toBe(5) // stage_start + thought + tool_call + summarization + final_answer
    expect(stats.thoughtsCount).toBe(1)
    expect(stats.toolCallsCount).toBe(1)
    expect(stats.finalAnswersCount).toBe(1)
    expect(stats.successfulToolCalls).toBe(1)
  })
})

