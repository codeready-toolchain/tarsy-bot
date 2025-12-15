/**
 * Constants for parallel stage execution types
 * Must match backend ParallelType enum in backend/tarsy/models/constants.py
 */

export const PARALLEL_TYPE = {
  SINGLE: 'single',
  MULTI_AGENT: 'multi_agent',
  REPLICA: 'replica',
} as const;

export type ParallelType = typeof PARALLEL_TYPE[keyof typeof PARALLEL_TYPE];

/**
 * Check if a parallel type represents actual parallelism (not single)
 */
export function isParallelType(parallelType: string | undefined | null): boolean {
  return parallelType !== undefined && 
         parallelType !== null && 
         parallelType !== '' &&
         parallelType !== PARALLEL_TYPE.SINGLE;
}

/**
 * Get all parallel types (excluding single)
 */
export function getParallelTypes(): string[] {
  return [PARALLEL_TYPE.MULTI_AGENT, PARALLEL_TYPE.REPLICA];
}

