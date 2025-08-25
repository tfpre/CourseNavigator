import asyncio
import json
import types
import pytest

from python.gateway.services.schedule_fit_service import (
    ScheduleFitService, SectionMeeting, SectionBundle, ProfilePrefs
)

class DummyRedis:
    def __init__(self): self.store = {}
    async def get(self, k): return self.store.get(k)
    async def set(self, k, v): self.store[k] = str(v)
    async def hget(self, k, f): return self.store.get((k,f))
    async def hset(self, k, f, v): self.store[(k,f)] = v
    async def expire(self, k, ttl): return 1

async def roster_no_conflict(_code):
    bundles = [
        SectionBundle(bundle_id="A", course_code="MATH 1910",
                      meetings=[SectionMeeting(days=["M","W"], start_min=610, end_min=660)]),
        SectionBundle(bundle_id="B", course_code="MATH 1910",
                      meetings=[SectionMeeting(days=["T","R"], start_min=700, end_min=750)]),
    ]
    return bundles

@pytest.mark.asyncio
async def test_no_conflict_high_score():
    r = DummyRedis()
    svc = ScheduleFitService(r, roster_fetcher=lambda _: roster_no_conflict(_))
    ranked = await svc.rank_schedules(["MATH 1910"], ProfilePrefs(), limit=3)
    assert ranked and ranked[0].fit_score >= 85

@pytest.mark.asyncio
async def test_conflict_penalized():
    async def roster_both(_code):
        # Two courses that overlap on M
        if _code == "CS 1110":
            return [SectionBundle(bundle_id="CS", course_code=_code,
                                  meetings=[SectionMeeting(days=["M"], start_min=600, end_min=660)])]
        return [SectionBundle(bundle_id="MATH", course_code=_code,
                              meetings=[SectionMeeting(days=["M"], start_min=630, end_min=690)])]
    r = DummyRedis()
    svc = ScheduleFitService(r, roster_fetcher=roster_both)
    ranked = await svc.rank_schedules(["CS 1110", "MATH 1910"], ProfilePrefs(), limit=3)
    assert ranked and ranked[0].fit_score == 90  # 100 - 15 (conflict) + 5 (light day) = 90
    assert ranked[0].conflict_reason

@pytest.mark.asyncio 
async def test_prefs_penalties():
    async def roster_morning(_code):
        # Heavy single-day schedule: >4 hours so no light day bonus
        return [SectionBundle(bundle_id="AM", course_code=_code,
                              meetings=[
                                  SectionMeeting(days=["M"], start_min=480, end_min=540),  # 8-9am Mon
                                  SectionMeeting(days=["M"], start_min=600, end_min=660),  # 10-11am Mon
                                  SectionMeeting(days=["M"], start_min=720, end_min=780),  # 12-1pm Mon  
                                  SectionMeeting(days=["M"], start_min=840, end_min=900),  # 2-3pm Mon
                                  SectionMeeting(days=["M"], start_min=960, end_min=1020), # 4-5pm Mon (5+ hours total)
                              ])]
    r = DummyRedis()
    svc = ScheduleFitService(r, roster_fetcher=roster_morning)
    ranked = await svc.rank_schedules(["BIO 1350"], ProfilePrefs(dislikes_morning=True), limit=1)
    assert ranked and ranked[0].fit_score == 95  # 100 - 5 (early penalty), no light day bonus due to heavy schedule

@pytest.mark.asyncio
async def test_conflict_reasons_specific():
    async def roster_conflicts(_code):
        # Two courses with specific overlap
        if _code == "CS 1110":
            return [SectionBundle(bundle_id="CS", course_code="CS 1110",
                                  meetings=[SectionMeeting(days=["M"], start_min=600, end_min=660)])]
        return [SectionBundle(bundle_id="MATH", course_code="MATH 1910",
                              meetings=[SectionMeeting(days=["M"], start_min=630, end_min=690)])]
    r = DummyRedis()
    svc = ScheduleFitService(r, roster_fetcher=roster_conflicts)
    ranked = await svc.rank_schedules(["CS 1110", "MATH 1910"], ProfilePrefs(), limit=1)
    assert ranked and ranked[0].conflict_reason
    assert "CS 1110×MATH 1910" in ranked[0].conflict_reason
    assert "Conflicts:" in ranked[0].conflict_reason

@pytest.mark.asyncio
async def test_demo_stub_functionality():
    # Test demo stub (no roster_fetcher provided)
    r = DummyRedis()
    svc = ScheduleFitService(r, roster_fetcher=None)
    ranked = await svc.rank_schedules(["CS 2110", "MATH 2940"], ProfilePrefs(), limit=2)
    assert len(ranked) > 0  # Should not return empty
    assert ranked[0].fit_score > 0  # Should have valid scores
    # All bundle IDs should contain course codes
    for schedule in ranked:
        for bundle_id in schedule.section_bundle_ids:
            assert "CS 2110" in bundle_id or "MATH 2940" in bundle_id