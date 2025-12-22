import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ParallelStageExecutionTabs from '../../components/ParallelStageExecutionTabs';
import type { StageExecution } from '../../types';
import { STAGE_STATUS, type StageStatus } from '../../utils/statusConstants';
import { PARALLEL_TYPE } from '../../utils/parallelConstants';

// Mock data for testing
const createMockParallelStage = (overrides?: Partial<StageExecution>): StageExecution => {
  return {
    execution_id: 'parent-exec-1',
    session_id: 'session-1',
    stage_id: 'investigation',
    stage_index: 0,
    stage_name: 'Investigation',
    agent: 'ParallelInvestigator',
    status: STAGE_STATUS.COMPLETED,
    started_at_us: 1700000000000000,
    paused_at_us: null,
    completed_at_us: 1700000060000000,
    duration_ms: 60000,
    stage_output: null,
    error_message: null,
    llm_interactions: [],
    mcp_communications: [],
    llm_interaction_count: 0,
    mcp_communication_count: 0,
    total_interactions: 0,
    stage_interactions_duration_ms: null,
    chronological_interactions: [],
    parallel_type: PARALLEL_TYPE.MULTI_AGENT,
    parallel_index: 0,
    parent_stage_execution_id: null,
    parallel_executions: [],
    ...overrides,
  };
};

const createMockChildExecution = (
  index: number,
  agent: string,
  status: StageStatus,
  overrides?: Partial<StageExecution>
): StageExecution => {
  return {
    execution_id: `child-exec-${index}`,
    session_id: 'session-1',
    stage_id: 'investigation',
    stage_index: 0,
    stage_name: 'Investigation',
    agent,
    status,
    started_at_us: 1700000000000000 + index * 1000,
    paused_at_us: status === STAGE_STATUS.PAUSED ? 1700000020000000 + index * 1000 : null,
    completed_at_us: status === STAGE_STATUS.COMPLETED ? 1700000030000000 + index * 1000 : null,
    duration_ms: status === STAGE_STATUS.COMPLETED ? 30000 : null,
    stage_output: null,
    error_message: status === STAGE_STATUS.FAILED ? 'Execution failed' : null,
    llm_interactions: [],
    mcp_communications: [],
    llm_interaction_count: 2,
    mcp_communication_count: 1,
    total_interactions: 3,
    stage_interactions_duration_ms: 5000,
    chronological_interactions: [],
    stage_input_tokens: 100,
    stage_output_tokens: 50,
    stage_total_tokens: 150,
    parallel_type: PARALLEL_TYPE.MULTI_AGENT,
    parallel_index: index,
    parent_stage_execution_id: 'parent-exec-1',
    parallel_executions: [],
    ...overrides,
  };
};

describe('ParallelStageExecutionTabs', () => {
  describe('Multi-Agent Parallel Execution', () => {
    let mockStage: StageExecution;

    beforeEach(() => {
      mockStage = createMockParallelStage({
        parallel_executions: [
          createMockChildExecution(1, 'KubernetesAgent', STAGE_STATUS.COMPLETED),
          createMockChildExecution(2, 'VMAgent', STAGE_STATUS.COMPLETED),
          createMockChildExecution(3, 'NetworkAgent', STAGE_STATUS.FAILED),
        ],
      });
    });

    it('renders parallel execution summary', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('Parallel Execution Summary')).toBeInTheDocument();
      expect(screen.getByText('Multi-Agent Mode')).toBeInTheDocument();
    });

    it('displays aggregate status correctly', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('2/3 Completed')).toBeInTheDocument();
    });

    it('shows execution count badges', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('2 completed')).toBeInTheDocument();
      expect(screen.getByText('1 failed')).toBeInTheDocument();
    });

    it('displays aggregate interaction counts', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      // Total LLM interactions: 2 * 3 = 6
      const llmChip = screen.getByText('6');
      expect(llmChip).toBeInTheDocument();

      // Total MCP interactions: 1 * 3 = 3
      const mcpChip = screen.getByText('3');
      expect(mcpChip).toBeInTheDocument();
    });

    it('displays aggregate token usage', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      // Total tokens: 150 * 3 = 450
      expect(screen.getByText('Total Tokens:')).toBeInTheDocument();
    });

    it('renders tabs for each parallel execution', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByRole('tab', { name: /KubernetesAgent/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /VMAgent/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /NetworkAgent/i })).toBeInTheDocument();
    });

    it('allows switching between tabs', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      const vmAgentTab = screen.getByRole('tab', { name: /VMAgent/i });
      fireEvent.click(vmAgentTab);

      // Should now show VMAgent details in the execution details section
      const agentLabels = screen.getAllByText('Agent:');
      expect(agentLabels.length).toBeGreaterThan(0);
    });

    it('displays error message for failed execution', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      const networkAgentTab = screen.getByRole('tab', { name: /NetworkAgent/i });
      fireEvent.click(networkAgentTab);

      expect(screen.getByText(/Execution failed/i)).toBeInTheDocument();
    });
  });

  describe('Replica Parallel Execution', () => {
    let mockStage: StageExecution;

    beforeEach(() => {
      mockStage = createMockParallelStage({
        parallel_type: PARALLEL_TYPE.REPLICA,
        parallel_executions: [
          createMockChildExecution(1, 'KubernetesAgent', STAGE_STATUS.COMPLETED, {
            parallel_type: PARALLEL_TYPE.REPLICA,
          }),
          createMockChildExecution(2, 'KubernetesAgent', STAGE_STATUS.COMPLETED, {
            parallel_type: PARALLEL_TYPE.REPLICA,
          }),
          createMockChildExecution(3, 'KubernetesAgent', STAGE_STATUS.COMPLETED, {
            parallel_type: PARALLEL_TYPE.REPLICA,
          }),
        ],
      });
    });

    it('shows replica mode label', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('Replica Mode')).toBeInTheDocument();
    });

    it('displays "All Completed" for all successful replicas', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('All Completed')).toBeInTheDocument();
    });

    it('labels replica tabs correctly', () => {
      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByRole('tab', { name: /KubernetesAgent-1/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /KubernetesAgent-2/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /KubernetesAgent-3/i })).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('shows warning when no parallel executions exist', () => {
      const mockStage = createMockParallelStage({
        parallel_executions: [],
      });

      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('No parallel executions found for this stage.')).toBeInTheDocument();
    });

    it('shows warning for non-parallel stage', () => {
      const mockStage = createMockParallelStage({
        parallel_type: PARALLEL_TYPE.SINGLE,
        parallel_executions: undefined,
      });

      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('No parallel executions found for this stage.')).toBeInTheDocument();
    });

    it('handles stages with no token data', () => {
      const mockStage = createMockParallelStage({
        parallel_executions: [
          createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, {
            stage_input_tokens: null,
            stage_output_tokens: null,
            stage_total_tokens: null,
          }),
        ],
      });

      render(<ParallelStageExecutionTabs stage={mockStage} />);

      // Should not show token usage section
      expect(screen.queryByText('Total Tokens:')).not.toBeInTheDocument();
    });

    it('handles stages with no interactions', () => {
      const mockStage = createMockParallelStage({
        parallel_executions: [
          createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, {
            llm_interaction_count: 0,
            mcp_communication_count: 0,
            total_interactions: 0,
            llm_interactions: [],
            mcp_communications: [],
          }),
        ],
      });

      render(<ParallelStageExecutionTabs stage={mockStage} />);

      // First tab should be visible by default
      expect(screen.getByText('No interactions recorded for this execution')).toBeInTheDocument();
    });
  });

  describe('Mixed Status Scenarios', () => {
    it('displays correct status for partially completed parallel execution', () => {
      const mockStage = createMockParallelStage({
        parallel_executions: [
          createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED),
          createMockChildExecution(2, 'Agent2', STAGE_STATUS.ACTIVE),
          createMockChildExecution(3, 'Agent3', STAGE_STATUS.PENDING),
        ],
      });

      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('1/3 Completed')).toBeInTheDocument();
      expect(screen.getByText('1 completed')).toBeInTheDocument();
      expect(screen.getByText('1 running')).toBeInTheDocument();
      expect(screen.getByText('1 pending')).toBeInTheDocument();
    });

    it('displays "All Failed" when all executions fail', () => {
      const mockStage = createMockParallelStage({
        parallel_executions: [
          createMockChildExecution(1, 'Agent1', STAGE_STATUS.FAILED),
          createMockChildExecution(2, 'Agent2', STAGE_STATUS.FAILED),
        ],
      });

      render(<ParallelStageExecutionTabs stage={mockStage} />);

      expect(screen.getByText('All Failed')).toBeInTheDocument();
      expect(screen.getByText('2 failed')).toBeInTheDocument();
    });
  });
});

