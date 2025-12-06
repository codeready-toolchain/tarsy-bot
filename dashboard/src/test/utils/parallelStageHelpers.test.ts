import { describe, it, expect } from 'vitest';
import {
  isParallelStage,
  getParallelStageLabel,
  getAggregateStatus,
  getSuccessFailureCounts,
  getTotalTokenUsage,
  getAggregateDuration,
  getAggregateInteractionCounts,
} from '../../utils/parallelStageHelpers';
import {
  createMockParallelStage,
  createMockChildExecution,
  createSingleStage,
  createMultiAgentParallelStage,
  createReplicaParallelStage,
} from './parallelStageMocks';
import { STAGE_STATUS } from '../../utils/statusConstants';
import { PARALLEL_TYPE } from '../../utils/parallelConstants';

describe('parallelStageHelpers', () => {
  describe('isParallelStage', () => {
    it('returns true for stage with parallel_executions array', () => {
      const stage = createMockParallelStage({
        parallel_executions: [
          createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED),
        ],
      });
      expect(isParallelStage(stage)).toBe(true);
    });

    it('returns true for stage with non-single parallel_type', () => {
      const stage = createMockParallelStage({
        parallel_type: PARALLEL_TYPE.MULTI_AGENT,
        parallel_executions: [],
      });
      expect(isParallelStage(stage)).toBe(true);
    });

    it('returns false for single stage', () => {
      const stage = createSingleStage();
      expect(isParallelStage(stage)).toBe(false);
    });

    it('returns false for stage with undefined parallel_executions and single type', () => {
      const stage = createSingleStage({
        parallel_type: PARALLEL_TYPE.SINGLE,
        parallel_executions: undefined,
      });
      expect(isParallelStage(stage)).toBe(false);
    });
  });

  describe('getParallelStageLabel', () => {
    it('generates replica label for replica type', () => {
      const stage = createMockChildExecution(1, 'KubernetesAgent', STAGE_STATUS.COMPLETED);
      const label = getParallelStageLabel(stage, 0, PARALLEL_TYPE.REPLICA);
      expect(label).toBe('KubernetesAgent-1');
    });

    it('generates multi-agent label for multi_agent type', () => {
      const stage = createMockChildExecution(1, 'KubernetesAgent', STAGE_STATUS.COMPLETED);
      const label = getParallelStageLabel(stage, 0, PARALLEL_TYPE.MULTI_AGENT);
      expect(label).toBe('KubernetesAgent');
    });

    it('defaults to multi-agent format', () => {
      const stage = createMockChildExecution(1, 'VMAgent', STAGE_STATUS.COMPLETED);
      const label = getParallelStageLabel(stage, 0);
      expect(label).toBe('VMAgent');
    });
  });

  describe('getAggregateStatus', () => {
    it('returns "All Completed" when all executions completed', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.COMPLETED),
      ];
      expect(getAggregateStatus(executions)).toBe('All Completed');
    });

    it('returns "All Failed" when all executions failed', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.FAILED),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.FAILED),
      ];
      expect(getAggregateStatus(executions)).toBe('All Failed');
    });

    it('returns "X/Y Completed" for partial completion', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.COMPLETED),
        createMockChildExecution(3, 'Agent3', STAGE_STATUS.FAILED),
      ];
      expect(getAggregateStatus(executions)).toBe('2/3 Completed');
    });

    it('returns "X/Y Running" for active executions', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.ACTIVE),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.PENDING),
      ];
      expect(getAggregateStatus(executions)).toBe('1/2 Running');
    });

    it('returns "No executions" for empty array', () => {
      expect(getAggregateStatus([])).toBe('No executions');
    });
  });

  describe('getSuccessFailureCounts', () => {
    it('counts executions by status correctly', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.COMPLETED),
        createMockChildExecution(3, 'Agent3', STAGE_STATUS.FAILED),
        createMockChildExecution(4, 'Agent4', STAGE_STATUS.ACTIVE),
        createMockChildExecution(5, 'Agent5', STAGE_STATUS.PENDING),
      ];

      const counts = getSuccessFailureCounts(executions);
      expect(counts.completed).toBe(2);
      expect(counts.failed).toBe(1);
      expect(counts.active).toBe(1);
      expect(counts.pending).toBe(1);
      expect(counts.total).toBe(5);
    });

    it('returns zero counts for empty array', () => {
      const counts = getSuccessFailureCounts([]);
      expect(counts.completed).toBe(0);
      expect(counts.failed).toBe(0);
      expect(counts.active).toBe(0);
      expect(counts.pending).toBe(0);
      expect(counts.total).toBe(0);
    });
  });

  describe('getTotalTokenUsage', () => {
    it('sums token usage across all executions', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, {
          stage_input_tokens: 100,
          stage_output_tokens: 50,
          stage_total_tokens: 150,
        }),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.COMPLETED, {
          stage_input_tokens: 200,
          stage_output_tokens: 100,
          stage_total_tokens: 300,
        }),
      ];

      const total = getTotalTokenUsage(executions);
      expect(total.input_tokens).toBe(300);
      expect(total.output_tokens).toBe(150);
      expect(total.total_tokens).toBe(450);
    });

    it('returns null values when no token data available', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, {
          stage_input_tokens: null,
          stage_output_tokens: null,
          stage_total_tokens: null,
        }),
      ];

      const total = getTotalTokenUsage(executions);
      expect(total.input_tokens).toBeNull();
      expect(total.output_tokens).toBeNull();
      expect(total.total_tokens).toBeNull();
    });

    it('handles partial token data', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, {
          stage_input_tokens: 100,
          stage_output_tokens: null,
          stage_total_tokens: null,
        }),
      ];

      const total = getTotalTokenUsage(executions);
      expect(total.input_tokens).toBe(100);
      expect(total.output_tokens).toBeNull();
      expect(total.total_tokens).toBeNull();
    });
  });

  describe('getAggregateDuration', () => {
    it('returns maximum duration from parallel executions', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, { duration_ms: 10000 }),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.COMPLETED, { duration_ms: 25000 }),
        createMockChildExecution(3, 'Agent3', STAGE_STATUS.COMPLETED, { duration_ms: 15000 }),
      ];

      const duration = getAggregateDuration(executions);
      expect(duration).toBe(25000);
    });

    it('returns null when no duration data available', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.ACTIVE, { duration_ms: null }),
      ];

      const duration = getAggregateDuration(executions);
      expect(duration).toBeNull();
    });
  });

  describe('getAggregateInteractionCounts', () => {
    it('sums interaction counts across all executions', () => {
      const executions = [
        createMockChildExecution(1, 'Agent1', STAGE_STATUS.COMPLETED, {
          llm_interaction_count: 5,
          mcp_communication_count: 3,
        }),
        createMockChildExecution(2, 'Agent2', STAGE_STATUS.COMPLETED, {
          llm_interaction_count: 2,
          mcp_communication_count: 4,
        }),
      ];

      const counts = getAggregateInteractionCounts(executions);
      expect(counts.llm_count).toBe(7);
      expect(counts.mcp_count).toBe(7);
      expect(counts.total_count).toBe(14);
    });

    it('returns zero counts for empty array', () => {
      const counts = getAggregateInteractionCounts([]);
      expect(counts.llm_count).toBe(0);
      expect(counts.mcp_count).toBe(0);
      expect(counts.total_count).toBe(0);
    });
  });

  describe('Integration with mock factories', () => {
    it('works with createMultiAgentParallelStage', () => {
      const stage = createMultiAgentParallelStage();
      
      expect(isParallelStage(stage)).toBe(true);
      expect(stage.parallel_executions).toHaveLength(3);
      
      const counts = getSuccessFailureCounts(stage.parallel_executions!);
      expect(counts.completed).toBe(2);
      expect(counts.failed).toBe(1);
    });

    it('works with createReplicaParallelStage', () => {
      const stage = createReplicaParallelStage('TestAgent', 4);
      
      expect(isParallelStage(stage)).toBe(true);
      expect(stage.parallel_type).toBe('replica');
      expect(stage.parallel_executions).toHaveLength(4);
      
      const status = getAggregateStatus(stage.parallel_executions!);
      expect(status).toBe('All Completed');
    });
  });
});

