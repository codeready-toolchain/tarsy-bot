import { createContext, useContext } from 'react';
import type { ReactNode, ReactElement } from 'react';
import { useVersionMonitor } from '../hooks/useVersionMonitor';
import type { VersionInfo } from '../hooks/useVersionMonitor';

/**
 * Version context to share version monitoring state across components
 * Prevents duplicate polling by calling useVersionMonitor hook only once
 */
const VersionContext = createContext<VersionInfo | undefined>(undefined);

/**
 * Props for VersionProvider component
 */
interface VersionProviderProps {
  children: ReactNode;
}

/**
 * VersionProvider component
 * 
 * Wraps the application and provides version monitoring state to all children.
 * Polls backend and dashboard versions every 30 seconds and shares the state
 * via context to prevent duplicate API calls.
 * 
 * @param props - Component props
 * @returns Provider component
 */
export function VersionProvider({ children }: VersionProviderProps): ReactElement {
  const versionInfo = useVersionMonitor();
  
  return (
    <VersionContext.Provider value={versionInfo}>
      {children}
    </VersionContext.Provider>
  );
}

/**
 * Custom hook to access version monitoring information
 * 
 * Must be used within a VersionProvider component.
 * 
 * @returns Version monitoring information
 * @throws Error if used outside of VersionProvider
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { backendVersion, dashboardVersionChanged } = useVersion();
 *   // ...
 * }
 * ```
 */
export function useVersion(): VersionInfo {
  const context = useContext(VersionContext);
  
  if (context === undefined) {
    throw new Error('useVersion must be used within a VersionProvider');
  }
  
  return context;
}

