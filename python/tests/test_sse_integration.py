# Integration test for SSE Resilience - End-to-end streaming verification
# Tests the full chat endpoint with robust SSE streaming

import asyncio
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from python.gateway.main import app, get_chat_orchestrator_service
from python.gateway.models import ChatRequest, StudentProfile


def create_mock_chat_service():
    """Create a mock chat orchestrator service"""
    async def mock_process_chat_request(request):
        # Simulate streaming chat response
        from python.gateway.models import ChatStreamChunk
        
        # Context info chunk
        yield ChatStreamChunk(
            chunk_id=1,
            content="",
            chunk_type="context_info",
            metadata={"status": "Analyzing your request"},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        # Token chunks
        words = ["I", "recommend", "CS", "3110", "for", "advanced", "algorithms"]
        for i, word in enumerate(words, 2):
            yield ChatStreamChunk(
                chunk_id=i,
                content=word + " ",
                chunk_type="token",
                metadata={},
                timestamp="2024-01-01T00:00:00Z"
            )
        
        # Course highlight chunk
        yield ChatStreamChunk(
            chunk_id=len(words) + 2,
            content="",
            chunk_type="course_highlight",
            metadata={"course_code": "CS 3110", "reasoning": "Perfect for algorithms"},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        # Done chunk
        yield ChatStreamChunk(
            chunk_id=len(words) + 3,
            content="",
            chunk_type="done",
            metadata={
                "conversation_id": "test_conv_123",
                "recommended_courses": [{"course_code": "CS 3110", "priority": 1}]
            },
            timestamp="2024-01-01T00:00:00Z"
        )
    
    mock_service = AsyncMock()
    mock_service.process_chat_request = mock_process_chat_request
    return mock_service


@pytest.mark.asyncio
async def test_sse_chat_stream_integration():
    """Test complete SSE streaming integration with chat endpoint"""
    
    # Override dependencies on the main app
    mock_service = create_mock_chat_service()
    app.dependency_overrides[get_chat_orchestrator_service] = lambda: mock_service
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Prepare chat request
            chat_request = ChatRequest(
                message="What algorithms course should I take?",
                student_profile=StudentProfile(
                    student_id="test_student",
                    major="Computer Science",
                    completed_courses=["CS 1110", "CS 2110"],
                    current_courses=[],
                    interests=["Algorithms"]
                ),
                conversation_id=None,
                context_preferences={
                    "include_prerequisites": True,
                    "include_professor_ratings": True,
                    "include_difficulty_info": True
                },
                stream=True,
                max_recommendations=5
            )
            
            # Make streaming request
            async with client.stream(
                "POST",
                "/api/chat",
                json=chat_request.model_dump(),
                headers={"Accept": "text/event-stream"}
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream"
                
                events = []
                content_chunks = []
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        
                        # Skip heartbeat and connection data
                        if data in ["heartbeat", "connected", "stream_complete"]:
                            continue
                        
                        try:
                            chunk_data = json.loads(data)
                            events.append(chunk_data)
                            
                            # Collect content tokens
                            if chunk_data.get("chunk_type") == "token":
                                content_chunks.append(chunk_data.get("content", ""))
                            
                            # Stop when we get done event
                            if chunk_data.get("chunk_type") == "done":
                                break
                                
                        except json.JSONDecodeError:
                            # Skip non-JSON data (like heartbeats)
                            continue
                
                # Verify we got expected events
                assert len(events) > 0
                
                # Check for context info
                context_events = [e for e in events if e.get("chunk_type") == "context_info"]
                assert len(context_events) > 0
                assert "Analyzing" in context_events[0]["metadata"]["status"]
                
                # Check content tokens
                token_events = [e for e in events if e.get("chunk_type") == "token"]
                assert len(token_events) > 0
                
                # Verify content makes sense
                full_content = "".join(content_chunks)
                assert "CS 3110" in full_content
                assert "algorithms" in full_content.lower()
                
                # Check course highlight
                highlight_events = [e for e in events if e.get("chunk_type") == "course_highlight"]
                assert len(highlight_events) > 0
                assert highlight_events[0]["metadata"]["course_code"] == "CS 3110"
                
                # Check done event
                done_events = [e for e in events if e.get("chunk_type") == "done"]
                assert len(done_events) == 1
                assert done_events[0]["metadata"]["conversation_id"] == "test_conv_123"
    
    finally:
        # Clean up dependency overrides
        app.dependency_overrides.clear()


def create_error_mock_service():
    """Create a mock chat service that generates an error"""
    async def error_generator(request):
        # Yield one good chunk then error
        from python.gateway.models import ChatStreamChunk
        
        yield ChatStreamChunk(
            chunk_id=1,
            content="Starting response...",
            chunk_type="token",
            metadata={},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        raise Exception("Simulated processing error")
    
    mock_service = AsyncMock()
    mock_service.process_chat_request = error_generator
    return mock_service


@pytest.mark.asyncio
async def test_sse_error_handling_integration():
    """Test SSE error handling in integration"""
    
    # Override dependencies on the main app
    mock_service = create_error_mock_service()
    app.dependency_overrides[get_chat_orchestrator_service] = lambda: mock_service
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            chat_request = ChatRequest(
                message="Test error handling",
                student_profile=StudentProfile(
                    student_id="test_student",
                    major="Computer Science",
                    completed_courses=[],
                    current_courses=[],
                    interests=[]
                ),
                stream=True
            )
            
            async with client.stream(
                "POST",
                "/api/chat", 
                json=chat_request.model_dump()
            ) as response:
                assert response.status_code == 200
                
                events = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data not in ["heartbeat", "connected", "stream_complete"]:
                            try:
                                events.append(json.loads(data))
                            except json.JSONDecodeError:
                                continue
                    
                    # Stop after we get some events to avoid infinite loop
                    if len(events) > 10:
                        break
                
                # Should have at least one token event and error handling
                token_events = [e for e in events if e.get("chunk_type") == "token"]
                assert len(token_events) > 0
                
                # Error should be handled gracefully (either error event or done event)
                error_or_done = [e for e in events if e.get("chunk_type") in ["error", "done"]]
                assert len(error_or_done) > 0
    
    finally:
        # Clean up dependency overrides
        app.dependency_overrides.clear()


def create_simple_mock_service():
    """Create simple mock chat orchestrator service"""
    async def simple_response(request):
        from python.gateway.models import ChatStreamChunk
        yield ChatStreamChunk(
            chunk_id=1,
            content="test",
            chunk_type="token",
            metadata={},
            timestamp="2024-01-01T00:00:00Z"
        )
        yield ChatStreamChunk(
            chunk_id=2,
            content="",
            chunk_type="done",
            metadata={},
            timestamp="2024-01-01T00:00:00Z"
        )
    
    mock_service = AsyncMock()
    mock_service.process_chat_request = simple_response
    return mock_service


@pytest.mark.asyncio
async def test_sse_headers_and_response_format():
    """Test SSE response headers and format are correct"""
    
    # Override dependencies on the main app
    mock_service = create_simple_mock_service()
    app.dependency_overrides[get_chat_orchestrator_service] = lambda: mock_service
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            chat_request = ChatRequest(
                message="test",
                student_profile=StudentProfile(
                    student_id="test",
                    major="CS",
                    completed_courses=[],
                    current_courses=[],
                    interests=[]
                ),
                stream=True
            )
            
            response = await client.post(
                "/api/chat",
                json=chat_request.model_dump(),
                headers={"Accept": "text/event-stream"}
            )
            
            # Check status and headers
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"
            assert "no-cache" in response.headers.get("cache-control", "")
            assert response.headers.get("connection") == "keep-alive"
            assert response.headers.get("access-control-allow-origin") == "*"
            
            # Response should contain SSE formatted data
            content = response.text
            assert "event:" in content
            assert "data:" in content
            assert "retry:" in content  # Should have retry hint
    
    finally:
        # Clean up dependency overrides
        app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])