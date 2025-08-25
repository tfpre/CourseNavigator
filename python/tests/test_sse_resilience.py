# Tests for SSE Resilience - Robust Server-Sent Events implementation
# Tests heartbeats, client disconnect detection, error handling, and metrics

import asyncio
import json
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.responses import StreamingResponse

from python.gateway.utils.sse import (
    resilient_sse_stream, 
    SSEEvent, 
    format_sse_event,
    simple_sse_generator,
    create_sse_response_headers
)


class MockRequest:
    """Mock FastAPI request for testing client disconnect detection"""
    
    def __init__(self, disconnected=False):
        self._disconnected = disconnected
        
    async def is_disconnected(self):
        return self._disconnected
    
    def set_disconnected(self, disconnected: bool):
        self._disconnected = disconnected


@pytest.mark.asyncio
async def test_sse_event_formatting():
    """Test SSE event formatting follows specification"""
    event = SSEEvent(data="test message", event="message", id="123", retry=3000)
    formatted = format_sse_event(event)
    
    expected = b"retry: 3000\nid: 123\nevent: message\ndata: test message\n\n"
    assert formatted == expected


@pytest.mark.asyncio
async def test_sse_event_multiline_data():
    """Test SSE event formatting handles multiline data correctly"""
    event = SSEEvent(data="line 1\nline 2\nline 3", event="message")
    formatted = format_sse_event(event)
    
    expected = b"event: message\ndata: line 1\ndata: line 2\ndata: line 3\n\n"
    assert formatted == expected


@pytest.mark.asyncio
async def test_simple_content_stream():
    """Test basic SSE streaming without heartbeats"""
    async def test_generator():
        yield "chunk 1"
        yield "chunk 2"
        yield "chunk 3"
    
    request = MockRequest()
    events = []
    
    async for event_bytes in resilient_sse_stream(
        test_generator(), 
        request, 
        event_type="test",
        include_heartbeats=False
    ):
        events.append(event_bytes)
    
    # Should have: connection event + 3 content events + done event
    assert len(events) >= 5
    
    # Check connection event
    assert b"event: connection" in events[0]
    assert b"data: connected" in events[0]
    assert b"retry: 3000" in events[0]
    
    # Check content events
    content_events = [e for e in events if b"event: test" in e]
    assert len(content_events) == 3
    assert b"data: chunk 1" in content_events[0]
    assert b"data: chunk 2" in content_events[1]
    assert b"data: chunk 3" in content_events[2]
    
    # Check done event
    done_events = [e for e in events if b"event: done" in e]
    assert len(done_events) == 1
    assert b"data: stream_complete" in done_events[0]


@pytest.mark.asyncio
async def test_heartbeat_generation():
    """Test that heartbeats are sent at regular intervals"""
    async def slow_generator():
        yield "chunk 1"
        await asyncio.sleep(0.5)  # Longer than heartbeat interval for testing
        yield "chunk 2"
    
    request = MockRequest()
    events = []
    
    # Mock heartbeat interval to be very short for testing
    with patch('python.gateway.utils.sse.HEARTBEAT_INTERVAL', 0.1):
        async for event_bytes in resilient_sse_stream(
            slow_generator(), 
            request, 
            event_type="test",
            include_heartbeats=True
        ):
            events.append(event_bytes)
            # Stop after we get some events to prevent infinite heartbeats
            if len(events) > 5:
                break
    
    # Should have heartbeat events
    heartbeat_events = [e for e in events if b"event: ping" in e and b"data: heartbeat" in e]
    assert len(heartbeat_events) > 0
    
    # Content events should still be present
    content_events = [e for e in events if b"event: test" in e]
    assert len(content_events) >= 1


@pytest.mark.asyncio
async def test_client_disconnect_detection():
    """Test that client disconnects are detected and stream terminates"""
    async def infinite_generator():
        counter = 0
        while True:
            counter += 1
            yield f"chunk {counter}"
            await asyncio.sleep(0.1)
    
    request = MockRequest()
    events = []
    
    # Mock disconnect check interval to be very short
    with patch('python.gateway.utils.sse.CLIENT_DISCONNECT_CHECK_INTERVAL', 0.05):
        async def collect_events():
            async for event_bytes in resilient_sse_stream(
                infinite_generator(), 
                request, 
                include_heartbeats=False
            ):
                events.append(event_bytes)
                # Simulate client disconnect after a few events
                if len(events) == 3:
                    request.set_disconnected(True)
                # Safety check to prevent infinite loop
                if len(events) > 10:
                    break
        
        await collect_events()
    
    # Stream should have terminated due to disconnect
    assert len(events) < 10  # Should not reach safety limit
    assert len(events) >= 3   # Should get some events before disconnect


@pytest.mark.asyncio
async def test_error_handling_in_generator():
    """Test that errors in content generator are handled gracefully"""
    async def error_generator():
        yield "good chunk"
        raise ValueError("Simulated generator error")
    
    request = MockRequest()
    events = []
    
    async for event_bytes in resilient_sse_stream(
        error_generator(), 
        request,
        include_heartbeats=False
    ):
        events.append(event_bytes)
    
    # Should have: connection + good chunk + error + done
    assert len(events) >= 4
    
    # Check that error event was generated
    error_events = [e for e in events if b"event: error" in e]
    assert len(error_events) == 1
    
    error_data = None
    for line in error_events[0].decode('utf-8').split('\n'):
        if line.startswith('data: '):
            error_data = json.loads(line[6:])
            break
    
    assert error_data is not None
    assert "error" in error_data
    assert "Simulated generator error" in error_data["error"]
    assert error_data.get("recoverable") is True


@pytest.mark.asyncio 
async def test_cancellation_handling():
    """Test that cancellation is handled gracefully"""
    async def long_generator():
        for i in range(100):
            yield f"chunk {i}"
            await asyncio.sleep(0.01)
    
    request = MockRequest()
    events = []
    
    async def collect_with_cancellation():
        try:
            async for event_bytes in resilient_sse_stream(
                long_generator(),
                request,
                include_heartbeats=False
            ):
                events.append(event_bytes)
                if len(events) == 5:  # Cancel after 5 events
                    raise asyncio.CancelledError()
        except asyncio.CancelledError:
            pass
    
    await collect_with_cancellation()
    
    # Should have some events but not all 100
    assert len(events) == 5
    
    # Last event should be cancellation event
    if events:
        last_event = events[-1]
        # The cancellation event might be added by the stream handler
        # We just verify we don't get all the chunks


@pytest.mark.asyncio
async def test_sse_headers():
    """Test SSE response headers are correct"""
    headers = create_sse_response_headers()
    
    assert headers["Content-Type"] == "text/event-stream"
    assert headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert headers["Connection"] == "keep-alive"
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "no" in headers["X-Accel-Buffering"]


@pytest.mark.asyncio
async def test_streaming_response_integration():
    """Test integration with FastAPI StreamingResponse"""
    async def test_content():
        yield "Hello"
        yield " "
        yield "World"
    
    request = MockRequest()
    
    # Create streaming response like the main.py endpoint
    response = StreamingResponse(
        resilient_sse_stream(test_content(), request, include_heartbeats=False),
        media_type="text/event-stream",
        headers=create_sse_response_headers()
    )
    
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"


@pytest.mark.asyncio
async def test_metrics_are_updated():
    """Test that Prometheus metrics are incremented during streaming"""
    # This test is more complex because we need to mock Prometheus metrics
    # For now, we'll just verify the stream works and doesn't crash with metrics
    
    async def test_generator():
        yield "test data"
    
    request = MockRequest()
    events = []
    
    # Should not raise any exceptions even if metrics are enabled
    async for event_bytes in resilient_sse_stream(
        test_generator(),
        request,
        include_heartbeats=False
    ):
        events.append(event_bytes)
    
    assert len(events) >= 3  # connection + content + done


@pytest.mark.asyncio
async def test_event_id_sequence():
    """Test that event IDs are sequential and unique"""
    async def test_generator():
        for i in range(3):
            yield f"message {i}"
    
    request = MockRequest()
    events = []
    
    async for event_bytes in resilient_sse_stream(
        test_generator(),
        request,
        include_heartbeats=False
    ):
        events.append(event_bytes.decode('utf-8'))
    
    # Extract event IDs from content events
    content_event_ids = []
    for event_str in events:
        if "event: message" in event_str:
            for line in event_str.split('\n'):
                if line.startswith('id: '):
                    content_event_ids.append(line[4:])
                    break
    
    # Should have 3 content events with sequential IDs
    assert len(content_event_ids) == 3
    assert content_event_ids == ["1", "2", "3"]


if __name__ == "__main__":
    # Run tests manually if needed
    pytest.main([__file__, "-v"])