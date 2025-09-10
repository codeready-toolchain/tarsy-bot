import type { WebSocketMessage, SessionUpdate, ChainProgressUpdate, StageProgressUpdate } from '../types';

type WebSocketEventHandler = (data: SessionUpdate) => void;
type ChainProgressHandler = (data: ChainProgressUpdate) => void;
type StageProgressHandler = (data: StageProgressUpdate) => void;
type WebSocketErrorHandler = (error: Event) => void;
type WebSocketCloseHandler = (event: CloseEvent) => void;
type SessionSpecificHandler = (data: any) => void; // For session-specific timeline updates

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string = '';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10; // Increased from 3 to 10
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private healthCheckInterval: ReturnType<typeof setInterval> | null = null;
  private isConnecting = false;
  private permanentlyDisabled = false;
  private lastConnectionAttempt = 0;
  private userId: string;
  private subscribedChannels = new Set<string>(); // Track subscribed channels
  private urlResolutionPromise: Promise<void> | null = null; // Track URL resolution state
  private eventHandlers: {
    sessionUpdate: WebSocketEventHandler[];
    sessionCompleted: WebSocketEventHandler[];
    sessionFailed: WebSocketEventHandler[];
    dashboardUpdate: WebSocketEventHandler[]; // Add handler for dashboard updates
    chainProgress: ChainProgressHandler[]; // Add handler for chain progress updates
    stageProgress: StageProgressHandler[]; // Add handler for stage progress updates
    connectionChange: Array<(connected: boolean) => void>; // Add connection change handler
    error: WebSocketErrorHandler[];
    close: WebSocketCloseHandler[];
    sessionSpecific: Map<string, SessionSpecificHandler[]>; // New: session-specific handlers
  } = {
    sessionUpdate: [],
    sessionCompleted: [],
    sessionFailed: [],
    dashboardUpdate: [], // Initialize dashboard update handlers
    chainProgress: [], // Initialize chain progress handlers
    stageProgress: [], // Initialize stage progress handlers
    connectionChange: [], // Initialize connection change handlers
    error: [],
    close: [],
    sessionSpecific: new Map(), // Initialize session-specific handlers
  };

  constructor() {
    // Generate a unique user ID for this dashboard session
    this.userId = 'dashboard-' + Math.random().toString(36).substr(2, 9);
    
    // WebSocket URL configuration
    // In development, use OAuth2 proxy to maintain authentication
    let wsBaseUrl: string | undefined;
    
    // Safety check: import.meta.env might be undefined in some environments
  try {
    wsBaseUrl = import.meta.env?.VITE_WS_BASE_URL;
  } catch (error) {
    console.warn('import.meta.env not available, falling back to default');
    wsBaseUrl = undefined;
  }
  
  if (!wsBaseUrl) {
    // Import at runtime to avoid circular dependency issues
    this.urlResolutionPromise = import('../config/env').then(({ urls }) => {
      wsBaseUrl = urls.websocket.base;
      this.url = `${wsBaseUrl}/ws/dashboard/${this.userId}`;
      this.startHealthCheck();
    }).catch(() => {
      // Fallback if config import fails
      if (import.meta.env.DEV) {
        wsBaseUrl = 'ws://localhost:5173';
      } else {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        wsBaseUrl = `${protocol}//${host}`;
      }
      this.url = `${wsBaseUrl}/ws/dashboard/${this.userId}`;
      this.startHealthCheck();
    }).finally(() => {
      // Mark URL resolution as complete
      this.urlResolutionPromise = null;
    });
    return; // Early return for async case
  }
    
    this.url = `${wsBaseUrl}/ws/dashboard/${this.userId}`;

    // Start periodic health check to recover from permanently disabled state
    this.startHealthCheck();
  }

  /**
   * Start periodic health check to detect when backend becomes available again
   */
  private startHealthCheck(): void {
    // Check every 30 seconds if we should attempt to reconnect
    this.healthCheckInterval = setInterval(() => {
      const now = Date.now();
      const timeSinceLastAttempt = now - this.lastConnectionAttempt;
      
      // If permanently disabled and it's been more than 2 minutes since last attempt
      if (this.permanentlyDisabled && timeSinceLastAttempt > 120000) {
        console.log('🔄 Health check: Attempting to recover from permanently disabled state');
        this.resetConnectionState();
        this.connect();
      }
      
      // If not connected and not connecting, try to reconnect
      if (!this.isConnected && !this.isConnecting && !this.permanentlyDisabled) {
        console.log('🔄 Health check: Connection lost, attempting to reconnect');
        this.connect();
      }
    }, 30000);
  }

  /**
   * Reset connection state to allow reconnection attempts
   */
  private resetConnectionState(): void {
    this.permanentlyDisabled = false;
    this.reconnectAttempts = 0;
    this.isConnecting = false;
    console.log('🔄 Connection state reset - ready for new connection attempts');
  }

  /**
   * Connect to WebSocket with automatic reconnection
   */
  async connect(): Promise<void> {
    if (this.permanentlyDisabled) {
      console.log('WebSocket permanently disabled (endpoint not available)');
      return;
    }

    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    // Wait for URL resolution if still in progress
    if (this.urlResolutionPromise) {
      console.log('🔌 Waiting for URL resolution before connecting...');
      try {
        await this.urlResolutionPromise;
      } catch (error) {
        console.error('❌ URL resolution failed:', error);
        return;
      }
      
      // Re-check connection state after URL resolution
      if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
        console.log('🔌 Connection already established or in progress after URL resolution');
        return;
      }
    }

    // Check if URL is set after resolution
    if (!this.url) {
      console.error('❌ Cannot connect: WebSocket URL not set');
      return;
    }

    this.isConnecting = true;
    this.lastConnectionAttempt = Date.now();
    console.log('🔌 Connecting to WebSocket:', this.url);

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('🎉 WebSocket connected successfully!');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.permanentlyDisabled = false; // Reset permanently disabled state on successful connection

        // Notify connection change handlers
        this.eventHandlers.connectionChange.forEach(handler => handler(true));

        // Subscribe to dashboard updates
        const subscribeMessage = {
          type: 'subscribe',
          channel: 'dashboard_updates'
        };
        console.log('📤 Sending subscription message:', subscribeMessage);
        this.send(subscribeMessage);

        // Re-subscribe to previously tracked session channels
        if (this.subscribedChannels.size > 0) {
          for (const channel of this.subscribedChannels) {
            this.send({ type: 'subscribe', channel });
          }
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          console.log('📥 WebSocket message received:', message);
          this.handleMessage(message);
        } catch (error) {
          console.error('❌ Failed to parse WebSocket message:', error, 'Raw data:', event.data);
        }
      };

      this.ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        this.isConnecting = false;
        this.eventHandlers.error.forEach(handler => handler(error));
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        this.isConnecting = false;
        this.ws = null;
        this.eventHandlers.close.forEach(handler => handler(event));

        // Notify connection change handlers
        this.eventHandlers.connectionChange.forEach(handler => handler(false));

        // Check if we should attempt to reconnect
        if (event.code !== 1000) {
          // On first failure, check if endpoint exists
          if (this.reconnectAttempts === 0) {
            this.checkEndpointExists().then(exists => {
              if (!exists) {
                console.log('WebSocket endpoint not available, will retry later via health check');
                this.permanentlyDisabled = true;
                return;
              }
              
              // Endpoint exists but connection failed, try to reconnect
              if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.scheduleReconnect();
              } else {
                console.log('Max WebSocket reconnection attempts reached, will retry later via health check');
                this.permanentlyDisabled = true;
              }
            });
          } else if (this.reconnectAttempts < this.maxReconnectAttempts) {
            // Subsequent failures - just retry
            this.scheduleReconnect();
          } else {
            console.log('Max WebSocket reconnection attempts reached, will retry later via health check');
            this.permanentlyDisabled = true;
          }
        }
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      this.isConnecting = false;
    }
  }

  /**
   * Check if WebSocket endpoint exists by testing HTTP endpoint via proxy
   */
  private async checkEndpointExists(): Promise<boolean> {
    try {
      // Test if the WebSocket endpoint path exists by checking a simple endpoint
      // Since WebSocket endpoints don't respond to HTTP, we'll just check if we get a reasonable response
      const response = await fetch(`/ws/dashboard/${this.userId}`);
      
      // If we get 404, the endpoint doesn't exist
      if (response.status === 404) {
        return false;
      }
      
      // Any other response (including WebSocket upgrade errors) suggests the endpoint exists
      return true;
    } catch (error) {
      console.log('Endpoint check failed, assuming endpoint might exist:', error);
      // Network error, assume endpoint might exist
      return true;
    }
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }

    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect');
      this.ws = null;
    }

    this.isConnecting = false;
    this.reconnectAttempts = 0;
    this.lastConnectionAttempt = 0; // Reset last connection attempt on manual disconnect
  }

  /**
   * Send message to WebSocket
   */
  private send(message: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(message: WebSocketMessage): void {
    console.log('🔄 Processing WebSocket message:', message);
    console.log('🔍 Message type:', message.type, 'Channel:', message.channel, 'Data type:', message.data?.type);
    
    // Handle message batches first
    if (message.type === 'message_batch' && message.messages) {
      console.log(`📦 Processing message batch with ${message.count} messages`);
      const batchedMessages = message.messages;
      batchedMessages.forEach(batchedMessage => {
        console.log('📥 Processing batched message:', batchedMessage);
        this.handleMessage(batchedMessage);
      });
      return;
    }

    switch (message.type) {
      case 'session_update':
        if (!message.data) {
          console.log('⚠️  session_update message has no data property, skipping');
          return;
        }
        console.log('📈 Handling session_update, calling', this.eventHandlers.sessionUpdate.length, 'handlers');
        this.eventHandlers.sessionUpdate.forEach(handler => handler(message.data!));
        
        // Also handle session-specific updates if this message has a channel
        if (message.channel && message.channel.startsWith('session_')) {
          console.log(`📈 Handling session-specific update for channel: ${message.channel}`);
          const handlers = this.eventHandlers.sessionSpecific.get(message.channel);
          if (handlers) {
            handlers.forEach(handler => handler(message.data!));
          }
        }
        break;
      case 'session_status_change':
        console.log('🔄 Handling session_status_change from session channel');
        // Handle session status changes from session-specific channels
        if (message.channel && message.channel.startsWith('session_')) {
          console.log(`🔄 Session status change for channel: ${message.channel}`);
          const handlers = this.eventHandlers.sessionSpecific.get(message.channel);
          if (handlers) {
            handlers.forEach(handler => handler(message.data || message));
          }
        }
        break;
      case 'batched_session_updates':
        console.log('📦 Handling batched_session_updates from session channel');
        // Handle batched timeline updates from session-specific channels
        if (message.channel && message.channel.startsWith('session_')) {
          console.log(`📦 Batched updates for channel: ${message.channel}`);
          const handlers = this.eventHandlers.sessionSpecific.get(message.channel);
          if (handlers) {
            handlers.forEach(handler => handler(message.data || message));
          }
        }
        break;
      case 'session_completed':
        if (!message.data) {
          console.log('⚠️  session_completed message has no data property, skipping');
          return;
        }
        console.log('✅ Handling session_completed, calling', this.eventHandlers.sessionCompleted.length, 'handlers');
        this.eventHandlers.sessionCompleted.forEach(handler => handler(message.data!));
        break;
      case 'session_failed':
        if (!message.data) {
          console.log('⚠️  session_failed message has no data property, skipping');
          return;
        }
        console.log('❌ Handling session_failed, calling', this.eventHandlers.sessionFailed.length, 'handlers');
        this.eventHandlers.sessionFailed.forEach(handler => handler(message.data!));
        break;
      case 'dashboard_update':
        if (!message.data) {
          console.log('⚠️  dashboard_update message has no data property, skipping');
          return;
        }
        
        // Check if this is actually a stage_progress message disguised as dashboard_update
        if (message.data && message.data.type === 'stage_progress') {
          console.log('🎯 Found stage_progress message within dashboard_update, redirecting to stage progress handlers');
          this.eventHandlers.stageProgress.forEach(handler => handler(message.data as StageProgressUpdate));
          // Still continue with session-specific handling below
        }
        
        // Check if this is a session-specific update (has channel property)
        if (message.channel && message.channel.startsWith('session_')) {
          console.log(`📈 Handling dashboard_update with session data for channel: ${message.channel}`);
          const handlers = this.eventHandlers.sessionSpecific.get(message.channel);
          if (handlers && handlers.length > 0) {
            console.log(`📈 Calling ${handlers.length} session-specific handlers for ${message.channel}`);
            handlers.forEach(handler => handler(message.data!));
          } else {
            console.log(`⚠️  No handlers registered for session channel: ${message.channel}`);
          }
          
          // Also call regular dashboard handlers
          console.log('📊 Also handling as regular dashboard_update, calling', this.eventHandlers.dashboardUpdate.length, 'handlers');
          this.eventHandlers.dashboardUpdate.forEach(handler => handler(message.data!));
        } else if (message.data.session_id && message.data.type !== 'system_metrics') {
          // Only try session-specific routing if:
          // 1. There's a session_id in the data
          // 2. It's not a system_metrics update (which should go to dashboard)
          // 3. There are actually handlers registered for that session
          const sessionChannel = `session_${message.data.session_id}`;
          const sessionHandlers = this.eventHandlers.sessionSpecific.get(sessionChannel);
          
          if (sessionHandlers && sessionHandlers.length > 0) {
            console.log(`📈 Handling dashboard_update with session data for channel: ${sessionChannel}`);
            console.log(`📈 Calling ${sessionHandlers.length} session-specific handlers for ${sessionChannel}`);
            sessionHandlers.forEach(handler => handler(message.data!));
            
            // Also call regular dashboard handlers for certain types
            if (message.data.type === 'session_status_change' || message.data.type === 'system_metrics') {
              console.log('📊 Also handling as regular dashboard_update, calling', this.eventHandlers.dashboardUpdate.length, 'handlers');
              this.eventHandlers.dashboardUpdate.forEach(handler => handler(message.data!));
            }
          } else {
            // No session-specific handlers registered - this is a dashboard-only update
            console.log('📊 Handling dashboard_update, calling', this.eventHandlers.dashboardUpdate.length, 'handlers');
            this.eventHandlers.dashboardUpdate.forEach(handler => handler(message.data!));
          }
        } else {
          // Regular dashboard update (no session_id or system_metrics)
          console.log('📊 Handling dashboard_update, calling', this.eventHandlers.dashboardUpdate.length, 'handlers');
          this.eventHandlers.dashboardUpdate.forEach(handler => handler(message.data!));
        }
        break;
      case 'ping':
        console.log('🏓 Received ping, responding with pong');
        // Respond to ping with pong
        this.send({ type: 'pong' });
        break;
      case 'connection_established':
        console.log('🔗 Connection established message received');
        break;
      case 'subscription_response':
        console.log('📋 Subscription response received:', message.data || 'no data');
        break;
      case 'chain_progress':
        if (!message.data) {
          console.log('⚠️  chain_progress message has no data property, skipping');
          return;
        }
        console.log('🔗 Handling chain_progress, calling', this.eventHandlers.chainProgress.length, 'handlers');
        this.eventHandlers.chainProgress.forEach(handler => handler(message.data as ChainProgressUpdate));
        break;
      case 'stage_progress':
        if (!message.data) {
          console.log('⚠️  stage_progress message has no data property, skipping');
          return;
        }
        console.log('🎯 Handling stage_progress, calling', this.eventHandlers.stageProgress.length, 'handlers');
        this.eventHandlers.stageProgress.forEach(handler => handler(message.data as StageProgressUpdate));
        break;
      default:
        // Handle session-specific messages that might not match standard types
        if (message.channel && message.channel.startsWith('session_') && message.data) {
          console.log(`📈 Handling session-specific message for channel: ${message.channel}`);
          
          // Check if this is actually a stage_progress message
          if (message.data && message.data.type === 'stage_progress') {
            console.log('🎯 Found stage_progress message in session-specific handler, calling stage progress handlers');
            this.eventHandlers.stageProgress.forEach(handler => handler(message.data as StageProgressUpdate));
          }
          
          const handlers = this.eventHandlers.sessionSpecific.get(message.channel);
          if (handlers) {
            handlers.forEach(handler => handler(message.data!));
          }
        } else {
          console.log('❓ Unknown message type:', message.type, 'Data present:', !!message.data);
          // Log more details for debugging
          console.log('❓ Message details:', {
            type: message.type,
            channel: message.channel,
            dataType: message.data?.type,
            dataKeys: message.data ? Object.keys(message.data) : []
          });
        }
    }
  }

  /**
   * Schedule reconnection attempt
   */
  private scheduleReconnect(): void {
    if (this.permanentlyDisabled) {
      return;
    }

    // Longer delays for backend restart scenarios: exponential backoff up to 30s
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    
    console.log(`WebSocket reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);
    
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  /**
   * Add event listener for session updates
   */
  onSessionUpdate(handler: WebSocketEventHandler): () => void {
    this.eventHandlers.sessionUpdate.push(handler);
    return () => {
      const index = this.eventHandlers.sessionUpdate.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.sessionUpdate.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for session completion
   */
  onSessionCompleted(handler: WebSocketEventHandler): () => void {
    this.eventHandlers.sessionCompleted.push(handler);
    return () => {
      const index = this.eventHandlers.sessionCompleted.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.sessionCompleted.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for session failure
   */
  onSessionFailed(handler: WebSocketEventHandler): () => void {
    this.eventHandlers.sessionFailed.push(handler);
    return () => {
      const index = this.eventHandlers.sessionFailed.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.sessionFailed.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for dashboard updates
   */
  onDashboardUpdate(handler: WebSocketEventHandler): () => void {
    this.eventHandlers.dashboardUpdate.push(handler);
    return () => {
      const index = this.eventHandlers.dashboardUpdate.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.dashboardUpdate.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for chain progress updates
   */
  onChainProgress(handler: ChainProgressHandler): () => void {
    this.eventHandlers.chainProgress.push(handler);
    return () => {
      const index = this.eventHandlers.chainProgress.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.chainProgress.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for stage progress updates
   */
  onStageProgress(handler: StageProgressHandler): () => void {
    this.eventHandlers.stageProgress.push(handler);
    return () => {
      const index = this.eventHandlers.stageProgress.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.stageProgress.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for session-specific updates
   */
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

  /**
   * Subscribe to a session-specific channel
   */
  subscribeToSessionChannel(sessionId: string): void {
    const channel = `session_${sessionId}`;
    if (this.subscribedChannels.has(channel)) {
      console.log(`Already subscribed to ${channel}`);
      return;
    }

    const subscribeMessage = {
      type: 'subscribe',
      channel: channel
    };
    
    console.log(`📤 Subscribing to session channel: ${channel}`);
    this.send(subscribeMessage);
    this.subscribedChannels.add(channel);
  }

  /**
   * Unsubscribe from a session-specific channel
   */
  unsubscribeFromSessionChannel(sessionId: string): void {
    const channel = `session_${sessionId}`;
    if (!this.subscribedChannels.has(channel)) {
      console.log(`Not subscribed to ${channel}`);
      return;
    }

    const unsubscribeMessage = {
      type: 'unsubscribe',
      channel: channel
    };
    
    console.log(`📤 Unsubscribing from session channel: ${channel}`);
    this.send(unsubscribeMessage);
    this.subscribedChannels.delete(channel);

    // Clean up event handlers for this channel
    this.eventHandlers.sessionSpecific.delete(channel);
  }

  /**
   * Add event listener for connection errors
   */
  onError(handler: WebSocketErrorHandler): () => void {
    this.eventHandlers.error.push(handler);
    return () => {
      const index = this.eventHandlers.error.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.error.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for connection close
   */
  onClose(handler: WebSocketCloseHandler): () => void {
    this.eventHandlers.close.push(handler);
    return () => {
      const index = this.eventHandlers.close.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.close.splice(index, 1);
      }
    };
  }

  /**
   * Add event listener for connection state changes
   */
  onConnectionChange(handler: (connected: boolean) => void): () => void {
    this.eventHandlers.connectionChange.push(handler);
    return () => {
      const index = this.eventHandlers.connectionChange.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.connectionChange.splice(index, 1);
      }
    };
  }

  /**
   * Get current connection state
   */
  get readyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  /**
   * Check if connected
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Check if WebSocket is permanently disabled
   */
  get isDisabled(): boolean {
    return this.permanentlyDisabled;
  }

  /**
   * Get the current user ID
   */
  get currentUserId(): string {
    return this.userId;
  }

  /**
   * Manually retry connection - useful for UI controls
   */
  async retry(): Promise<void> {
    console.log('🔄 Manual retry requested');
    this.resetConnectionState();
    await this.connect();
  }

  /**
   * Cleanup all timers and connections - useful for component unmounting
   */
  cleanup(): void {
    console.log('🧹 Cleaning up WebSocket service');
    
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }

    this.disconnect();
  }
}

// Export singleton instance
export const webSocketService = new WebSocketService(); 