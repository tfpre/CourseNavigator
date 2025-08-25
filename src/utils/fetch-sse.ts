// Robust SSE client using fetch() instead of EventSource to support Bearer auth
// Implements Option A from redisTicket.md - POST streaming with manual SSE parsing

export interface SSEMessage {
  data: string;
  event?: string;
  id?: string;
  retry?: number;
}

export interface FetchSSEOptions {
  headers?: Record<string, string>;
  body?: string; // JSON payload for POST request
  onMessage: (message: SSEMessage) => void;
  onError?: (error: Error) => void;
  onConnectionStatus?: (status: 'connecting' | 'connected' | 'reconnecting' | 'disconnected') => void;
  onHeartbeat?: () => void;
  maxReconnectAttempts?: number;
  heartbeatTimeoutMs?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
}

interface ParsedSSEEvent {
  event?: string;
  data?: string;
  id?: string;
  retry?: number;
}

const BACKOFF_SCHEDULE = [1000, 2000, 4000, 8000, 16000, 30000]; // Progressive backoff

export class FetchSSEClient {
  private url: string;
  private options: Required<FetchSSEOptions>;
  private abortController: AbortController | null = null;
  private reconnectAttempts = 0;
  private isConnected = false;
  private lastHeartbeat = 0;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;

  constructor(url: string, options: FetchSSEOptions) {
    this.url = url;
    this.options = {
      headers: options.headers || {},
      body: options.body,
      onMessage: options.onMessage,
      onError: options.onError || (() => {}),
      onConnectionStatus: options.onConnectionStatus || (() => {}),
      onHeartbeat: options.onHeartbeat || (() => {}),
      maxReconnectAttempts: options.maxReconnectAttempts || 5,
      heartbeatTimeoutMs: options.heartbeatTimeoutMs || 15000,
      initialBackoffMs: options.initialBackoffMs || 1000,
      maxBackoffMs: options.maxBackoffMs || 30000
    };
  }

  async connect(): Promise<void> {
    this.cleanup();
    this.abortController = new AbortController();
    
    try {
      this.options.onConnectionStatus('connecting');
      
      const response = await fetch(this.url, {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache',
          ...this.options.headers
        },
        body: this.options.body,
        signal: this.abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      this.isConnected = true;
      this.reconnectAttempts = 0;
      this.lastHeartbeat = Date.now();
      this.options.onConnectionStatus('connected');
      this.startHeartbeatMonitor();

      await this.processStream(response.body);

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // Intentional abort
      }
      
      this.handleConnectionError(error as Error);
    }
  }

  private async processStream(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer
        
        for (const line of lines) {
          this.processSSELine(line);
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  private processSSELine(line: string): void {
    // Update heartbeat on any line (including comments)
    this.lastHeartbeat = Date.now();
    
    // Handle SSE comments (heartbeats)
    if (line.startsWith(':')) {
      this.options.onHeartbeat();
      return;
    }

    // Empty line triggers event dispatch
    if (line.trim() === '') {
      this.dispatchEvent();
      return;
    }

    // Parse SSE events
    if (line.startsWith('data:') || line.startsWith('event:') || line.startsWith('id:') || line.startsWith('retry:')) {
      this.parseSSEEvent(line);
    }
  }

  private currentEvent: ParsedSSEEvent = {};

  private parseSSEEvent(line: string): void {
    const colonIndex = line.indexOf(':');
    if (colonIndex === -1) return;

    const field = line.slice(0, colonIndex);
    const value = line.slice(colonIndex + 1).trim();

    switch (field) {
      case 'data':
        this.currentEvent.data = (this.currentEvent.data || '') + value + '\n';
        break;
      case 'event':
        this.currentEvent.event = value;
        break;
      case 'id':
        this.currentEvent.id = value;
        break;
      case 'retry':
        this.currentEvent.retry = parseInt(value, 10);
        break;
    }
  }

  private dispatchEvent(): void {
    if (this.currentEvent.data !== undefined) {
      // Remove trailing newline
      const data = this.currentEvent.data.replace(/\n$/, '');
      
      const message: SSEMessage = {
        data,
        event: this.currentEvent.event,
        id: this.currentEvent.id,
        retry: this.currentEvent.retry
      };

      this.options.onMessage(message);
    }
    
    // Reset for next event
    this.currentEvent = {};
  }

  private startHeartbeatMonitor(): void {
    this.stopHeartbeatMonitor();
    
    this.heartbeatTimer = window.setInterval(() => {
      const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeat;
      
      if (timeSinceLastHeartbeat > this.options.heartbeatTimeoutMs) {
        this.handleConnectionError(new Error('Heartbeat timeout'));
      }
    }, 5000); // Check every 5 seconds
  }

  private stopHeartbeatMonitor(): void {
    if (this.heartbeatTimer) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private handleConnectionError(error: Error): void {
    this.isConnected = false;
    this.stopHeartbeatMonitor();
    this.options.onError(error);

    if (this.reconnectAttempts < this.options.maxReconnectAttempts) {
      this.scheduleReconnect();
    } else {
      this.options.onConnectionStatus('disconnected');
    }
  }

  private scheduleReconnect(): void {
    this.options.onConnectionStatus('reconnecting');
    
    const backoffIndex = Math.min(this.reconnectAttempts, BACKOFF_SCHEDULE.length - 1);
    const baseDelay = BACKOFF_SCHEDULE[backoffIndex];
    const jitter = Math.random() * 500; // Add jitter to prevent thundering herd
    const delay = Math.min(baseDelay + jitter, this.options.maxBackoffMs);
    
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  private cleanup(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    this.stopHeartbeatMonitor();
    this.isConnected = false;
  }

  close(): void {
    this.cleanup();
    this.options.onConnectionStatus('disconnected');
  }

  isConnectionActive(): boolean {
    return this.isConnected;
  }
}

// Factory function for easy usage
export function createFetchSSE(url: string, options: FetchSSEOptions): FetchSSEClient {
  return new FetchSSEClient(url, options);
}