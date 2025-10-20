import axios, { type AxiosInstance, AxiosError } from 'axios';
import type { SessionsResponse, Session, DetailedSession, SessionFilter, FilterOptions, SearchResult, SystemWarning } from '../types';
import { authService } from './auth';

// API base URL configuration  
// In development, use Vite proxy (relative URLs) to handle CORS with OAuth2 proxy
// In production, use the full URL from environment variables
import { urls } from '../config/env';

const API_BASE_URL = urls.api.base;

class APIClient {
  private client: AxiosInstance;
  private readonly INITIAL_RETRY_DELAY = 500; // ms
  private readonly MAX_RETRY_DELAY = 5000; // ms - cap at 5 seconds

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000,
      withCredentials: true, // Important: include cookies for OAuth2 proxy
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    // Add response interceptor for error handling and authentication
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        // Log API errors for debugging
        if (error.response?.status && error.response.status >= 400) {
          console.warn(`API Error ${error.response.status}:`, {
            method: error.config?.method?.toUpperCase(),
            url: error.config?.url,
            status: error.response.status,
            message: error.message,
          });
        }
        
        // Handle 401 Unauthorized - redirect to OAuth login
        if (error.response?.status === 401) {
          authService.handleAuthError();
          return Promise.reject(error);
        }
        
        // Handle network errors (pod restart, backend down, etc.)
        // Do NOT treat these as auth errors - the session may still be valid
        // Only 401 responses indicate actual authentication failures
        if (error.request && !error.response) {
          console.warn('Network error - backend may be restarting:', {
            url: error.config?.url,
            message: error.message,
          });
          // Let the error propagate without triggering re-authentication
          // The UI should show a temporary error, not redirect to login
        }
        
        return Promise.reject(error);
      }
    );
  }

  /**
   * Retry wrapper for temporary errors with exponential backoff (capped)
   * Used during backend restarts to automatically retry failed requests
   * Retries indefinitely until success or non-retryable error
   */
  private async retryOnTemporaryError<T>(
    operation: () => Promise<T>,
    operationName: string = 'API call'
  ): Promise<T> {
    let attempt = 0;
    
    while (true) {
      try {
        return await operation();
      } catch (error) {
        // Determine if this is a retryable error
        let isRetryable = false;
        
        if (error && typeof error === 'object' && 'isAxiosError' in error) {
          const axiosError = error as AxiosError;
          
          // Retry on network errors (no response from server - backend down/restarting)
          if (axiosError.request && !axiosError.response) {
            isRetryable = true;
          }
          
          // Retry on 502 Bad Gateway (proxy/routing issues during restart)
          // Retry on 503 Service Unavailable (backend starting up)
          if (axiosError.response?.status === 502 || axiosError.response?.status === 503) {
            isRetryable = true;
          }
        }
        
        // If not retryable, fail immediately
        if (!isRetryable) {
          throw error;
        }
        
        // Calculate exponential backoff delay with cap at MAX_RETRY_DELAY
        const exponentialDelay = this.INITIAL_RETRY_DELAY * Math.pow(2, attempt);
        const delay = Math.min(exponentialDelay, this.MAX_RETRY_DELAY);
        console.log(`🔄 ${operationName} failed, retrying in ${delay}ms... (attempt ${attempt + 1})`);
        
        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, delay));
        attempt++;
      }
    }
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
      throw error;
    }
  }

  /**
   * Fetch active sessions only (Phase 2)
   * Backend returns a simple array of Session objects
   */
  async getActiveSessions(): Promise<{ active_sessions: Session[], total_count: number }> {
    try {
      const response = await this.client.get<Session[]>('/api/v1/history/active-sessions');
      
      // Active sessions fetched successfully
      
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
      throw error;
    }
  }

  /**
   * Fetch active sessions with automatic retry on temporary errors
   * Used during reconnection to handle backend startup delays
   * Retries indefinitely on network/502/503 errors until backend is ready
   */
  async getActiveSessionsWithRetry(): Promise<{ active_sessions: Session[], total_count: number }> {
    return this.retryOnTemporaryError(
      () => this.getActiveSessions(),
      'Get active sessions'
    );
  }

  /**
   * Fetch historical sessions with automatic retry on temporary errors
   * Used during reconnection to handle backend startup delays
   * Retries indefinitely on network/502/503 errors until backend is ready
   */
  async getHistoricalSessionsWithRetry(page: number = 1, pageSize: number = 25): Promise<SessionsResponse> {
    return this.retryOnTemporaryError(
      () => this.getHistoricalSessions(page, pageSize),
      'Get historical sessions'
    );
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
      
      
      const response = await this.client.get<SessionsResponse>(url);
      
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid historical sessions response format');
      }
    } catch (error) {
      console.error('Failed to fetch historical sessions:', error);
      throw error;
    }
  }

  /**
   * EP-0010: Fetch detailed session data by ID
   * Returns comprehensive session data including alert_data, final_analysis, and stages with embedded interactions
   */
  async getSessionDetail(sessionId: string): Promise<DetailedSession> {
    try {
      const response = await this.client.get<DetailedSession>(`/api/v1/history/sessions/${sessionId}`);
      
      // Session detail fetched successfully
      
      if (response.data && typeof response.data === 'object' && 'session_id' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid session detail response format');
      }
    } catch (error) {
      console.error('Failed to fetch session detail:', error);
      if (axios.isAxiosError?.(error) && error.response?.status === 404) {
        throw new Error('Session not found');
      }
      throw error;
    }
  }

  /**
   * Get session summary statistics only (lightweight)
   */
  async getSessionSummary(sessionId: string): Promise<any> {
    try {
      const response = await this.client.get(`/api/v1/history/sessions/${sessionId}/summary`);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch session summary:', error);
      if (axios.isAxiosError?.(error) && error.response?.status === 404) {
        throw new Error('Session not found');
      }
      throw error;
    }
  }

  /**
   * Health check endpoint
   */
  async healthCheck(): Promise<{ status: string; version?: string; [key: string]: any }> {
    try {
      const response = await this.client.get('/health');
      return response.data;
    } catch (error) {
      console.error('Health check failed:', error);
      throw error;
    }
  }

  /**
   * Get system warnings
   * Returns active system warnings (MCP failures, runbook service issues, etc.)
   */
  async getSystemWarnings(): Promise<SystemWarning[]> {
    try {
      const response = await this.client.get<SystemWarning[]>('/api/v1/system/warnings');
      
      if (Array.isArray(response.data)) {
        return response.data;
      } else {
        throw new Error('Invalid system warnings response format');
      }
    } catch (error) {
      console.error('Failed to fetch system warnings:', error);
      throw error;
    }
  }

  // EP-0018: Manual Alert Submission methods

  /**
   * Submit an alert for processing (flexible data structure)
   */
  async submitAlert(alertData: Record<string, any>): Promise<{ session_id: string; status: string; message: string }> {
    try {
      const response = await this.client.post(urls.api.submitAlert, alertData);
      return response.data;
    } catch (error) {
      console.error('Error submitting alert:', error);
      throw error;
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
      const response = await this.client.get('/api/v1/alert-types');
      return response.data;
    } catch (error) {
      console.error('Error getting alert types:', error);
      throw error;
    }
  }

  /**
   * Get list of runbook URLs from configured GitHub repository.
   * 
   * Returns a list of markdown file URLs from the configured runbooks repository.
   * If runbooks_repo_url is not configured or if fetching fails, returns an empty list.
   * The dashboard should add "Default Runbook" option to this list.
   */
  async getRunbooks(): Promise<string[]> {
    try {
      const response = await this.client.get('/api/v1/runbooks');
      return response.data;
    } catch (error) {
      console.error('Error getting runbooks:', error);
      // Return empty array on error - don't fail the UI
      return [];
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
      throw error;
    }
  }

  /**
   * Get available filter options (Phase 4)
   * Returns available values for agent types, alert types, and status options
   */
  async getFilterOptions(): Promise<FilterOptions> {
    try {
      const response = await this.client.get<FilterOptions>('/api/v1/history/filter-options');
      
      
      if (response.data && typeof response.data === 'object') {
        return response.data;
      } else {
        throw new Error('Invalid filter options response format');
      }
    } catch (error) {
      console.error('Failed to fetch filter options:', error);
      throw error;
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
      
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid filtered sessions response format');
      }
    } catch (error) {
      console.error('Failed to fetch filtered sessions:', error);
      throw error;
    }
  }
}

// Export singleton instance
export const apiClient = new APIClient();

// Helper function for error handling in components
export const handleAPIError = (error: unknown): string => {
  // Handle AxiosError specifically to extract meaningful error messages
  if (error && typeof error === 'object' && 'isAxiosError' in error) {
    const axiosError = error as AxiosError;
    
    if (axiosError.response?.data) {
      const data = axiosError.response.data as any;
      // Try to extract a meaningful error message from response data
      if (data.detail) {
        if (typeof data.detail === 'string') {
          return data.detail;
        }
        if (data.detail.message) {
          return data.detail.message;
        }
        if (data.detail.error) {
          return data.detail.error;
        }
      }
      if (data.error) {
        return data.error;
      }
      if (data.message) {
        return data.message;
      }
    }
    
    // Fallback to status-based messages
    if (axiosError.response?.status) {
      const status = axiosError.response.status;
      if (status === 400) {
        return 'Bad Request: Invalid data format';
      } else if (status === 401) {
        return 'Unauthorized: Please check your authentication';
      } else if (status === 403) {
        return 'Forbidden: You do not have permission to perform this action';
      } else if (status === 404) {
        return 'Not Found: The requested resource was not found';
      } else if (status === 429) {
        return 'Too many requests. Please wait a moment and try again';
      } else if (status === 500) {
        return 'Server error occurred. Please try again later';
      } else if (status === 503) {
        return 'Service temporarily unavailable. Please try again later';
      } else {
        return `Request failed with status ${status}`;
      }
    }
    
    // Network error
    if (axiosError.request && !axiosError.response) {
      return 'Unable to connect to backend. The service may be restarting. Please wait or try refreshing.';
    }
    
    // Other axios errors
    return axiosError.message || 'Request failed';
  }
  
  // Handle regular Error objects
  if (error instanceof Error) {
    return error.message;
  }
  
  return 'An unexpected error occurred';
}; 