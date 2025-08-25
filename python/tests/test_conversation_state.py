import os, json, asyncio, time
import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis
except Exception:
    fakeredis = None

from gateway.services.chat_orchestrator import ChatOrchestratorService
from gateway.services.vector_service import VectorService
from gateway.services.graph_service import GraphService
from gateway.services.rag_service import RAGService
from gateway.models import StudentProfile, ConversationState, ConversationMessage

class DummyVS(VectorService): pass
class DummyGS(GraphService): pass
class DummyRS(RAGService): pass

@pytest_asyncio.fixture
async def fake_redis():
    if fakeredis is None:
        pytest.skip("fakeredis not installed")
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.close()

@pytest.mark.asyncio
async def test_roundtrip_save_load(fake_redis):
    svc = ChatOrchestratorService(DummyVS(), DummyGS(), DummyRS(), redis_client=fake_redis)
    profile = StudentProfile(student_id="t1", major="CS", year="sophomore",
                             completed_courses=["CS 1110"], current_courses=[], interests=["ml"])
    st = ConversationState(conversation_id="conv_test", student_profile=profile, messages=[])
    st.messages.append(ConversationMessage(role="user", content="hi"))
    await svc._save_conversation_state(st)

    # Load back
    out = await svc.get_conversation_state("conv_test")
    assert out is not None
    assert out.student_profile.major == "CS"
    assert out.messages[-1].content == "hi"

@pytest.mark.asyncio
async def test_ttl_is_set(fake_redis, monkeypatch):
    monkeypatch.setenv("REDIS_TTL_DAYS", "1")
    svc = ChatOrchestratorService(DummyVS(), DummyGS(), DummyRS(), redis_client=fake_redis)
    profile = StudentProfile(student_id="t2", major="Math", year="freshman",
                             completed_courses=[], current_courses=[], interests=[])
    st = ConversationState(conversation_id="conv_ttl", student_profile=profile, messages=[])
    await svc._save_conversation_state(st)
    ttl = await fake_redis.ttl("conversation:conv_ttl")
    assert 0 < ttl <= 86400

@pytest.mark.asyncio
async def test_graceful_when_redis_down(monkeypatch):
    class BrokenRedis:
        async def get(self, *a, **k): raise RuntimeError("boom")
        async def setex(self, *a, **k): raise RuntimeError("boom")
        async def ping(self): return False

    svc = ChatOrchestratorService(DummyVS(), DummyGS(), DummyRS(), redis_client=BrokenRedis())
    profile = StudentProfile(student_id="t3", major="CS", year="senior", completed_courses=[], current_courses=[], interests=[])
    st = await svc._load_conversation_state("conv_missing", profile)
    assert st.conversation_id.startswith("conv_")  # created new state
    # save should not raise
    await svc._save_conversation_state(st)