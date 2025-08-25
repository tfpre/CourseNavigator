# SSE Resilience Utility - Robust Server-Sent Events with heartbeats and reconnection
# Implements UX Friction Minimization ground truth with production-grade streaming

import asyncio
import json
import uuid
import logging
import time
from typing import AsyncIterator, Optional, Dict, Any
from dataclasses import dataclass

# Prometheus metrics with duplicate registration protection
try:
    from prometheus_client import Counter, Histogram
    sse_connections_total = Counter("sse_connections_total", "SSE connections established")
    sse_disconnections_total = Counter("sse_disconnections_total", "SSE client disconnections")
    sse_heartbeats_sent = Counter("sse_heartbeats_sent_total", "SSE heartbeats sent")
    sse_events_sent = Counter("sse_events_sent_total", "SSE events sent", ["event_type"])
    sse_stream_duration = Histogram("sse_stream_duration_seconds", "SSE stream duration", buckets=(1, 5, 10, 30, 60, 300, 600))
except (ImportError, ValueError):
    # Fallback for local development without Prometheus or duplicate registration
    class _NoopMetric:
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    
    sse_connections_total = sse_disconnections_total = sse_heartbeats_sent = _NoopMetric()
    sse_events_sent = sse_stream_duration = _NoopMetric()

logger = logging.getLogger(__name__)

# Configuration constants
HEARTBEAT_INTERVAL = 10.0  # seconds
RETRY_HINT_MS = 3000       # client should retry after 3s
CLIENT_DISCONNECT_CHECK_INTERVAL = 2.0  # check every 2s


@dataclass
class SSEEvent:
    """Structured SSE event"""
    data: str
    event: Optional[str] = None
    id: Optional[str] = None
    retry: Optional[int] = None


def format_sse_event(event: SSEEvent) -> bytes:
    """Format an SSE event according to the specification"""
    lines = []
    
    if event.retry is not None:
        lines.append(f"retry: {event.retry}")
    
    if event.id is not None:
        lines.append(f"id: {event.id}")
    
    if event.event is not None:
        lines.append(f"event: {event.event}")
    
    # Handle multi-line data by splitting and prefixing each line
    for line in event.data.splitlines():
        lines.append(f"data: {line}")
    
    # Add final newline to complete the event
    return "\n".join(lines).encode("utf-8") + b"\n\n"


async def resilient_sse_stream(
    content_generator: AsyncIterator[str], 
    request, 
    event_type: str = "message",
    include_heartbeats: bool = True
) -> AsyncIterator[bytes]:
    """
    Robust SSE stream with heartbeats, client disconnect detection, and proper formatting.
    
    Features:
    - Heartbeat comments every 10s to keep connection alive
    - Automatic client disconnect detection 
    - Proper SSE formatting with retry hints
    - Prometheus metrics integration
    - Graceful cancellation and cleanup
    """
    
    sse_connections_total.inc()
    stream_start = time.time()
    last_heartbeat = time.time()
    event_counter = 0
    
    # Send initial retry hint
    initial_event = SSEEvent(
        data="connected", 
        event="connection", 
        retry=RETRY_HINT_MS,
        id=str(uuid.uuid4())
    )
    yield format_sse_event(initial_event)
    
    # Queue for managing heartbeats and content
    event_queue: asyncio.Queue[bytes] = asyncio.Queue()
    
    async def heartbeat_sender():
        """Background task to send periodic heartbeats"""
        nonlocal last_heartbeat
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                
                # Send heartbeat comment (keeps connection alive)
                heartbeat_event = SSEEvent(data="heartbeat", event="ping")
                await event_queue.put(format_sse_event(heartbeat_event))
                
                sse_heartbeats_sent.inc()
                last_heartbeat = time.time()
                
        except asyncio.CancelledError:
            logger.debug("Heartbeat sender cancelled")
            return
    
    async def content_sender():
        """Background task to process content stream"""
        nonlocal event_counter
        try:
            async for chunk in content_generator:
                event_counter += 1
                
                # Format content as SSE event
                content_event = SSEEvent(
                    data=chunk,
                    event=event_type,
                    id=str(event_counter)
                )
                
                await event_queue.put(format_sse_event(content_event))
                sse_events_sent.labels(event_type=event_type).inc()
                
        except asyncio.CancelledError:
            logger.debug("Content sender cancelled")
            return
        except Exception as e:
            logger.error(f"Content generator error: {e}")
            # Send error event to client
            error_event = SSEEvent(
                data=json.dumps({"error": str(e), "recoverable": True}),
                event="error",
                id=str(event_counter + 1)
            )
            await event_queue.put(format_sse_event(error_event))
        finally:
            # Send completion event
            done_event = SSEEvent(
                data="stream_complete",
                event="done",
                id=str(event_counter + 1)
            )
            await event_queue.put(format_sse_event(done_event))
    
    async def disconnect_checker():
        """Background task to check for client disconnects"""
        try:
            while True:
                await asyncio.sleep(CLIENT_DISCONNECT_CHECK_INTERVAL)
                
                # Check if client disconnected using FastAPI request state
                if hasattr(request, 'is_disconnected') and await request.is_disconnected():
                    logger.info("Client disconnected, terminating SSE stream")
                    sse_disconnections_total.inc()
                    return
                    
        except asyncio.CancelledError:
            return
    
    # Start background tasks
    heartbeat_task = None
    content_task = asyncio.create_task(content_sender())
    disconnect_task = asyncio.create_task(disconnect_checker())
    
    if include_heartbeats:
        heartbeat_task = asyncio.create_task(heartbeat_sender())
    
    try:
        # Main event loop - yield events as they become available
        while True:
            # Check if all tasks are done
            if content_task.done() and (not heartbeat_task or heartbeat_task.cancelled()):
                # Drain any remaining events
                while not event_queue.empty():
                    yield event_queue.get_nowait()
                break
            
            # Check if disconnect checker detected client disconnect
            if disconnect_task.done():
                logger.info("Client disconnect detected, stopping stream")
                break
            
            try:
                # Wait for next event with timeout to check task states
                event_data = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield event_data
                
                # If this was a done event, we can stop
                if b'event: done' in event_data:
                    break
                    
            except asyncio.TimeoutError:
                # No events in queue, check if we should continue
                continue
            
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled")
        # Send cancellation event to client
        cancel_event = SSEEvent(data="cancelled", event="cancelled")
        yield format_sse_event(cancel_event)
        
    except Exception as e:
        logger.exception(f"SSE stream error: {e}")
        # Send error event to client
        error_event = SSEEvent(
            data=json.dumps({"error": str(e), "timestamp": time.time()}),
            event="error"
        )
        yield format_sse_event(error_event)
        
    finally:
        # Cleanup: cancel all background tasks
        tasks_to_cancel = [content_task, disconnect_task]
        if heartbeat_task:
            tasks_to_cancel.append(heartbeat_task)
        
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Record stream duration for observability
        stream_duration = time.time() - stream_start
        sse_stream_duration.observe(stream_duration)
        
        logger.info(f"SSE stream completed in {stream_duration:.2f}s, sent {event_counter} events")


async def simple_sse_generator(content: str, chunk_size: int = 50) -> AsyncIterator[str]:
    """Simple test generator that yields content in chunks"""
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        yield chunk
        # Small delay to simulate realistic streaming
        await asyncio.sleep(0.1)


def create_sse_response_headers() -> Dict[str, str]:
    """Create standard SSE response headers"""
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Cache-Control",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "X-Accel-Buffering": "no",  # Disable nginx buffering
    }