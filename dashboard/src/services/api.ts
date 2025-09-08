import axios, { type AxiosInstance, AxiosError } from 'axios';
import type { SessionsResponse, Session, DetailedSession, SessionFilter, FilterOptions, SearchResult } from '../types';

// API base URL configuration
// In development with Vite proxy, use relative URLs
// In production, use the full URL from environment variables
const API_BASE_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');

class APIClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        console.error('API Error:', error);
        
        if (error.response) {
          // Server responded with error status
          const message = (error.response.data as any)?.error || `Server error: ${error.response.status}`;
          return Promise.reject(new Error(message));
        } else if (error.request) {
          // Network error
          return Promise.reject(new Error('Network error: Unable to connect to server'));
        } else {
          // Other error
          return Promise.reject(new Error('Request failed'));
        }
      }
    );
  }

  /**
   * Fetch all sessions (newest first) - Phase 1 method
   * For Phase 1, we fetch all sessions without pagination
   */
  async getSessions(): Promise<SessionsResponse> {
    try {
      const response = await this.client.get<SessionsResponse>('/api/v1/history/sessions');
      
      // The backend returns the SessionsResponse directly, not wrapped in data
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid response format');
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
      throw error instanceof Error ? error : new Error('Failed to fetch sessions');
    }
  }

  /**
   * Fetch active sessions only (Phase 2)
   * Backend returns a simple array of Session objects
   */
  async getActiveSessions(): Promise<{ active_sessions: Session[], total_count: number }> {
    try {
      const response = await this.client.get<Session[]>('/api/v1/history/active-sessions');
      
      // Debug logging to help troubleshoot filtering issues
      console.log('Active sessions API response:', {
        totalSessions: Array.isArray(response.data) ? response.data.length : 0,
        statuses: Array.isArray(response.data) ? response.data.map((s: any) => s.status) : [],
        url: response.config?.url
      });
      
      // Backend returns a simple array, so we need to wrap it in the expected format
      if (Array.isArray(response.data)) {
        return {
          active_sessions: response.data,
          total_count: response.data.length
        };
      } else {
        throw new Error('Invalid active sessions response format');
      }
    } catch (error) {
      console.error('Failed to fetch active sessions:', error);
      throw error instanceof Error ? error : new Error('Failed to fetch active sessions');
    }
  }

  /**
   * Fetch historical sessions (completed/failed) - Phase 2
   * Gets sessions with status 'completed' or 'failed'
   */
  async getHistoricalSessions(page: number = 1, pageSize: number = 25): Promise<SessionsResponse> {
    try {
      // Build query string manually to ensure proper FastAPI format
      const queryParams = new URLSearchParams();
      queryParams.append('status', 'completed');
      queryParams.append('status', 'failed');
      queryParams.append('page', page.toString());
      queryParams.append('page_size', pageSize.toString());
      const url = `/api/v1/history/sessions?${queryParams.toString()}`;
      
      console.log('🔍 Historical sessions - Full URL:', url);
      
      const response = await this.client.get<SessionsResponse>(url);
      
      // Debug logging to help troubleshoot filtering issues
      console.log('Historical sessions API response:', {
        totalSessions: response.data?.sessions?.length || 0,
        statuses: response.data?.sessions?.map(s => s.status) || [],
        requestedUrl: response.config?.url,
        actualUrl: response.request?.responseURL || 'unknown',
        params: response.config?.params,
        method: response.config?.method,
        rawResponseData: response.data
      });
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid historical sessions response format');
      }
    } catch (error) {
      console.error('Failed to fetch historical sessions:', error);
      throw error instanceof Error ? error : new Error('Failed to fetch historical sessions');
    }
  }

  /**
   * EP-0010: Fetch detailed session data by ID
   * Returns comprehensive session data including alert_data, final_analysis, and stages with embedded interactions
   */
  async getSessionDetail(sessionId: string): Promise<DetailedSession> {
    try {
      const response = await this.client.get<DetailedSession>(`/api/v1/history/sessions/${sessionId}`);
      
      console.log('Session detail API response:', {
        sessionId,
        hasAlertData: !!response.data?.alert_data,
        hasFinalAnalysis: !!response.data?.final_analysis,
        stagesCount: response.data?.stages?.length || 0,
        totalInteractions: response.data?.stages?.reduce(
          (total, stage) => total + (stage.total_interactions || 0), 0
        ) || 0,
        status: response.data?.status
      });
      
      if (response.data && typeof response.data === 'object' && 'session_id' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid session detail response format');
      }
    } catch (error) {
      console.error('Failed to fetch session detail:', error);
      if (error instanceof Error && error.message.includes('404')) {
        throw new Error('Session not found');
      }
      throw error instanceof Error ? error : new Error('Failed to fetch session detail');
    }
  }

  /**
   * Get session summary statistics only (lightweight)
   */
  async getSessionSummary(sessionId: string): Promise<any> {
    try {
      console.log(`📊 Fetching summary statistics for session: ${sessionId}`);
      const response = await this.client.get(`/api/v1/history/sessions/${sessionId}/summary`);
      console.log('📊 Session summary API response:', response.data);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch session summary:', error);
      if (error instanceof Error && error.message.includes('404')) {
        throw new Error('Session not found');
      }
      throw error instanceof Error ? error : new Error('Failed to fetch session summary');
    }
  }

  /**
   * Health check endpoint
   */
  async healthCheck(): Promise<{ status: string }> {
    try {
      const response = await this.client.get('/api/v1/history/health');
      return response.data;
    } catch (error) {
      console.error('Health check failed:', error);
      throw error instanceof Error ? error : new Error('Health check failed');
    }
  }

  // EP-0018: Manual Alert Submission methods

  /**
   * Submit an alert for processing (flexible data structure)
   */
  async submitAlert(alertData: Record<string, any>): Promise<{ alert_id: string; status: string; message: string }> {
    try {
      const response = await this.client.post('/alerts', alertData);
      return response.data;
    } catch (error) {
      console.error('Error submitting alert:', error);
      throw error instanceof Error ? error : new Error('Failed to submit alert');
    }
  }

  /**
   * Get supported alert types for the development/testing web interface dropdown.
   * 
   * NOTE: These alert types are used only for dropdown selection in this
   * development/testing interface. In production, external clients (like Alert Manager)
   * can submit any alert type. The system analyzes all alert types using the provided
   * runbook and all available MCP tools.
   */
  async getAlertTypes(): Promise<string[]> {
    try {
      const response = await this.client.get('/alert-types');
      return response.data;
    } catch (error) {
      console.error('Error getting alert types:', error);
      throw error instanceof Error ? error : new Error('Failed to get alert types');
    }
  }

  /**
   * Get session ID for an alert ID - needed for WebSocket subscription
   * The client needs the session ID (generated later) to subscribe to alert updates
   */
  async getSessionIdForAlert(alertId: string): Promise<{ alert_id: string; session_id: string | null }> {
    try {
      const response = await this.client.get(`/session-id/${alertId}`);
      return response.data;
    } catch (error) {
      console.error('Error getting session ID for alert:', error);
      throw error instanceof Error ? error : new Error('Failed to get session ID for alert');
    }
  }

  // Phase 4: Search and filtering methods

  /**
   * Search sessions by content (Phase 4)
   * Searches across alert types, error messages, and other session content
   */
  async searchSessions(searchTerm: string, limit?: number): Promise<SearchResult> {
    try {
      const params = new URLSearchParams();
      params.append('q', searchTerm);
      if (limit) {
        params.append('limit', limit.toString());
      }
      
      const response = await this.client.get<SessionsResponse>(`/api/v1/history/search?${params.toString()}`);
      
      console.log('Search sessions API response:', {
        searchTerm,
        totalResults: response.data?.sessions?.length || 0,
        limit,
        url: response.config?.url
      });
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        return {
          sessions: response.data.sessions,
          total_count: response.data.sessions.length,
          search_term: searchTerm
        };
      } else {
        throw new Error('Invalid search response format');
      }
    } catch (error) {
      console.error('Failed to search sessions:', error);
      throw error instanceof Error ? error : new Error('Failed to search sessions');
    }
  }

  /**
   * Get available filter options (Phase 4)
   * Returns available values for agent types, alert types, and status options
   */
  async getFilterOptions(): Promise<FilterOptions> {
    try {
      const response = await this.client.get<FilterOptions>('/api/v1/history/filter-options');
      
      console.log('Filter options API response:', {
        agentTypes: response.data?.agent_types?.length || 0,
        alertTypes: response.data?.alert_types?.length || 0,
        statusOptions: response.data?.status_options?.length || 0
      });
      
      if (response.data && typeof response.data === 'object') {
        return response.data;
      } else {
        throw new Error('Invalid filter options response format');
      }
    } catch (error) {
      console.error('Failed to fetch filter options:', error);
      throw error instanceof Error ? error : new Error('Failed to fetch filter options');
    }
  }

  /**
   * Fetch sessions with advanced filtering (Phase 4)
   * Enhanced version of getSessions with comprehensive filtering support
   */
  async getFilteredSessions(filters: SessionFilter, page: number = 1, pageSize: number = 25): Promise<SessionsResponse> {
    try {
      const queryParams = new URLSearchParams();
      
      // Add search parameter (only if 3+ characters to match backend validation)
      if (filters.search && filters.search.trim() && filters.search.trim().length >= 3) {
        queryParams.append('search', filters.search.trim());
      }
      
      // Add status filters (multiple values)
      if (filters.status && filters.status.length > 0) {
        filters.status.forEach(status => {
          queryParams.append('status', status);
        });
      }
      
      // Add agent type filter (single value)
      if (filters.agent_type && filters.agent_type.length > 0) {
        // Backend expects single value, take the first selected value
        queryParams.append('agent_type', filters.agent_type[0]);
      }
      
      // Add alert type filter (single value) 
      if (filters.alert_type && filters.alert_type.length > 0) {
        // Backend expects single value, take the first selected value
        queryParams.append('alert_type', filters.alert_type[0]);
      }
      
      // Add date range filters (convert ISO strings to microseconds)
      if (filters.start_date) {
        const startDateUs = new Date(filters.start_date).getTime() * 1000; // Convert to microseconds
        queryParams.append('start_date_us', startDateUs.toString());
      }
      if (filters.end_date) {
        const endDateUs = new Date(filters.end_date).getTime() * 1000; // Convert to microseconds
        queryParams.append('end_date_us', endDateUs.toString());
      }
      
      // Add pagination parameters
      queryParams.append('page', page.toString());
      queryParams.append('page_size', pageSize.toString());
      
      const url = `/api/v1/history/sessions?${queryParams.toString()}`;
      
      console.log('Filtered sessions API request:', {
        filters,
        url,
        queryParams: queryParams.toString(),
        searchSkipped: filters.search && filters.search.trim() && filters.search.trim().length < 3 ? 
          `Search term "${filters.search.trim()}" too short (< 3 chars)` : false
      });
      
      const response = await this.client.get<SessionsResponse>(url);
      
      console.log('Filtered sessions API response:', {
        totalSessions: response.data?.sessions?.length || 0,
        appliedFilters: filters,
        url: response.config?.url
      });
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid filtered sessions response format');
      }
    } catch (error) {
      console.error('Failed to fetch filtered sessions:', error);
      throw error instanceof Error ? error : new Error('Failed to fetch filtered sessions');
    }
  }
}

// Export singleton instance
export const apiClient = new APIClient();

// Helper function for error handling in components
export const handleAPIError = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}; 