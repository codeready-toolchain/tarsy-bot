import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../services/api';
import { DASHBOARD_VERSION } from '../config/env';

/**
 * Version information returned by the hook
 */
export interface VersionInfo {
  /**
   * Current backend version from latest poll
   */
  backendVersion: string | null;
  
  /**
   * Backend health status from latest poll
   */
  backendStatus: string;
  
  /**
   * Whether dashboard version has changed (requires 2 consecutive mismatches)
   */
  dashboardVersionChanged: boolean;
  
  /**
   * Function to manually refresh version info
   */
  refresh: () => Promise<void>;
}

/**
 * Custom hook to monitor backend and dashboard versions
 * 
 * Periodically polls:
 * - Backend version from /health endpoint (updates live in footer)
 * - Dashboard version from index.html meta tag (triggers banner after 2 consecutive mismatches)
 * 
 * Polling interval: 30 seconds for both
 * Consecutive detection: 2 mismatches (60s) before showing dashboard update banner
 * 
 * @returns Version monitoring information and control functions
 * 
 * @example
 * ```tsx
 * const { 
 *   backendVersion, 
 *   backendStatus,
 *   dashboardVersionChanged,
 *   refresh 
 * } = useVersionMonitor();
 * 
 * if (dashboardVersionChanged) {
 *   return <UpdateBanner onRefresh={() => window.location.reload()} />;
 * }
 * ```
 */
export function useVersionMonitor(): VersionInfo {
  const POLL_INTERVAL_MS = 30000; // 30 seconds
  const REQUIRED_CONSECUTIVE_MISMATCHES = 2; // 60 seconds total
  
  // Backend version state (updates live)
  const [backendVersion, setBackendVersion] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<string>('checking');
  
  // Dashboard version detection state
  const [consecutiveMismatches, setConsecutiveMismatches] = useState<number>(0);
  const [dashboardVersionChanged, setDashboardVersionChanged] = useState<boolean>(false);
  
  // Track initial load
  const isInitialMount = useRef<boolean>(true);
  
  /**
   * Fetch backend version from health endpoint
   * Updates live - no consecutive detection needed
   */
  const fetchBackendVersion = useCallback(async () => {
    try {
      const health: { status: string; version?: string; [key: string]: any } = await apiClient.healthCheck();
      const version = health.version || 'unknown';
      
      setBackendVersion(version);
      setBackendStatus(health.status || 'unknown');
    } catch (error) {
      console.error('Failed to fetch backend version:', error);
      // Keep last known version on error
      setBackendStatus('error');
    }
  }, []);
  
  /**
   * Check dashboard version by fetching index.html and parsing meta tag
   * Uses consecutive detection to avoid flicker during rolling updates
   */
  const checkDashboardVersion = useCallback(async () => {
    try {
      // Fetch index.html with cache-busting query param
      const response = await fetch(`/index.html?_=${Date.now()}`, {
        cache: 'no-cache',
        headers: {
          'Cache-Control': 'no-cache',
        },
      });
      
      if (!response.ok) {
        return;
      }
      
      const html = await response.text();
      
      // Extract version from meta tag
      const versionMatch = html.match(/<meta\s+name=["']app-version["']\s+content=["']([^"']+)["']/i);
      const fetchedVersion = versionMatch?.[1];
      
      if (!fetchedVersion || fetchedVersion === '__APP_VERSION__') {
        // Version not injected yet (dev mode) or parsing failed
        return;
      }
      
      // Compare with current JS version
      if (fetchedVersion !== DASHBOARD_VERSION) {
        // Version mismatch detected
        setConsecutiveMismatches(prev => {
          const newCount = prev + 1;
          
          // Trigger banner after required consecutive mismatches
          if (newCount >= REQUIRED_CONSECUTIVE_MISMATCHES && !isInitialMount.current) {
            setDashboardVersionChanged(true);
            console.info(`🆕 Dashboard version changed: ${DASHBOARD_VERSION} → ${fetchedVersion}`);
          }
          
          return newCount;
        });
      } else {
        // Version matches - reset counter
        if (consecutiveMismatches > 0) {
          setConsecutiveMismatches(0);
        }
      }
    } catch (error) {
      // Silently fail - this is optional monitoring
    }
  }, [consecutiveMismatches]);
  
  /**
   * Refresh both backend and dashboard version information
   */
  const refresh = useCallback(async () => {
    await Promise.all([
      fetchBackendVersion(),
      checkDashboardVersion(),
    ]);
  }, [fetchBackendVersion, checkDashboardVersion]);
  
  // Initial fetch on mount
  useEffect(() => {
    refresh();
    
    // Mark initial mount as complete after first poll
    const timer = setTimeout(() => {
      isInitialMount.current = false;
    }, 1000);
    
    return () => clearTimeout(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  
  // Set up polling interval
  useEffect(() => {
    const intervalId = setInterval(() => {
      refresh();
    }, POLL_INTERVAL_MS);
    
    return () => clearInterval(intervalId);
  }, [refresh, POLL_INTERVAL_MS]);
  
  return {
    backendVersion,
    backendStatus,
    dashboardVersionChanged,
    refresh,
  };
}

