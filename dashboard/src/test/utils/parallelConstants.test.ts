import { describe, it, expect } from 'vitest';
import { PARALLEL_TYPE, isParallelType, getParallelTypes } from '../../utils/parallelConstants';

describe('parallelConstants', () => {
  describe('PARALLEL_TYPE', () => {
    it('defines single type', () => {
      expect(PARALLEL_TYPE.SINGLE).toBe('single');
    });

    it('defines multi-agent type', () => {
      expect(PARALLEL_TYPE.MULTI_AGENT).toBe('multi_agent');
    });

    it('defines replica type', () => {
      expect(PARALLEL_TYPE.REPLICA).toBe('replica');
    });

    it('matches backend ParallelType enum values', () => {
      // These values must match backend/tarsy/models/constants.py ParallelType enum
      expect(PARALLEL_TYPE.SINGLE).toBe('single');
      expect(PARALLEL_TYPE.MULTI_AGENT).toBe('multi_agent');
      expect(PARALLEL_TYPE.REPLICA).toBe('replica');
    });
  });

  describe('isParallelType', () => {
    it('returns true for multi_agent', () => {
      expect(isParallelType(PARALLEL_TYPE.MULTI_AGENT)).toBe(true);
    });

    it('returns true for replica', () => {
      expect(isParallelType(PARALLEL_TYPE.REPLICA)).toBe(true);
    });

    it('returns false for single', () => {
      expect(isParallelType(PARALLEL_TYPE.SINGLE)).toBe(false);
    });

    it('returns false for undefined', () => {
      expect(isParallelType(undefined)).toBe(false);
    });

    it('returns false for null', () => {
      expect(isParallelType(null)).toBe(false);
    });

    it('returns false for empty string', () => {
      expect(isParallelType('')).toBe(false);
    });

    it('returns true for any non-empty, non-single string', () => {
      expect(isParallelType('some_other_type')).toBe(true);
    });
  });

  describe('getParallelTypes', () => {
    it('returns array of parallel types excluding single', () => {
      const types = getParallelTypes();
      expect(types).toEqual([PARALLEL_TYPE.MULTI_AGENT, PARALLEL_TYPE.REPLICA]);
    });

    it('returns array with exactly 2 elements', () => {
      const types = getParallelTypes();
      expect(types).toHaveLength(2);
    });

    it('does not include single type', () => {
      const types = getParallelTypes();
      expect(types).not.toContain(PARALLEL_TYPE.SINGLE);
    });

    it('includes multi_agent type', () => {
      const types = getParallelTypes();
      expect(types).toContain(PARALLEL_TYPE.MULTI_AGENT);
    });

    it('includes replica type', () => {
      const types = getParallelTypes();
      expect(types).toContain(PARALLEL_TYPE.REPLICA);
    });
  });
});

