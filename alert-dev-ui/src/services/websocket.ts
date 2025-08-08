/**
 * WebSocket service for real-time progress updates via dashboard websockets
 */

import { ProcessingStatus } from '../types';

export type WebSocketEventHandler = (status: ProcessingStatus) => void;
export type WebSocketErrorHandler = (error: string) => void;
export type WebSocketCloseHandler = () => void;

export class WebSocketService {
  private ws: WebSocket | null = null;
  private alertId: string | null = null;
  private sessionId: string | null = null;
  private userId: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 1000; // Start with 1 second
  private connecting = false; // Prevent multiple simultaneous connection attempts

  // Event handlers
  private onStatusUpdate: WebSocketEventHandler | null = null;
  private onError: WebSocketErrorHandler | null = null;
  private onClose: WebSocketCloseHandler | null = null;

  constructor() {
    this.handleMessage = this.handleMessage.bind(this);
    this.handleError = this.handleError.bind(this);
    this.handleClose = this.handleClose.bind(this);
    
    // Generate a unique user ID for this dev UI instance
    this.userId = `dev-ui-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Connect to dashboard WebSocket and subscribe to session updates
   */
  connect(alertId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        // Prevent multiple simultaneous connection attempts
        if (this.connecting) {
          reject(new Error('Connection already in progress'));
          return;
        }
        
        // If already connected to the same alert, resolve immediately
        if (this.ws?.readyState === WebSocket.OPEN && this.alertId === alertId) {
          resolve();
          return;
        }
        
        // Close existing connection if switching alerts
        if (this.ws && this.alertId !== alertId) {
          this.ws.close();
        }
        
        this.connecting = true;
        this.alertId = alertId;
        const wsUrl = `ws://localhost:8000/ws/dashboard/${this.userId}`;
        
        console.log(`Connecting to dashboard WebSocket: ${wsUrl}`);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = async () => {
          console.log('Dashboard WebSocket connected');
          this.connecting = false;
          this.reconnectAttempts = 0;
          
          // Try to get session ID and subscribe to session channel
          await this.subscribeToSession();
          resolve();
        };

        this.ws.onmessage = this.handleMessage;
        this.ws.onerror = this.handleError;
        this.ws.onclose = this.handleClose;

        // Timeout for connection
        setTimeout(() => {
          if (this.ws?.readyState !== WebSocket.OPEN) {
            this.connecting = false;
            reject(new Error('WebSocket connection timeout'));
          }
        }, 5000);

      } catch (error) {
        console.error('Error creating WebSocket:', error);
        this.connecting = false;
        reject(error);
      }
    });
  }

  /**
   * Get session ID and subscribe to session-specific channel
   */
  // Add retry tracking for session subscription
  private sessionRetryCount = 0;
  private maxSessionRetries = 10;

  private async subscribeToSession(): Promise<void> {
    if (!this.alertId) return;

    try {
      // Get session ID from backend
      const response = await fetch(`http://localhost:8000/session-id/${this.alertId}`);
      const data = await response.json();
      
      if (data.session_id) {
        this.sessionId = data.session_id;
        this.sessionRetryCount = 0; // Reset on success
        console.log(`Got session ID: ${this.sessionId}`);
        
        // Subscribe to session-specific channel
        this.subscribeToChannel(`session_${this.sessionId}`);
      } else {
        if (this.sessionRetryCount >= this.maxSessionRetries) {
          console.error('Max session retries reached');
          return;
        }
        this.sessionRetryCount++;
        console.log('Session ID not available yet, will retry...');
        // Retry after a delay with a simple backoff
        setTimeout(() => this.subscribeToSession(), 2000 * Math.min(this.sessionRetryCount, 5));
      }
    } catch (error) {
      if (this.sessionRetryCount >= this.maxSessionRetries) {
        console.error('Max session retries reached');
        return;
      }
      this.sessionRetryCount++;
      console.error('Error getting session ID:', error);
      // Retry after a delay with a simple backoff
      setTimeout(() => this.subscribeToSession(), 2000 * Math.min(this.sessionRetryCount, 5));
    }
  }

  /**
   * Subscribe to a dashboard websocket channel
   */
  private subscribeToChannel(channel: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('Cannot subscribe - WebSocket not open');
      return;
    }

    const subscriptionMessage = {
      type: 'subscribe',
      channel: channel
    };

    console.log(`Subscribing to channel: ${channel}`);
    this.ws.send(JSON.stringify(subscriptionMessage));
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(event: MessageEvent) {
    try {
      const message: any = JSON.parse(event.data);
      console.log('Dashboard WebSocket message received:', message);

      switch (message.type) {
        case 'connection_established':
          console.log('Dashboard connection established:', message);
          break;
        case 'subscription_response':
          console.log('Subscription response:', message);
          break;
        case 'session_update':
          // Handle session-specific updates
          if (message.data && this.sessionId && message.session_id === this.sessionId) {
            this.handleSessionUpdate(message.data);
          }
          break;
        case 'dashboard_update':
          // Handle general dashboard updates
          if (message.data) {
            this.handleDashboardUpdate(message.data);
          }
          break;
        case 'error':
          if (message.message && this.onError) {
            this.onError(message.message);
          }
          break;
        default:
          console.log('Unknown dashboard message type:', message.type);
      }
    } catch (error) {
      console.error('Error parsing dashboard WebSocket message:', error);
    }
  }

  /**
   * Handle session-specific updates
   */
  private handleSessionUpdate(data: any) {
    console.log('Session update received:', data);
    
    // Try to extract processing status from session update
    if (data.type === 'session_status_change' || data.type === 'llm_interaction' || data.type === 'mcp_communication') {
      // Convert dashboard update to ProcessingStatus format
      const status = this.convertToProcessingStatus(data);
      if (status && this.onStatusUpdate) {
        this.onStatusUpdate(status);
      }
    }
  }

  /**
   * Handle general dashboard updates
   */
  private handleDashboardUpdate(data: any) {
    console.log('Dashboard update received:', data);
    // For now, we mainly care about session-specific updates
  }

  /**
   * Convert dashboard update to ProcessingStatus format
   */
  private convertToProcessingStatus(data: any): ProcessingStatus | null {
    try {
      // Map dashboard update data to ProcessingStatus format
      let status: 'queued' | 'processing' | 'completed' | 'error' = 'processing';
      let progress = 50;
      let currentStep = 'Processing...';
      let result: string | undefined = undefined;
      let error: string | undefined = undefined;

      if (data.type === 'session_status_change') {
        switch (data.status) {
          case 'pending':
            status = 'queued';
            progress = 0;
            currentStep = 'Alert queued for processing';
            break;
          case 'in_progress':
            status = 'processing';
            progress = 50;
            currentStep = 'Processing alert...';
            break;
          case 'completed':
            status = 'completed';
            progress = 100;
            currentStep = 'Processing completed';
            result = data.final_analysis || 'Analysis completed';
            break;
          case 'failed':
            status = 'error';
            progress = 0;
            currentStep = 'Processing failed';
            error = data.error_message || 'Processing failed';
            break;
        }
      } else if (data.type === 'llm_interaction') {
        currentStep = `LLM: ${data.step_description || 'Processing...'}`;
        progress = Math.min(75, 25 + (data.iteration_number || 0) * 10);
      } else if (data.type === 'mcp_communication') {
        currentStep = `Tool: ${data.tool_name || 'Using tool...'}`;
        progress = Math.min(90, 60 + (data.communication_id ? 10 : 0));
      }

      const processingStatus: ProcessingStatus = {
        alert_id: this.alertId || '',
        status,
        progress,
        current_step: currentStep,
        timestamp: new Date().toISOString()
      };

      // Add optional properties if they exist
      if (result) {
        processingStatus.result = result;
      }
      if (error) {
        processingStatus.error = error;
      }

      return processingStatus;
    } catch (err) {
      console.error('Error converting dashboard update to ProcessingStatus:', err);
      return null;
    }
  }

  /**
   * Handle WebSocket errors
   */
  private handleError(event: Event) {
    console.error('WebSocket error:', event);
    if (this.onError) {
      this.onError('WebSocket connection error');
    }
  }

  /**
   * Handle WebSocket close
   */
  private handleClose(event: CloseEvent) {
    console.log('WebSocket closed:', event);
    this.connecting = false;
    
    if (this.onClose) {
      this.onClose();
    }

    // Attempt to reconnect if not intentionally closed
    if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.attemptReconnect();
    }
  }

  /**
   * Attempt to reconnect WebSocket
   */
  private attemptReconnect() {
    this.reconnectAttempts++;
    const delay = this.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`Attempting to reconnect dashboard WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms`);
    
    setTimeout(() => {
      if (this.alertId) {
        this.connect(this.alertId).catch(error => {
          console.error('Dashboard reconnection failed:', error);
        });
      }
    }, delay);
  }

  /**
   * Set status update handler
   */
  onStatusUpdateHandler(handler: WebSocketEventHandler) {
    this.onStatusUpdate = handler;
  }

  /**
   * Set error handler
   */
  onErrorHandler(handler: WebSocketErrorHandler) {
    this.onError = handler;
  }

  /**
   * Set close handler
   */
  onCloseHandler(handler: WebSocketCloseHandler) {
    this.onClose = handler;
  }

  /**
   * Send a message through WebSocket
   */
  send(message: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not open. Cannot send message:', message);
    }
  }

  /**
   * Close WebSocket connection
   */
  disconnect() {
    if (this.ws) {
      console.log('Closing dashboard WebSocket connection');
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.alertId = null;
    this.sessionId = null;
    this.reconnectAttempts = 0;
    this.connecting = false;
  }

  /**
   * Get connection status
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export default WebSocketService; 