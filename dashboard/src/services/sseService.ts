/**
 * SSE Service - Singleton to prevent React Strict Mode from creating multiple connections
 */

import type { 
  SessionUpdate, 
  ChainProgressUpdate, 
  StageProgressUpdate 
} from '../types';

type SSEEventHandler = (data: SessionUpdate) => void;
type ChainProgressHandler = (data: ChainProgressUpdate) => void;
type StageProgressHandler = (data: StageProgressUpdate) => void;
type SSEErrorHandler = (error: Event) => void;
type SessionSpecificHandler = (data: any) => void;

interface SSEConnection {
  eventSource: EventSource;
  channel: string;
  lastEventId: number;
  reconnectAttempts: number;
}

class SSEService {
  private connections: Map<string, SSEConnection> = new Map();
  private pendingConnections: Set<string> = new Set(); // Track in-progress connections
  private baseUrl: string = '';
  private maxReconnectAttempts = 10;
  private healthCheckInterval: ReturnType<typeof setInterval> | null = null;
  private permanentlyDisabled = false;
  private urlResolutionPromise: Promise<void> | null = null;
  
  private eventHandlers: {
    sessionUpdate: SSEEventHandler[];
    sessionCompleted: SSEEventHandler[];
    sessionFailed: SSEEventHandler[];
    dashboardUpdate: SSEEventHandler[];
    chainProgress: ChainProgressHandler[];
    stageProgress: StageProgressHandler[];
    connectionChange: Array<(connected: boolean) => void>;
    error: SSEErrorHandler[];
    sessionSpecific: Map<string, SessionSpecificHandler[]>;
  } = {
    sessionUpdate: [],
    sessionCompleted: [],
    sessionFailed: [],
    dashboardUpdate: [],
    chainProgress: [],
    stageProgress: [],
    connectionChange: [],
    error: [],
    sessionSpecific: new Map(),
  };

  constructor() {
    // Initialize base URL from config
    this.urlResolutionPromise = import('../config/env').then(({ urls }) => {
      this.baseUrl = urls.api.base;
      this.startHealthCheck();
    }).catch((error) => {
      console.error('Failed to load SSE configuration:', error);
      // Fallback: use current page's origin
      this.baseUrl = window.location.origin;
      this.startHealthCheck();
      return;
    });
  }

  /**
   * Start periodic health check
   */
  private startHealthCheck(): void {
    this.healthCheckInterval = setInterval(() => {
      // Attempt to reconnect to any disconnected channels
      if (!this.permanentlyDisabled && this.connections.size === 0) {
        // If we had subscriptions before, try to reconnect
        this.notifyConnectionChange();
      }
    }, 30000); // Check every 30 seconds
  }

  /**
   * Connect to SSE endpoint
   */
  async connect(): Promise<void> {
    if (this.permanentlyDisabled) {
      console.log('SSE permanently disabled (endpoint not available)');
      return;
    }

    // Wait for URL resolution
    if (this.urlResolutionPromise) {
      try {
        await this.urlResolutionPromise;
      } catch (error) {
        console.error('❌ URL resolution failed:', error);
        return;
      }
    }

    // Note: baseUrl can be empty string in development (relative URLs with Vite proxy)
    if (this.baseUrl === undefined || this.baseUrl === null) {
      console.error('❌ Cannot connect: SSE base URL not set');
      return;
    }

    // Subscribe to dashboard channel by default
    await this.subscribeToChannel('sessions');
  }

  /**
   * Subscribe to a specific SSE channel
   */
  private async subscribeToChannel(channel: string, lastEventId: number = 0): Promise<void> {
    // Prevent concurrent connection attempts to the same channel (React Strict Mode protection)
    if (this.pendingConnections.has(channel)) {
      return;
    }
    
    // Don't reconnect if already connected
    if (this.connections.has(channel)) {
      const connection = this.connections.get(channel)!;
      if (connection.eventSource.readyState === EventSource.OPEN) {
        return;
      }
      // Clean up old connection
      connection.eventSource.close();
      this.connections.delete(channel);
    }
    
    // Mark this channel as pending
    this.pendingConnections.add(channel);

    try {
      const url = `${this.baseUrl}/api/v1/events/stream?channel=${encodeURIComponent(channel)}&last_event_id=${lastEventId}`;
      const eventSource = new EventSource(url);

      const connection: SSEConnection = {
        eventSource,
        channel,
        lastEventId,
        reconnectAttempts: 0,
      };

      this.connections.set(channel, connection);

      eventSource.onopen = () => {
        console.log(`✅ SSE connected to channel: ${channel}`);
        connection.reconnectAttempts = 0;
        this.permanentlyDisabled = false;
        this.pendingConnections.delete(channel); // Connection successful, remove from pending
        this.notifyConnectionChange();
      };

      // Handle different event types from backend
      eventSource.addEventListener('session.created', (event: MessageEvent) => {
        this.handleEvent('session.created', event, connection);
      });

      eventSource.addEventListener('session.started', (event: MessageEvent) => {
        this.handleEvent('session.started', event, connection);
      });

      eventSource.addEventListener('session.completed', (event: MessageEvent) => {
        this.handleEvent('session.completed', event, connection);
      });

      eventSource.addEventListener('session.failed', (event: MessageEvent) => {
        this.handleEvent('session.failed', event, connection);
      });

      eventSource.addEventListener('llm.interaction', (event: MessageEvent) => {
        this.handleEvent('llm.interaction', event, connection);
      });

      eventSource.addEventListener('mcp.tool_call', (event: MessageEvent) => {
        this.handleEvent('mcp.tool_call', event, connection);
      });

      eventSource.addEventListener('mcp.list_tools', (event: MessageEvent) => {
        this.handleEvent('mcp.list_tools', event, connection);
      });

      eventSource.addEventListener('stage.started', (event: MessageEvent) => {
        this.handleEvent('stage.started', event, connection);
      });

      eventSource.addEventListener('stage.completed', (event: MessageEvent) => {
        this.handleEvent('stage.completed', event, connection);
      });

      eventSource.addEventListener('stage.failed', (event: MessageEvent) => {
        this.handleEvent('stage.failed', event, connection);
      });

      eventSource.onerror = (error) => {
        console.error(`❌ SSE error on channel ${channel} (readyState: ${eventSource.readyState})`);
        this.eventHandlers.error.forEach(handler => handler(error));
        
        // Remove from pending on error
        this.pendingConnections.delete(channel);
        
        // Only reconnect if connection is actually closed
        // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
        if (eventSource.readyState === EventSource.CLOSED) {
          // Handle reconnection with exponential backoff
          if (connection.reconnectAttempts < this.maxReconnectAttempts) {
            connection.reconnectAttempts++;
            // Start with 200ms, then exponential backoff: 200ms, 400ms, 800ms, 1.6s, 3.2s...
            const delay = Math.min(200 * Math.pow(2, connection.reconnectAttempts - 1), 30000);
            console.log(`🔄 SSE reconnecting to ${channel} in ${delay}ms (attempt ${connection.reconnectAttempts}/${this.maxReconnectAttempts})`);
            
            setTimeout(() => {
              this.subscribeToChannel(channel, connection.lastEventId);
            }, delay);
          } else {
            console.warn(`❌ Max SSE reconnection attempts reached for channel: ${channel}`);
            this.permanentlyDisabled = true;
            this.connections.delete(channel);
            this.notifyConnectionChange();
          }
        }
      };

    } catch (error) {
      console.error(`Failed to create SSE connection to ${channel}:`, error);
      this.pendingConnections.delete(channel); // Clean up on exception
    }
  }

  /**
   * Handle SSE event
   */
  private handleEvent(eventType: string, event: MessageEvent, connection: SSEConnection): void {
    try {
      const data = JSON.parse(event.data);
      
      // Update last event ID for catchup
      if (event.lastEventId) {
        connection.lastEventId = parseInt(event.lastEventId, 10);
      }

      // Map SSE events to handler types
      switch (eventType) {
        case 'session.created':
        case 'session.started':
          // Session update
          this.eventHandlers.sessionUpdate.forEach(handler => handler(data));
          this.routeToSessionHandlers(data);
          break;

        case 'session.completed':
          this.eventHandlers.sessionCompleted.forEach(handler => handler(data));
          this.eventHandlers.sessionUpdate.forEach(handler => handler(data));
          this.routeToSessionHandlers(data);
          break;

        case 'session.failed':
          this.eventHandlers.sessionFailed.forEach(handler => handler(data));
          this.eventHandlers.sessionUpdate.forEach(handler => handler(data));
          this.routeToSessionHandlers(data);
          break;

        case 'llm.interaction':
        case 'mcp.tool_call':
        case 'mcp.list_tools':
          // Dashboard updates (interactions)
          this.eventHandlers.dashboardUpdate.forEach(handler => handler(data));
          this.routeToSessionHandlers(data);
          break;

        case 'stage.started':
        case 'stage.completed':
        case 'stage.failed':
          // Stage progress updates
          const stageUpdate: StageProgressUpdate = {
            session_id: data.session_id,
            chain_id: data.chain_id || '',
            stage_execution_id: data.execution_id || '',
            stage_id: data.stage_id || '',
            stage_name: data.stage_name || '',
            stage_index: data.stage_index || 0,
            agent: data.agent_type || '',
            status: this.mapStageStatus(eventType),
            started_at_us: data.started_at_us,
            completed_at_us: data.completed_at_us,
            timestamp_us: data.timestamp_us || Date.now() * 1000,
          };
          
          this.eventHandlers.stageProgress.forEach(handler => handler(stageUpdate));
          this.eventHandlers.dashboardUpdate.forEach(handler => handler(stageUpdate as any));
          this.routeToSessionHandlers(stageUpdate);
          break;

        default:
          console.log('❓ Unknown SSE event type:', eventType);
      }
    } catch (error) {
      console.error('❌ Failed to parse SSE message:', error, 'Raw data:', event.data);
    }
  }

  /**
   * Map stage event type to status
   */
  private mapStageStatus(eventType: string): 'pending' | 'active' | 'completed' | 'failed' {
    if (eventType === 'stage.started') return 'active';
    if (eventType === 'stage.completed') return 'completed';
    if (eventType === 'stage.failed') return 'failed';
    return 'pending';
  }

  /**
   * Route event to session-specific handlers
   */
  private routeToSessionHandlers(data: any): void {
    if (data.session_id) {
      const sessionChannel = `session_${data.session_id}`;
      const handlers = this.eventHandlers.sessionSpecific.get(sessionChannel);
      if (handlers) {
        handlers.forEach(handler => handler(data));
      }
    }
  }

  /**
   * Notify connection change handlers
   */
  private notifyConnectionChange(): void {
    // Report connected if any connection is OPEN
    const isConnected = Array.from(this.connections.values()).some(
      conn => conn.eventSource.readyState === EventSource.OPEN
    );
    
    this.eventHandlers.connectionChange.forEach(handler => handler(isConnected));
  }

  /**
   * Disconnect from all SSE channels
   */
  disconnect(): void {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }

    for (const connection of this.connections.values()) {
      connection.eventSource.close();
    }
    this.connections.clear();
    this.notifyConnectionChange();
  }

  /**
   * Subscribe to a session-specific channel
   */
  subscribeToSessionChannel(sessionId: string): void {
    const channel = `session:${sessionId}`;
    console.log(`📤 Subscribing to session channel: ${channel}`);
    this.subscribeToChannel(channel);
  }

  /**
   * Unsubscribe from a session-specific channel
   */
  unsubscribeFromSessionChannel(sessionId: string): void {
    const channel = `session:${sessionId}`;
    const connection = this.connections.get(channel);
    if (connection) {
      console.log(`📤 Unsubscribing from session channel: ${channel}`);
      connection.eventSource.close();
      this.connections.delete(channel);
      
      // Clean up event handlers for this session
      const sessionChannel = `session_${sessionId}`;
      this.eventHandlers.sessionSpecific.delete(sessionChannel);
    }
  }

  /**
   * Event handler registration methods (maintain WebSocket API compatibility)
   */

  onSessionUpdate(handler: SSEEventHandler): () => void {
    this.eventHandlers.sessionUpdate.push(handler);
    return () => {
      const index = this.eventHandlers.sessionUpdate.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.sessionUpdate.splice(index, 1);
      }
    };
  }

  onSessionCompleted(handler: SSEEventHandler): () => void {
    this.eventHandlers.sessionCompleted.push(handler);
    return () => {
      const index = this.eventHandlers.sessionCompleted.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.sessionCompleted.splice(index, 1);
      }
    };
  }

  onSessionFailed(handler: SSEEventHandler): () => void {
    this.eventHandlers.sessionFailed.push(handler);
    return () => {
      const index = this.eventHandlers.sessionFailed.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.sessionFailed.splice(index, 1);
      }
    };
  }

  onDashboardUpdate(handler: SSEEventHandler): () => void {
    this.eventHandlers.dashboardUpdate.push(handler);
    return () => {
      const index = this.eventHandlers.dashboardUpdate.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.dashboardUpdate.splice(index, 1);
      }
    };
  }

  onChainProgress(handler: ChainProgressHandler): () => void {
    this.eventHandlers.chainProgress.push(handler);
    return () => {
      const index = this.eventHandlers.chainProgress.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.chainProgress.splice(index, 1);
      }
    };
  }

  onStageProgress(handler: StageProgressHandler): () => void {
    this.eventHandlers.stageProgress.push(handler);
    return () => {
      const index = this.eventHandlers.stageProgress.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.stageProgress.splice(index, 1);
      }
    };
  }

  onSessionSpecificUpdate(channel: string, handler: SessionSpecificHandler): () => void {
    if (!this.eventHandlers.sessionSpecific.has(channel)) {
      this.eventHandlers.sessionSpecific.set(channel, []);
    }
    this.eventHandlers.sessionSpecific.get(channel)!.push(handler);
    return () => {
      const handlers = this.eventHandlers.sessionSpecific.get(channel);
      if (handlers) {
        const index = handlers.indexOf(handler);
        if (index > -1) {
          handlers.splice(index, 1);
        }
      }
    };
  }

  onConnectionChange(handler: (connected: boolean) => void): () => void {
    this.eventHandlers.connectionChange.push(handler);
    return () => {
      const index = this.eventHandlers.connectionChange.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.connectionChange.splice(index, 1);
      }
    };
  }

  onError(handler: SSEErrorHandler): () => void {
    this.eventHandlers.error.push(handler);
    return () => {
      const index = this.eventHandlers.error.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.error.splice(index, 1);
      }
    };
  }

  /**
   * Compatibility methods for WebSocket-like API
   */

  onClose(_handler: (event: CloseEvent) => void): () => void {
    // SSE doesn't have a direct close event, but we can simulate it
    // For now, return a no-op unsubscribe
    return () => {};
  }

  get readyState(): number {
    // Return OPEN if any connection is open, CLOSED otherwise
    const hasOpenConnection = Array.from(this.connections.values()).some(
      conn => conn.eventSource.readyState === EventSource.OPEN
    );
    return hasOpenConnection ? EventSource.OPEN : EventSource.CLOSED;
  }

  get isConnected(): boolean {
    return Array.from(this.connections.values()).some(
      conn => conn.eventSource.readyState === EventSource.OPEN
    );
  }

  get isDisabled(): boolean {
    return this.permanentlyDisabled;
  }

  get currentUserId(): string {
    // SSE doesn't require a user ID like WebSocket did
    return 'sse-client';
  }

  async retry(): Promise<void> {
    console.log('🔄 Manual retry requested');
    this.permanentlyDisabled = false;
    
    // Reconnect to all known channels
    const channels = Array.from(this.connections.keys());
    for (const channel of channels) {
      const connection = this.connections.get(channel)!;
      connection.eventSource.close();
      this.connections.delete(channel);
      await this.subscribeToChannel(channel, connection.lastEventId);
    }
    
    // If no channels, try to connect to default
    if (channels.length === 0) {
      await this.connect();
    }
  }

  cleanup(): void {
    this.disconnect();
  }
}

// Export singleton instance
export const sseService = new SSEService();

