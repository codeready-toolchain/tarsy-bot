import axios, { type AxiosInstance, AxiosError } from 'axios';
import type { SessionsResponse, Session, DetailedSession, SessionFilter, FilterOptions, SearchResult, SystemWarning, MCPServersResponse, Chat, ChatUserMessage, ChatAvailabilityResponse, MCPSelectionConfig, SessionScore, ScoreSessionRequest, ScoreSessionResponse } from '../types';
import { authService } from './auth';
import { TERMINAL_SESSION_STATUSES } from '../utils/statusConstants';

// API base URL configuration  
// In development, use Vite proxy (relative URLs) to handle CORS with OAuth2 proxy
// In production, use the full URL from environment variables
import { urls } from '../config/env';

const API_BASE_URL = urls.api.base;

// Retry configuration constants - exported for testing
export const INITIAL_RETRY_DELAY = 500; // ms
export const MAX_RETRY_DELAY = 5000; // ms - cap at 5 seconds

class APIClient {
  private client: AxiosInstance;

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
    operation: () => Promise<T>
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
          // Retry on 504 Gateway Timeout (proxy timeout during heavy load or slow startup)
          if (axiosError.response?.status === 502 || 
              axiosError.response?.status === 503 || 
              axiosError.response?.status === 504) {
            isRetryable = true;
          }
          
          // Retry on axios timeout errors (ECONNABORTED or similar timeout codes)
          // These occur when the request exceeds the configured timeout (10s)
          if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
            isRetryable = true;
          }
        }
        
        // If not retryable, fail immediately
        if (!isRetryable) {
          throw error;
        }
        
        // Calculate exponential backoff delay with cap at MAX_RETRY_DELAY
        const exponentialDelay = INITIAL_RETRY_DELAY * Math.pow(2, attempt);
        const delay = Math.min(exponentialDelay, MAX_RETRY_DELAY);
        console.log(`🔄 API retry in ${delay}ms (attempt ${attempt + 1})`);
        
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
      () => this.getActiveSessions()
    );
  }

  /**
   * Fetch historical sessions with automatic retry on temporary errors
   * Used during reconnection to handle backend startup delays
   * Retries indefinitely on network/502/503/504 errors until backend is ready
   */
  async getHistoricalSessionsWithRetry(page: number = 1, pageSize: number = 25, sortBy?: string, sortOrder?: string): Promise<SessionsResponse> {
    return this.retryOnTemporaryError(
      () => this.getHistoricalSessions(page, pageSize, sortBy, sortOrder)
    );
  }

  /**
   * Fetch filtered sessions with automatic retry on temporary errors
   * Used during reconnection with active filters to handle backend startup delays
   * Retries indefinitely on network/502/503/504 errors until backend is ready
   */
  async getFilteredSessionsWithRetry(filters: SessionFilter, page: number = 1, pageSize: number = 25, sortBy?: string, sortOrder?: string): Promise<SessionsResponse> {
    return this.retryOnTemporaryError(
      () => this.getFilteredSessions(filters, page, pageSize, sortBy, sortOrder)
    );
  }

  /**
   * Fetch historical sessions (completed/failed/cancelled)
   * Gets sessions with terminal statuses
   */
  async getHistoricalSessions(page: number = 1, pageSize: number = 25, sortBy?: string, sortOrder?: string): Promise<SessionsResponse> {
    try {
      // Build query string manually to ensure proper FastAPI format
      const queryParams = new URLSearchParams();
      // Add all terminal statuses
      TERMINAL_SESSION_STATUSES.forEach(status => {
        queryParams.append('status', status);
      });
      queryParams.append('page', page.toString());
      queryParams.append('page_size', pageSize.toString());
      
      // Add sorting parameters if provided
      if (sortBy) {
        queryParams.append('sort_by', sortBy);
      }
      if (sortOrder) {
        queryParams.append('sort_order', sortOrder);
      }
      
      const url = `/api/v1/history/sessions?${queryParams.toString()}`;
      
      
      const response = await this.client.get<SessionsResponse>(url);
      
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        // Transform flat response to SessionsResponse structure
        const data: any = response.data;
        
        // Check if pagination is already nested (new format) or flat (old format)
        if (data.pagination) {
          // Already in the correct nested format
          return response.data;
        } else {
          // Transform flat structure to nested SessionsResponse format
          return {
            sessions: data.sessions,
            pagination: {
              page: data.page || 1,
              page_size: data.page_size || 25,
              total_pages: data.total_pages || 0,
              total_items: data.total_count || 0,
            },
            filters_applied: data.filters_applied || {},
          };
        }
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
  async getAlertTypes(): Promise<{ alert_types: string[], default_alert_type: string }> {
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

  /**
   * Get available MCP servers and their tools.
   * 
   * Returns information about all configured MCP servers including:
   * - Server ID and type
   * - Enabled status
   * - Available tools with descriptions and input schemas
   * 
   * Used for building UI to select which MCP servers/tools to use for alert processing.
   */
  async getMCPServers(): Promise<MCPServersResponse> {
    try {
      const response = await this.client.get<MCPServersResponse>('/api/v1/system/mcp-servers');
      
      if (response.data && typeof response.data === 'object' && 'servers' in response.data) {
        return response.data;
      } else {
        throw new Error('Invalid MCP servers response format');
      }
    } catch (error) {
      console.error('Error fetching MCP servers:', error);
      throw error;
    }
  }

  /**
   * Get default tools configuration.
   * 
   * Returns the provider's default configuration including:
   * - Available MCP servers (enabled by default)
   * - Native tools default state (per provider config)
   * 
   * Used to populate initial UI state and detect user changes.
   */
  /**
   * Get default tools configuration for a specific alert type.
   * 
   * Different alert types use different chains with different default MCP servers.
   * If no alert_type is provided, uses the system's default alert type.
   */
  async getDefaultToolsConfig(alertType?: string): Promise<MCPSelectionConfig> {
    try {
      const params = alertType ? `?alert_type=${encodeURIComponent(alertType)}` : '';
      const response = await this.client.get<{
        alert_type: string;
        mcp_servers: Array<{ server_id: string }>;
        native_tools: { [key: string]: boolean };
      }>(`/api/v1/system/default-tools${params}`);
      
      if (response.data && typeof response.data === 'object') {
        // Transform backend response to MCPSelectionConfig format
        // Note: Backend returns 'server_id' but frontend MCPServerSelection uses 'name'
        return {
          servers: response.data.mcp_servers.map(server => ({
            name: server.server_id,  // Backend uses server_id, frontend uses name
            tools: null,             // null means all tools selected by default
          })),
          native_tools: response.data.native_tools ?? undefined,
        };
      } else {
        throw new Error('Invalid default tools response format');
      }
    } catch (error) {
      console.error('Error fetching default tools config:', error);
      throw error;
    }
  }

  /**
   * Cancel an active session
   * 
   * Sends a cancellation request for the specified session.
   * The backend will attempt to cancel the processing task and mark the session as cancelled.
   */
  async cancelSession(sessionId: string): Promise<{ success: boolean; message: string; status: string }> {
    try {
      const response = await this.client.post(`/api/v1/history/sessions/${sessionId}/cancel`);
      return response.data;
    } catch (error) {
      console.error('Error cancelling session:', error);
      throw error;
    }
  }

  /**
   * Cancel an individual paused agent in a parallel stage
   */
  async cancelAgent(sessionId: string, executionId: string): Promise<{ success: boolean; session_status: string; stage_status: string }> {
    try {
      const response = await this.client.post(`/api/v1/history/sessions/${sessionId}/stages/${executionId}/cancel`);
      return response.data;
    } catch (error) {
      console.error('Error cancelling agent:', error);
      throw error;
    }
  }

  /**
   * Resume a paused session
   */
  async resumeSession(sessionId: string): Promise<{ success: boolean; message: string; status: string }> {
    try {
      const response = await this.client.post(`/api/v1/history/sessions/${sessionId}/resume`);
      return response.data;
    } catch (error) {
      console.error('Error resuming session:', error);
      throw error;
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
  async getFilteredSessions(filters: SessionFilter, page: number = 1, pageSize: number = 25, sortBy?: string, sortOrder?: string): Promise<SessionsResponse> {
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
      
      // Add sorting parameters if provided
      if (sortBy) {
        queryParams.append('sort_by', sortBy);
      }
      if (sortOrder) {
        queryParams.append('sort_order', sortOrder);
      }
      
      const url = `/api/v1/history/sessions?${queryParams.toString()}`;
      
      // Filtered sessions API request
      
      const response = await this.client.get<SessionsResponse>(url);
      
      
      if (response.data && typeof response.data === 'object' && 'sessions' in response.data) {
        // Transform flat response to SessionsResponse structure
        const data: any = response.data;
        
        // Check if pagination is already nested (new format) or flat (old format)
        if (data.pagination) {
          // Already in the correct nested format
          return response.data;
        } else {
          // Transform flat structure to nested SessionsResponse format
          return {
            sessions: data.sessions,
            pagination: {
              page: data.page || 1,
              page_size: data.page_size || 25,
              total_pages: data.total_pages || 0,
              total_items: data.total_count || 0,
            },
            filters_applied: data.filters_applied || {},
          };
        }
      } else {
        throw new Error('Invalid filtered sessions response format');
      }
    } catch (error) {
      console.error('Failed to fetch filtered sessions:', error);
      throw error;
    }
  }

  // EP-0027: Chat capability methods

  /**
   * Create a new chat for a completed session
   */
  async createChat(sessionId: string): Promise<Chat> {
    try {
      const response = await this.client.post<Chat>(
        `/api/v1/sessions/${sessionId}/chat`
      );
      return response.data;
    } catch (error) {
      console.error('Error creating chat:', error);
      throw error;
    }
  }

  /**
   * Get chat details by ID
   */
  async getChat(chatId: string): Promise<Chat> {
    try {
      const response = await this.client.get<Chat>(`/api/v1/chats/${chatId}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching chat:', error);
      throw error;
    }
  }

  /**
   * Send a message to the chat
   */
  async sendChatMessage(
    chatId: string, 
    content: string, 
    author: string
  ): Promise<ChatUserMessage> {
    try {
      const response = await this.client.post<ChatUserMessage>(
        `/api/v1/chats/${chatId}/messages`,
        { content, author }
      );
      return response.data;
    } catch (error) {
      console.error('Error sending chat message:', error);
      throw error;
    }
  }

  /**
   * Cancel an active chat execution
   */
  async cancelChatExecution(stageExecutionId: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await this.client.post(`/api/v1/chats/executions/${stageExecutionId}/cancel`);
      return response.data;
    } catch (error) {
      console.error('Error cancelling chat execution:', error);
      throw error;
    }
  }

  /**
   * Get chat message history
   */
  async getChatMessages(
    chatId: string,
    limit?: number,
    offset?: number
  ): Promise<{ messages: any[]; total_count: number; chat_id: string }> {
    try {
      const params = new URLSearchParams();
      if (limit) params.append('limit', limit.toString());
      if (offset) params.append('offset', offset.toString());
      
      const response = await this.client.get<{ messages: any[]; total_count: number; chat_id: string }>(
        `/api/v1/chats/${chatId}/messages?${params.toString()}`
      );
      return response.data;
    } catch (error) {
      console.error('Error fetching chat messages:', error);
      throw error;
    }
  }

  /**
   * Check if chat is available for a session
   */
  async checkChatAvailable(sessionId: string): Promise<ChatAvailabilityResponse> {
    try {
      const response = await this.client.get<ChatAvailabilityResponse>(
        `/api/v1/sessions/${sessionId}/chat-available`
      );
      return response.data;
    } catch (error) {
      console.error('Error checking chat availability:', error);
      throw error;
    }
  }

  // EP-0028: Session Scoring methods

  /**
   * Trigger async scoring for a session
   * Returns immediately with score_id and status (202 for new scoring, 200 for existing)
   */
  async scoreSession(sessionId: string, request?: ScoreSessionRequest): Promise<ScoreSessionResponse> {
    try {
      const response = await this.client.post<ScoreSessionResponse>(
        `/api/v1/scoring/sessions/${sessionId}/score`,
        request || {}
      );
      return response.data;
    } catch (error) {
      console.error('Error scoring session:', error);
      throw error;
    }
  }

  /**
   * Get session score (any status: pending, in_progress, completed, failed)
   */
  async getSessionScore(sessionId: string): Promise<SessionScore> {
    try {
      const response = await this.client.get<SessionScore>(
        `/api/v1/scoring/sessions/${sessionId}/score`
      );
      return response.data;
    } catch (error) {
      console.error('Error fetching session score:', error);
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