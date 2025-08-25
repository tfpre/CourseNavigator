import pytest
from fastapi.testclient import TestClient
from gateway.main import app, get_redis
from fastapi import Depends

try:
    import fakeredis.aioredis as fakeredis
except ImportError:
    fakeredis = None

if fakeredis:
    async def _fake_redis():
        return fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = _fake_redis

client = TestClient(app)

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_and_teardown_redis():
    # This is a placeholder for setting up and tearing down a test redis instance
    # For a real application, you would use a library like fakeredis
    # or a separate test database.
    yield


def test_profile_api_flow(setup_and_teardown_redis):
    student_id = "test_student_123"

    # 1. Create a profile
    profile_data = {
        "student_id": student_id,
        "major": "Computer Science",
        "year": "junior",
        "completed_courses": ["CS 1110", "CS 2110"],
        "current_courses": ["CS 3110"],
        "interests": ["machine learning"]
    }
    response = client.put(f"/profiles/{student_id}", json=profile_data, headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json()["major"] == "Computer Science"

    # 2. Get the profile
    response = client.get(f"/profiles/{student_id}", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json()["major"] == "Computer Science"

    # 3. Patch the profile
    patch_data = {"year": "senior"}
    response = client.patch(f"/profiles/{student_id}", json=patch_data, headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json()["year"] == "senior"

    # 4. Get the patched profile
    response = client.get(f"/profiles/{student_id}", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json()["year"] == "senior"
