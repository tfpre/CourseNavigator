import pytest
from fastapi.testclient import TestClient
from ..gateway.main import app, get_redis
from ..gateway.models import StudentProfile, ChatRequest
from fastapi import Depends

try:
    import fakeredis.aioredis as fakeredis
except ImportError:
    fakeredis = None

if fakeredis:
    app.dependency_overrides[get_redis] = lambda: fakeredis.FakeRedis(decode_responses=True)

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_and_teardown_redis():
    yield

def test_chat_integration_with_profile(setup_and_teardown_redis):
    student_id = "test_student_chat_integration"

    # 1. Create a profile
    profile_data = {
        "student_id": student_id,
        "major": "History",
        "year": "senior",
        "completed_courses": ["HIST 101"],
        "current_courses": ["HIST 400"],
        "interests": ["ancient history"]
    }
    response = client.put(f"/profiles/{student_id}", json=profile_data, headers={"Authorization": "Bearer test"})
    assert response.status_code == 200

    # 2. Send a chat message without a profile, but with the same student_id in the conversation_id
    chat_request = ChatRequest(
        message="What should I take next?",
        conversation_id=f"conv_{student_id}"
    )
    
    # This is a placeholder for the actual streaming response handling
    # In a real test, you would iterate over the streaming response and check the content
    response = client.post("/api/chat", json=chat_request.dict())
    assert response.status_code == 200
