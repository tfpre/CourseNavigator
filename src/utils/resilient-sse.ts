// Resilient SSE Client - Production-grade EventSource wrapper with auto-reconnection
// Implements UX Friction Minimization ground truth with robust streaming

import { useRef, useEffect, useState } from 'react';

export interface SSEMessage {
  data: string;
  event: string;
  id?: string;
}

export interface ResilientSSEOptions {
  url: string;
  onMessage: (message: SSEMessage) => void;
  onError?: (error: Error) => void;
  onConnectionStatus?: (status: 'connecting' | 'connected' | 'reconnecting' | 'disconnected') => void;
  onHeartbeat?: () => void;
  maxReconnectAttempts?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  heartbeatTimeoutMs?: number;
}

export class ResilientSSE {
  private es?: EventSource;
  private url: string;
  private options: Required<ResilientSSEOptions>;
  private lastHeartbeat = 0;
  private heartbeatTimer?: number;
  private reconnectAttempts = 0;
  private currentBackoffMs: number;
  private isDestroyed = false;
  private abortController: AbortController;
  private lastEventId?: string;

  // Backoff schedule: 1s, 2s, 4s, 8s, 16s, 30s (max)
  private static readonly BACKOFF_SCHEDULE = [1000, 2000, 4000, 8000, 16000, 30000];

  constructor(options: ResilientSSEOptions) {
    this.url = options.url;
    this.abortController = new AbortController();
    
    // Set defaults for required options
    this.options = {
      url: options.url,
      onMessage: options.onMessage,
      onError: options.onError || (() => {}),
      onConnectionStatus: options.onConnectionStatus || (() => {}),
      onHeartbeat: options.onHeartbeat || (() => {}),
      maxReconnectAttempts: options.maxReconnectAttempts || 10,
      initialBackoffMs: options.initialBackoffMs || 1000,
      maxBackoffMs: options.maxBackoffMs || 30000,
      heartbeatTimeoutMs: options.heartbeatTimeoutMs || 15000,
    };
    
    this.currentBackoffMs = this.options.initialBackoffMs;
  }

  connect(): void {
    if (this.isDestroyed) {
      console.warn('Cannot connect: ResilientSSE instance has been destroyed');
      return;
    }

    this.options.onConnectionStatus('connecting');
    
    // Add Last-Event-ID header for resume capability
    const url = this.lastEventId 
      ? `${this.url}${this.url.includes('?') ? '&' : '?'}lastEventId=${this.lastEventId}`
      : this.url;
    
    this.es = new EventSource(url);
    
    this.es.onopen = () => {
      console.log('SSE connection established');
      this.options.onConnectionStatus('connected');
      this.reconnectAttempts = 0;
      this.currentBackoffMs = this.options.initialBackoffMs;
      this.lastHeartbeat = Date.now();
      this.startHeartbeatMonitoring();
    };

    this.es.onmessage = (event) => {
      this.handleMessage(event);
    };

    // Handle specific event types
    this.es.addEventListener('ping', (event) => {
      this.lastHeartbeat = Date.now();
      this.options.onHeartbeat();
    });

    this.es.addEventListener('error', (event: any) => {
      console.error('SSE error event received:', event);
      this.handleError(new Error(`SSE error event: ${event.data || 'Unknown error'}`));
    });

    this.es.addEventListener('done', (event) => {
      console.log('SSE stream completed successfully');
      this.close(false); // Don't trigger reconnection on normal completion
    });

    this.es.addEventListener('cancelled', (event) => {
      console.log('SSE stream was cancelled');
      this.close(false); // Don't reconnect on cancellation
    });

    this.es.onerror = (event) => {
      console.error('SSE connection error:', event);
      this.handleConnectionError();
    };
  }

  private handleMessage(event: MessageEvent): void {
    this.lastHeartbeat = Date.now();
    
    // Store last event ID for resume capability
    if (event.lastEventId) {
      this.lastEventId = event.lastEventId;
    }

    // Skip done messages (handled by event listener)
    if (event.data === '[DONE]' || event.data === 'stream_complete') {
      this.close(false);
      return;
    }

    // Skip heartbeat data
    if (event.data === 'heartbeat' || event.data === 'connected') {
      return;
    }

    try {
      this.options.onMessage({
        data: event.data,
        event: event.type || 'message',
        id: event.lastEventId
      });
    } catch (error) {
      console.error('Error handling SSE message:', error);
      this.options.onError(error instanceof Error ? error : new Error(String(error)));
    }
  }

  private handleError(error: Error): void {
    console.error('SSE processing error:', error);
    this.options.onError(error);
    this.close(false); // Don't auto-reconnect on processing errors
  }

  private handleConnectionError(): void {
    if (this.isDestroyed || !this.es) {
      return;
    }

    console.warn(`SSE connection error, attempt ${this.reconnectAttempts + 1}`);
    
    // Clean up current connection
    this.cleanup(false);
    
    // Check if we should reconnect
    if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
      console.error(`Max reconnection attempts (${this.options.maxReconnectAttempts}) reached`);
      this.options.onConnectionStatus('disconnected');
      this.options.onError(new Error('Max reconnection attempts reached'));
      return;
    }

    // Schedule reconnection with exponential backoff + jitter
    const backoffIndex = Math.min(this.reconnectAttempts, ResilientSSE.BACKOFF_SCHEDULE.length - 1);
    const baseBackoff = ResilientSSE.BACKOFF_SCHEDULE[backoffIndex];
    const jitter = Math.random() * 500; // Add up to 500ms jitter
    const delay = Math.min(baseBackoff + jitter, this.options.maxBackoffMs);
    
    this.options.onConnectionStatus('reconnecting');
    this.reconnectAttempts++;
    
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => {
      if (!this.isDestroyed) {
        this.connect();
      }
    }, delay);
  }

  private startHeartbeatMonitoring(): void {
    this.stopHeartbeatMonitoring();
    
    const checkInterval = 5000; // Check every 5 seconds
    
    this.heartbeatTimer = window.setInterval(() => {
      const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeat;
      
      if (timeSinceLastHeartbeat > this.options.heartbeatTimeoutMs) {
        console.warn(`No heartbeat for ${timeSinceLastHeartbeat}ms, triggering reconnection`);
        this.handleConnectionError();
      }
    }, checkInterval);
  }

  private stopHeartbeatMonitoring(): void {
    if (this.heartbeatTimer) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = undefined;
    }
  }

  private cleanup(triggerReconnect: boolean = true): void {
    this.stopHeartbeatMonitoring();
    
    if (this.es) {
      this.es.close();
      this.es = undefined;
    }
  }

  close(final: boolean = true): void {
    this.cleanup(false);
    
    if (final) {
      this.isDestroyed = true;
      this.abortController.abort();
      this.options.onConnectionStatus('disconnected');
    }
  }

  // Public API
  get readyState(): number {
    return this.es?.readyState ?? EventSource.CLOSED;
  }

  get connectionStatus(): 'connecting' | 'connected' | 'reconnecting' | 'disconnected' {
    if (this.isDestroyed) return 'disconnected';
    if (!this.es) return 'disconnected';
    
    switch (this.es.readyState) {
      case EventSource.CONNECTING:
        return this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
      case EventSource.OPEN:
        return 'connected';
      case EventSource.CLOSED:
      default:
        return 'disconnected';
    }
  }

  get reconnectAttemptCount(): number {
    return this.reconnectAttempts;
  }

  get isConnected(): boolean {
    return this.es?.readyState === EventSource.OPEN;
  }
}

// Factory function for easier usage
export function createResilientSSE(options: ResilientSSEOptions): ResilientSSE {
  const client = new ResilientSSE(options);
  client.connect();
  return client;
}

// React hook for SSE with automatic cleanup
export function useResilientSSE(options: ResilientSSEOptions) {
  const clientRef = useRef<ResilientSSE | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'reconnecting' | 'disconnected'>('disconnected');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  useEffect(() => {
    // Create SSE client with status tracking
    const client = new ResilientSSE({
      ...options,
      onConnectionStatus: (status) => {
        setConnectionStatus(status);
        setReconnectAttempts(client.reconnectAttemptCount);
        if (options.onConnectionStatus) {
          options.onConnectionStatus(status);
        }
      }
    });
    
    clientRef.current = client;
    client.connect();

    // Cleanup on unmount
    return () => {
      client.close();
      clientRef.current = null;
    };
  }, [options.url]); // Only recreate if URL changes

  return {
    connectionStatus,
    reconnectAttempts,
    isConnected: connectionStatus === 'connected',
    close: () => clientRef.current?.close(),
    reconnect: () => {
      if (clientRef.current) {
        clientRef.current.close();
        clientRef.current.connect();
      }
    }
  };
}