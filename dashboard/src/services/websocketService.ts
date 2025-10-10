/**
 * WebSocket Service - Single connection with channel subscriptions
 */

type EventHandler = (data: any) => void;

interface SubscribedChannel {
  channel: string;
  lastEventId: number;
  handlers: EventHandler[];
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private baseUrl: string = '';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private isConnecting = false;
  private urlResolutionPromise: Promise<void> | null = null;
  
  // Channel subscriptions
  private channels: Map<string, SubscribedChannel> = new Map();
  
  // Global event handlers
  private eventHandlers: Map<string, EventHandler[]> = new Map();
  private connectionHandlers: Array<(connected: boolean) => void> = [];

  constructor() {
    // Initialize base URL from config
    this.urlResolutionPromise = import('../config/env').then(({ urls }) => {
      // Use the WebSocket-specific configuration
      // In development: ws://localhost:8000 (direct to backend)
      // In production: wss://... (from environment config)
      this.baseUrl = urls.websocket.base;
      console.log('✅ WebSocket configured:', this.baseUrl);
    }).catch((error) => {
      console.error('Failed to load WebSocket configuration:', error);
      // Fallback: connect to backend on default port
      this.baseUrl = 'ws://localhost:8000';
      console.log('✅ WebSocket configured (fallback):', this.baseUrl);
    });
  }

  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('Already connected');
      return;
    }

    if (this.isConnecting) {
      console.log('Connection already in progress');
      return;
    }

    this.isConnecting = true;

    try {
      // Wait for URL resolution before connecting
      if (this.urlResolutionPromise) {
        await this.urlResolutionPromise;
        this.urlResolutionPromise = null; // Clear after first use
      }

      // Validate baseUrl is set
      if (!this.baseUrl) {
        throw new Error('WebSocket base URL not configured');
      }

      const wsUrl = `${this.baseUrl}/api/v1/ws`;
      console.log('🔌 Connecting to WebSocket:', wsUrl);
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('✅ WebSocket connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.notifyConnectionChange(true);
        
        // Resubscribe to all channels
        this.resubscribeAll();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleEvent(data);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        this.isConnecting = false;
      };

      this.ws.onclose = () => {
        console.log('🔌 WebSocket closed');
        this.ws = null;
        this.isConnecting = false;
        this.notifyConnectionChange(false);
        this.scheduleReconnect();
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(200 * Math.pow(2, this.reconnectAttempts - 1), 30000);
    console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private resubscribeAll(): void {
    for (const [channel, sub] of this.channels.entries()) {
      this.sendSubscribe(channel);
      
      // Request catchup if we have last event ID
      if (sub.lastEventId > 0) {
        this.sendCatchup(channel, sub.lastEventId);
      }
    }
  }

  private sendSubscribe(channel: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'subscribe',
        channel: channel
      }));
    }
  }

  private sendUnsubscribe(channel: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'unsubscribe',
        channel: channel
      }));
    }
  }

  private sendCatchup(channel: string, lastEventId: number): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'catchup',
        channel: channel,
        last_event_id: lastEventId
      }));
    }
  }

  subscribeToChannel(channel: string, handler: EventHandler): () => void {
    // Create channel subscription if not exists
    if (!this.channels.has(channel)) {
      this.channels.set(channel, {
        channel: channel,
        lastEventId: 0,
        handlers: []
      });
      
      // Send subscribe message if connected
      this.sendSubscribe(channel);
    }

    // Add handler
    const sub = this.channels.get(channel)!;
    sub.handlers.push(handler);

    // Return unsubscribe function
    return () => {
      const sub = this.channels.get(channel);
      if (sub) {
        const index = sub.handlers.indexOf(handler);
        if (index > -1) {
          sub.handlers.splice(index, 1);
        }
        
        // Remove channel if no more handlers
        if (sub.handlers.length === 0) {
          this.sendUnsubscribe(channel);
          this.channels.delete(channel);
        }
      }
    };
  }

  private handleEvent(data: any): void {
    const eventType = data.type;
    
    // Update last event ID for channel
    if (data.id && data.session_id) {
      const sessionChannel = `session:${data.session_id}`;
      const sub = this.channels.get(sessionChannel);
      if (sub) {
        sub.lastEventId = data.id;
      }
    }
    
    if (data.id) {
      const sub = this.channels.get('sessions');
      if (sub && eventType?.startsWith('session.')) {
        sub.lastEventId = data.id;
      }
    }

    // Route to channel-specific handlers
    if (data.session_id) {
      const sessionChannel = `session:${data.session_id}`;
      const sub = this.channels.get(sessionChannel);
      if (sub) {
        sub.handlers.forEach(h => h(data));
      }
    }

    // Route to global handlers
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.forEach(h => h(data));
    }

    // Route 'sessions' channel events
    if (eventType?.startsWith('session.')) {
      const sub = this.channels.get('sessions');
      if (sub) {
        sub.handlers.forEach(h => h(data));
      }
    }
  }

  onEvent(eventType: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);

    return () => {
      const handlers = this.eventHandlers.get(eventType);
      if (handlers) {
        const index = handlers.indexOf(handler);
        if (index > -1) {
          handlers.splice(index, 1);
        }
      }
    };
  }

  onConnectionChange(handler: (connected: boolean) => void): () => void {
    this.connectionHandlers.push(handler);
    return () => {
      const index = this.connectionHandlers.indexOf(handler);
      if (index > -1) {
        this.connectionHandlers.splice(index, 1);
      }
    };
  }

  private notifyConnectionChange(connected: boolean): void {
    this.connectionHandlers.forEach(h => h(connected));
  }

  disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

// Export singleton
export const websocketService = new WebSocketService();

