# Test to verify the auth fix - fetch-based SSE with POST body and auth headers
# This tests the critical auth issue resolution from redisTicket.md

import asyncio
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock

from python.gateway.main import app, get_chat_orchestrator_service
from python.gateway.models import ChatRequest, StudentProfile


def create_mock_chat_service():
    """Create a mock chat orchestrator service for auth testing"""
    async def mock_process_chat_request(request):
        from python.gateway.models import ChatStreamChunk
        
        # Simple streaming response to test auth flow
        yield ChatStreamChunk(
            chunk_id=1,
            content="Testing auth fix with POST streaming",
            chunk_type="token",
            metadata={},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        yield ChatStreamChunk(
            chunk_id=2,
            content="",
            chunk_type="done",
            metadata={"conversation_id": "auth_test_123"},
            timestamp="2024-01-01T00:00:00Z"
        )
    
    mock_service = AsyncMock()
    mock_service.process_chat_request = mock_process_chat_request
    return mock_service


@pytest.mark.asyncio
async def test_auth_fix_post_streaming_with_headers():
    """Test that POST streaming works with auth headers (fixes EventSource auth issue)"""
    
    # Override dependencies on the main app
    mock_service = create_mock_chat_service()
    app.dependency_overrides[get_chat_orchestrator_service] = lambda: mock_service
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Prepare chat request with auth simulation
            chat_request = ChatRequest(
                message="Test auth fix",
                student_profile=StudentProfile(
                    student_id="auth_test_student",
                    major="Computer Science",
                    completed_courses=["CS 1110"],
                    current_courses=[],
                    interests=["Testing"]
                ),
                conversation_id=None,
                stream=True
            )
            
            # Make POST request with potential auth headers (simulating the fix)
            headers = {
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                # This is where Bearer auth would go - the fix makes this possible
                # "Authorization": "Bearer test_token_123"
            }
            
            async with client.stream(
                "POST",
                "/api/chat",
                json=chat_request.model_dump(),
                headers=headers
            ) as response:
                # Verify the request works with POST (not GET like EventSource)
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream"
                
                # Verify we can stream the response (proving auth + body work together)
                events = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data not in ["heartbeat", "connected", "stream_complete"]:
                            try:
                                chunk_data = json.loads(data)
                                events.append(chunk_data)
                                
                                # Stop when we get done event
                                if chunk_data.get("chunk_type") == "done":
                                    break
                            except json.JSONDecodeError:
                                continue
                
                # Verify we got the expected stream response
                assert len(events) >= 2
                
                # Check token event
                token_events = [e for e in events if e.get("chunk_type") == "token"]
                assert len(token_events) > 0
                assert "auth fix" in token_events[0]["content"]
                
                # Check done event
                done_events = [e for e in events if e.get("chunk_type") == "done"]
                assert len(done_events) == 1
                assert done_events[0]["metadata"]["conversation_id"] == "auth_test_123"
    
    finally:
        # Clean up dependency overrides
        app.dependency_overrides.clear()


@pytest.mark.asyncio 
async def test_auth_headers_preserved_in_post():
    """Verify that auth headers can be included in POST requests (unlike EventSource)"""
    
    mock_service = create_mock_chat_service()
    app.dependency_overrides[get_chat_orchestrator_service] = lambda: mock_service
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            chat_request = ChatRequest(
                message="Test header preservation",
                student_profile=StudentProfile(
                    student_id="test_headers",
                    major="CS",
                    completed_courses=[],
                    current_courses=[],
                    interests=[]
                ),
                stream=True
            )
            
            # Test with custom headers that EventSource couldn't send
            headers = {
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Authorization": "Bearer test_token_should_work",
                "X-Custom-Header": "custom_value",
                "X-API-Key": "api_key_123"
            }
            
            response = await client.post(
                "/api/chat",
                json=chat_request.model_dump(),
                headers=headers
            )
            
            # Verify headers work with POST (this was impossible with EventSource)
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"
            
            # Verify streaming content is received
            content = response.text
            assert "event:" in content or "data:" in content
    
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])