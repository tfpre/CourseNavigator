import pytest, pytest_asyncio, json
from gateway.services.student_profile_service import StudentProfileService
from gateway.models import StudentProfile

try:
    import fakeredis.aioredis as fakeredis
except Exception:
    fakeredis = None

@pytest_asyncio.fixture
async def r():
    if fakeredis is None:
        pytest.skip("fakeredis not installed")
    rr = fakeredis.FakeRedis(decode_responses=True)
    yield rr
    await rr.flushall(); await rr.close()

@pytest.mark.asyncio
async def test_put_get_roundtrip(r):
    s = StudentProfileService(r)
    p = StudentProfile(student_id="s1", major="CS", year="junior",
                       completed_courses=["CS 1110"], current_courses=["CS 2110"], interests=["ml"])
    ok = await s.put(p); assert ok
    out = await s.get("s1")
    assert out is not None and out.major == "CS" and "CS 1110" in out.completed_courses

@pytest.mark.asyncio
async def test_patch_and_merge(r):
    s = StudentProfileService(r)
    # start empty; patch creates shell
    out = await s.patch("s2", {"major": "Math"})
    assert out.major == "Math"
    # merge prefers incoming non-empty and preserves prior lists
    inc = StudentProfile(student_id="s2", major=None, year="freshman",
                         completed_courses=["MATH 1110"], current_courses=[], interests=[])
    merged = await s.merge(inc)
    assert merged.year == "freshman"
    assert "MATH 1110" in merged.completed_courses
