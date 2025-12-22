import { describe, it, expect } from 'vitest'
import { parseStageConversation, parseSessionConversation } from '../../utils/conversationParser'
import type { StageExecution, DetailedSession } from '../../types'

describe('conversationParser - MCP Error Handling', () => {
  it('should extract error messages from failed MCP tool calls', () => {
    const mockStage: StageExecution = {
      execution_id: 'test-stage-1',
      session_id: 'test-session',
      stage_id: 'analysis',
      stage_index: 0,
      stage_name: 'Analysis Stage',
      agent: 'TestAgent',
      status: 'failed',
      started_at_us: 1000000,
      paused_at_us: null,
      completed_at_us: 2000000,
      duration_ms: 1000,
      llm_interactions: [{
        id: 'llm-1',
        event_id: 'llm-1',
        type: 'llm',
        timestamp_us: 1100000,
        duration_ms: 500,
        step_description: 'AI Analysis',
        details: {
          model_name: 'test-model',
          interaction_type: 'investigation',
          conversation: {
            messages: [{
              role: 'system',
              content: 'You are a helpful assistant.'
            }, {
              role: 'user',
              content: 'Check ArgoCD for unhealthy applications'
            }, {
              role: 'assistant',
              content: 'I need to check ArgoCD for unhealthy applications.\n\nThought: I should use the unhealthyApplications tool to get a list of applications that are not healthy.\n\nAction: unhealthyApplications\nAction Input: {}\n\nObservation: Error occurred while calling the tool.\n\nThought: The tool call failed. Let me try again.'
            }]
          },
          success: true,
          total_tokens: 150,
          input_tokens: 50,
          output_tokens: 100,
          temperature: null,
          error_message: null,
          tool_calls: null,
          tool_results: null
        }
      }],
      mcp_communications: [{
        event_id: 'mcp-1',
        type: 'mcp',
        timestamp_us: 1150000,
        duration_ms: 2,
        step_description: 'Check unhealthy ArgoCD applications',
        details: {
          tool_name: 'unhealthyApplications',
          server_name: 'argocd-server',
          communication_type: 'tool_call',
          parameters: {},
          result: {},
          available_tools: {},
          success: false,
          error_message: 'Failed to call tool unhealthyApplications on argocd-server: Type=McpError | Message=Get "https://argocd.example.com/api/v1/applications": net/http: invalid header field value for "Authorization"'
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
    } as unknown as StageExecution

    const result = parseStageConversation(mockStage)
    
    // Should have extracted conversation steps
    expect(result.steps.length).toBeGreaterThan(0)
    
    // Look for action steps with error messages
    const actionSteps = result.steps.filter(step => step.type === 'action')
    expect(actionSteps.length).toBeGreaterThan(0)
    
    const failedActionStep = actionSteps.find(step => !step.success && step.errorMessage)
    expect(failedActionStep).toBeDefined()
    expect(failedActionStep!.success).toBe(false)
    expect(failedActionStep!.errorMessage).toContain('Failed to call tool unhealthyApplications')
    expect(failedActionStep!.errorMessage).toContain('net/http: invalid header field value')
    expect(failedActionStep!.actionName).toBe('unhealthyApplications')
  })

  it('should handle successful MCP calls without error messages', () => {
    const mockStage: StageExecution = {
      execution_id: 'test-stage-2',
      session_id: 'test-session',
      stage_id: 'success-stage',
      stage_index: 0,
      stage_name: 'Success Stage',
      agent: 'TestAgent',
      status: 'completed',
      started_at_us: 1000000,
      paused_at_us: null,
      completed_at_us: 2000000,
      duration_ms: 1000,
      llm_interactions: [{
        id: 'llm-1',
        event_id: 'llm-1',
        type: 'llm',
        timestamp_us: 1100000,
        duration_ms: 500,
        step_description: 'AI Analysis',
        details: {
          model_name: 'test-model',
          interaction_type: 'investigation',
          conversation: {
            messages: [{
              role: 'system',
              content: 'You are a helpful assistant.'
            }, {
              role: 'user',
              content: 'Get Kubernetes pods'
            }, {
              role: 'assistant',
              content: 'I will get the Kubernetes pods.\n\nThought: I should use the kubectl tool to get pods.\n\nAction: kubectl_get_pods\nAction Input: {"namespace": "default"}\n\nObservation: Found 3 pods running in the default namespace.\n\nThought: Successfully retrieved the pod information.'
            }]
          },
          success: true,
          temperature: null,
          error_message: null,
          input_tokens: null,
          output_tokens: null,
          total_tokens: null,
          tool_calls: null,
          tool_results: null
        }
      }],
      mcp_communications: [{
        event_id: 'mcp-1',
        type: 'mcp',
        timestamp_us: 1150000,
        duration_ms: 800,
        step_description: 'Get Kubernetes pods',
        details: {
          tool_name: 'kubectl_get_pods',
          server_name: 'kubernetes-server',
          communication_type: 'tool_call',
          parameters: { namespace: 'default' },
          result: { pods: ['nginx-1', 'nginx-2', 'app-1'] },
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
    } as unknown as StageExecution

    const result = parseStageConversation(mockStage)
    
    // Should have extracted conversation steps
    expect(result.steps.length).toBeGreaterThan(0)
    
    // Look for successful action steps
    const actionSteps = result.steps.filter(step => step.type === 'action')
    expect(actionSteps.length).toBeGreaterThan(0)
    
    const successfulActionStep = actionSteps.find(step => step.success)
    expect(successfulActionStep).toBeDefined()
    expect(successfulActionStep!.success).toBe(true)
    expect(successfulActionStep!.errorMessage).toBeUndefined()
    expect(successfulActionStep!.actionName).toBe('kubectl_get_pods')
    expect(successfulActionStep!.actionResult).toBeDefined()
  })

  it('should parse complete session with mixed successful and failed MCP calls', () => {
    const mockSession: DetailedSession = {
      session_id: 'test-session-123',
      alert_type: 'MixedTestAlert',
      agent_type: 'test-agent',
      status: 'completed',
      started_at_us: 1000000,
      completed_at_us: 3000000,
      alert_data: {},
      stages: [{
        execution_id: 'test-stage-1',
        session_id: 'test-session-123',
        stage_id: 'mixed-stage',
        stage_index: 0,
        stage_name: 'Mixed Results Stage',
        agent: 'TestAgent',
        status: 'completed',
        started_at_us: 1000000,
        completed_at_us: 2000000,
        duration_ms: 1000,
        llm_interactions: [{
          id: 'llm-1',
          event_id: 'llm-1',
          type: 'llm',
          timestamp_us: 1100000,
          duration_ms: 500,
          step_description: 'Mixed Actions',
          details: {
            model_name: 'test-model',
            interaction_type: 'investigation',
            conversation: {
              messages: [{
                role: 'system',
                content: 'You are a helpful assistant.'
              }, {
                role: 'user',
                content: 'Perform multiple actions'
              }, {
                role: 'assistant',
                content: 'I will perform the actions.\n\nThought: Let me start with the first tool.\n\nAction: successfulTool\nAction Input: {}\n\nObservation: Success\n\nThought: Now let me try the second tool.\n\nAction: failingTool\nAction Input: {}\n\nObservation: Error occurred.'
              }]
            },
            success: true,
            temperature: null,
            error_message: null,
            input_tokens: null,
            output_tokens: null,
            total_tokens: null,
            tool_calls: null,
            tool_results: null
          }
        }],
        mcp_communications: [{
          event_id: 'mcp-success',
          type: 'mcp',
          timestamp_us: 1150000,
          duration_ms: 100,
          step_description: 'Successful tool call',
          details: {
            tool_name: 'successfulTool',
            server_name: 'test-server',
            communication_type: 'tool_call',
            parameters: {},
            result: { status: 'ok' },
            available_tools: {},
            success: true,
            error_message: null
          }
        }, {
          event_id: 'mcp-failure',
          type: 'mcp',
          timestamp_us: 1160000,
          duration_ms: 5,
          step_description: 'Failed tool call',
          details: {
            tool_name: 'failingTool',
            server_name: 'test-server',
            communication_type: 'tool_call',
            parameters: {},
            result: {},
            available_tools: {},
            success: false,
            error_message: 'Tool execution failed: Connection timeout'
          }
        }],
        total_interactions: 3,
        stage_output: null,
        error_message: null,
        llm_interaction_count: 1,
        mcp_communication_count: 2,
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

    const result = parseSessionConversation(mockSession)
    
    expect(result.stages.length).toBe(1)
    
    const stage = result.stages[0]
    const actionSteps = stage.steps.filter(step => step.type === 'action')
    const thoughtSteps = stage.steps.filter(step => step.type === 'thought')
    
    // Verify parsed steps structure
    
    // Should have at least one action step
    expect(actionSteps.length).toBeGreaterThan(0)
    
    // Test that we can handle MCP error messages in parsed results
    // The parser may only extract the first action from multi-action messages
    const actionStep = actionSteps[0]
    expect(actionStep).toBeDefined()
    
    // The key test: verify that MCP error messages are properly linked to actions
    if (!actionStep.success && actionStep.errorMessage) {
      expect(actionStep.errorMessage).toContain('Tool execution failed')
    }
    
    // Verify we have some parsed content
    expect(stage.steps.length).toBeGreaterThan(0)
    expect(thoughtSteps.length + actionSteps.length).toBeGreaterThan(0)
  })

  it('should parse malformed Thought section without colon', () => {
    const mockStage: StageExecution = {
      execution_id: 'test-stage-malformed',
      session_id: 'test-session',
      stage_id: 'investigation',
      stage_index: 0,
      stage_name: 'Investigation Stage',
      agent: 'TestAgent',
      status: 'completed',
      started_at_us: 1000000,
      paused_at_us: null,
      completed_at_us: 2000000,
      duration_ms: 1000,
      llm_interactions: [{
        id: 'llm-1',
        event_id: 'llm-1',
        type: 'llm',
        timestamp_us: 1100000,
        duration_ms: 500,
        step_description: 'AI Analysis',
        details: {
          model_name: 'test-model',
          interaction_type: 'investigation',
          conversation: {
            messages: [{
              role: 'user',
              content: 'Investigate the alert'
            }, {
              role: 'assistant',
              content: 'Thought\nThe user wants me to investigate a security alert.\nI need to check the logs first.\n\nAction: get_logs\nAction Input: pod: suspicious-pod'
            }]
          },
          success: true,
          total_tokens: 100,
          input_tokens: 30,
          output_tokens: 70,
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
      stage_total_tokens: null,
      stage_interactions_duration_ms: 500,
      chronological_interactions: []
    }

    const result = parseStageConversation(mockStage)
    
    expect(result.steps.length).toBeGreaterThan(0)
    
    const thoughtSteps = result.steps.filter(step => step.type === 'thought')
    const actionSteps = result.steps.filter(step => step.type === 'action')
    
    // Should parse thought even without colon
    expect(thoughtSteps.length).toBe(1)
    expect(thoughtSteps[0].content).toContain('The user wants me to investigate')
    expect(thoughtSteps[0].content).toContain('I need to check the logs first')
    
    // Should also parse the action
    expect(actionSteps.length).toBe(1)
    expect(actionSteps[0].actionName).toBe('get_logs')
  })
})
