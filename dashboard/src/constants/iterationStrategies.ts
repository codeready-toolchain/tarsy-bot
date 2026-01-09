/**
 * Iteration Strategy Constants
 * 
 * These constants define the different agent iteration strategies used in TARSy.
 */

/**
 * Iteration strategy types
 */
export const ITERATION_STRATEGIES = {
  REACT: 'react',
  NATIVE_THINKING: 'native-thinking',
  SYNTHESIS_NATIVE_THINKING: 'synthesis-native-thinking',
} as const;

/**
 * Type for iteration strategy values
 */
export type IterationStrategy = typeof ITERATION_STRATEGIES[keyof typeof ITERATION_STRATEGIES];

/**
 * Check if a strategy is native thinking based
 */
export function isNativeThinkingStrategy(strategy: string | null | undefined): boolean {
  return strategy === ITERATION_STRATEGIES.NATIVE_THINKING || 
         strategy === ITERATION_STRATEGIES.SYNTHESIS_NATIVE_THINKING;
}
