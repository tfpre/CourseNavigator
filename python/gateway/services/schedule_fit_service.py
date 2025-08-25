from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

# Prometheus is optional—guard import so local devs without it don't crash.
try:
    from prometheus_client import Histogram, Counter
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_, **__): return self
        def observe(self, *_): pass
        def inc(self, *_): pass
    Histogram = Counter = _Noop  # type: ignore

SCHEDULE_FIT_TIMEOUT_MS = int(os.getenv("SCHEDULE_FIT_TIMEOUT_MS", "300"))
SCHEDULE_FIT_BEAM_WIDTH = int(os.getenv("SCHEDULE_FIT_BEAM_WIDTH", "1024"))
SCHEDULE_FIT_NODE_LIMIT = int(os.getenv("SCHEDULE_FIT_NODE_LIMIT", "50000"))
SCHEDULE_FIT_GAP_MIN = int(os.getenv("SCHEDULE_FIT_GAP_MIN", "120"))  # minutes
SCHEDULE_FIT_EARLY_MIN = int(os.getenv("SCHEDULE_FIT_EARLY_MIN", "540"))  # 9:00 = 9*60

# Scoring weights (tunable)
W_CONFLICT = float(os.getenv("SCHEDULE_W_CONFLICT", "15"))
W_GAP = float(os.getenv("SCHEDULE_W_GAP", "5"))
W_EARLY = float(os.getenv("SCHEDULE_W_EARLY", "5"))
W_FRIDAY = float(os.getenv("SCHEDULE_W_FRIDAY", "8"))
BONUS_LIGHT_DAY = float(os.getenv("SCHEDULE_BONUS_LIGHT_DAY", "5"))
LIGHT_DAY_HOURS_MAX = float(os.getenv("SCHEDULE_LIGHT_DAY_HOURS_MAX", "4.0"))

# Metrics
schedule_fit_ms = Histogram(
    "schedule_fit_ms",
    "Schedule fit ranking time (ms)"
)
schedule_fit_generated_total = Counter(
    "schedule_fit_generated_total",
    "Schedules generated", ["result"]
)
schedule_fit_candidates_total = Counter(
    "schedule_fit_candidates_total",
    "Candidate evaluation counts", ["status"]
)
schedule_fit_pruned_total = Counter(
    "schedule_fit_pruned_total", 
    "Pruned candidates", ["reason"]
)

# ---- Models ----

DAYS = ("M", "T", "W", "R", "F", "S", "U")  # R=Thursday

class SectionMeeting(BaseModel):
    days: List[str] = Field(default_factory=list, description="e.g., ['M','W']")
    start_min: int  = Field(..., description="minutes since 00:00")
    end_min: int    = Field(..., description="minutes since 00:00 (end > start)")
    campus_tz: str = Field(default="America/New_York")

    @field_validator("days")
    @classmethod
    def _valid_days(cls, v: List[str]) -> List[str]:
        for d in v:
            if d not in DAYS:
                raise ValueError(f"Invalid day: {d}")
        return v

class SectionBundle(BaseModel):
    bundle_id: str
    course_code: str
    meetings: List[SectionMeeting]

class ProfilePrefs(BaseModel):
    dislikes_morning: bool = False
    no_fri: bool = False

class RankedSchedule(BaseModel):
    section_bundle_ids: List[str]
    fit_score: int
    conflict_reason: Optional[str] = None
    # Optional extras for explainability
    total_gaps: int = 0
    earliest_start: int = 0

# ---- Utility functions ----

def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Check if two time intervals overlap."""
    return not (a_end <= b_start or b_end <= a_start)

def _count_conflicts(meetings: List[SectionMeeting]) -> int:
    """Count overlapping meeting pairs on the same day."""
    conflicts = 0
    by_day = {d: [] for d in DAYS}
    for m in meetings:
        for d in m.days:
            by_day[d].append((m.start_min, m.end_min))
    for _, intervals in by_day.items():
        intervals.sort()
        # Simple sweep: compare each with next; list is small per day
        for i in range(len(intervals)):
            for j in range(i + 1, len(intervals)):
                if _overlap(*intervals[i], *intervals[j]):
                    conflicts += 1
    return conflicts

def _count_gaps(meetings: List[SectionMeeting], min_gap: int) -> Tuple[int, int, int]:
    """
    Returns (num_large_gaps, earliest_start_min, max_daily_hours).
    """
    num_gaps = 0
    earliest = 24 * 60
    max_day_hours = 0
    by_day = {d: [] for d in DAYS}
    for m in meetings:
        for d in m.days:
            by_day[d].append((m.start_min, m.end_min))
    for d, intervals in by_day.items():
        if not intervals:
            continue
        intervals.sort()
        earliest = min(earliest, intervals[0][0])
        # total duration for the day
        total = sum(e - s for s, e in intervals)
        max_day_hours = max(max_day_hours, total / 60.0)
        # gaps
        for i in range(1, len(intervals)):
            prev_end = intervals[i - 1][1]
            curr_start = intervals[i][0]
            gap = curr_start - prev_end
            if gap >= min_gap:
                num_gaps += 1
    if earliest == 24 * 60:
        earliest = 0
    return num_gaps, earliest, math.ceil(max_day_hours)

def _has_early(meetings: List[SectionMeeting], early_min: int) -> bool:
    """Check if any meeting starts before early_min (e.g. 540 = 9:00 AM)."""
    for m in meetings:
        if m.start_min < early_min:
            return True
    return False

def _has_friday(meetings: List[SectionMeeting]) -> bool:
    return any("F" in m.days for m in meetings)

def _conflict_pairs(bundles: List[SectionBundle]) -> List[Tuple[str, str]]:
    """Return sorted unique pairs of course_codes that overlap."""
    pairs = set()
    # Build day-wise intervals labeled by course
    by_day = {d: [] for d in DAYS}
    for b in bundles:
        for m in b.meetings:
            for d in m.days:
                by_day[d].append((m.start_min, m.end_min, b.course_code))
    for intervals in by_day.values():
        intervals.sort()  # by start
        for i in range(len(intervals)):
            s1, e1, c1 = intervals[i]
            for j in range(i+1, len(intervals)):
                s2, e2, c2 = intervals[j]
                if _overlap(s1, e1, s2, e2):
                    a, b = sorted((c1, c2))
                    pairs.add((a, b))
    return sorted(pairs)

def _now_ms() -> float:
    return time.perf_counter() * 1000.0

def _score_schedule(meetings: List[SectionMeeting], prefs: ProfilePrefs) -> Tuple[int, dict]:
    score = 100.0
    conflicts = _count_conflicts(meetings)
    score -= W_CONFLICT * conflicts

    gaps, earliest_start, max_day_hours = _count_gaps(meetings, SCHEDULE_FIT_GAP_MIN)
    score -= W_GAP * gaps

    if prefs.dislikes_morning and _has_early(meetings, SCHEDULE_FIT_EARLY_MIN):
        score -= W_EARLY

    if prefs.no_fri and _has_friday(meetings):
        score -= W_FRIDAY

    # Only give light day bonus if ALL days are light (every day ≤ 4 hours)
    all_days_light = True
    by_day = {d: [] for d in DAYS}
    for m in meetings:
        for d in m.days:
            by_day[d].append((m.start_min, m.end_min))
    
    for d, intervals in by_day.items():
        if intervals:  # If there are classes on this day
            total_hours = sum(e - s for s, e in intervals) / 60.0
            if total_hours > LIGHT_DAY_HOURS_MAX:
                all_days_light = False
                break
    
    if all_days_light and any(intervals for intervals in by_day.values()):
        score += BONUS_LIGHT_DAY

    score = max(0, min(100, int(round(score))))
    meta = dict(conflicts=conflicts, gaps=gaps, earliest_start=earliest_start, max_day_hours=max_day_hours)
    return score, meta

# ---- Service ----

class ScheduleFitService:
    """
    Rank conflict-aware schedules across courses by selecting one SectionBundle per course.
    Requires Redis-like client with async get/set/hget/hset/expire operations (aioredis-compatible).
    """

    def __init__(self, redis_client, roster_fetcher=None, term: Optional[str] = None):
        self.r = redis_client
        self.roster_fetcher = roster_fetcher  # Optional async callable(course_code) -> list[SectionBundle]
        self.term = term or os.getenv("ACADEMIC_TERM", "2025SP")

    # ------------------- Redis helpers -------------------

    async def _tagver(self) -> int:
        k = f"tagver:roster:{self.term}"
        v = await self.r.get(k)
        if v is None:
            await self.r.set(k, 1)
            return 1
        return int(v)

    def _mk_cache_key(self, term: str, ver: int, course_code: str) -> str:
        return f"section_bundles:{term}:v{ver}:{course_code}"

    async def _hget_bundles(self, course_code: str) -> Optional[List[SectionBundle]]:
        ver = await self._tagver()
        key = self._mk_cache_key(self.term, ver, course_code)
        v = await self.r.hget(key, "bundles")
        if not v:  # None or empty
            return None
        try:
            blob = json.loads(v)
            return [SectionBundle.model_validate(x) for x in blob]
        except Exception:
            return None

    async def _hset_bundles(self, course_code: str, bundles: List[SectionBundle]) -> None:
        ver = await self._tagver()
        key = self._mk_cache_key(self.term, ver, course_code)
        val = json.dumps([b.model_dump(mode="json") for b in bundles])
        await self.r.hset(key, "bundles", val)
        await self.r.expire(key, 30 * 24 * 3600)  # 30 days

    # ------------------- Demo stub -------------------
    
    def _demo_roster_stub(self, course_code: str) -> List[SectionBundle]:
        """Demo stub that generates realistic section bundles for any course code."""
        # Generate 2-3 bundles with different time patterns
        bundles = []
        
        # Bundle A: MWF morning pattern
        bundles.append(SectionBundle(
            bundle_id=f"{course_code}_A",
            course_code=course_code,
            meetings=[
                SectionMeeting(days=["M", "W", "F"], start_min=600, end_min=650)  # 10:00-10:50
            ]
        ))
        
        # Bundle B: TR afternoon pattern  
        bundles.append(SectionBundle(
            bundle_id=f"{course_code}_B", 
            course_code=course_code,
            meetings=[
                SectionMeeting(days=["T", "R"], start_min=780, end_min=855)  # 1:00-2:15
            ]
        ))
        
        # Bundle C: Evening or different pattern for variety
        if hash(course_code) % 3 == 0:  # Some courses get evening option
            bundles.append(SectionBundle(
                bundle_id=f"{course_code}_C",
                course_code=course_code, 
                meetings=[
                    SectionMeeting(days=["M", "W"], start_min=1080, end_min=1170)  # 6:00-7:30 PM
                ]
            ))
            
        return bundles
    
    # ------------------- ETL entrypoint -------------------

    async def _get_bundles(self, course_code: str) -> List[SectionBundle]:
        cached = await self._hget_bundles(course_code)
        if cached is not None and len(cached) > 0:
            return cached

        if self.roster_fetcher is None:
            # v1 fallback: demo stub to prevent silent failures
            return self._demo_roster_stub(course_code)

        bundles = await self.roster_fetcher(course_code)
        await self._hset_bundles(course_code, bundles)
        return bundles

    # ------------------- Ranking -------------------

    async def rank_schedules(
        self,
        course_codes: List[str],
        prefs: ProfilePrefs,
        limit: int = 3,
    ) -> List[RankedSchedule]:
        t0 = time.perf_counter()
        deadline_ms = _now_ms() + SCHEDULE_FIT_TIMEOUT_MS
        try:
            # Load bundles in parallel
            bundles_lists = await asyncio.gather(
                *[self._get_bundles(code) for code in course_codes]
            )

            # If any course has no options, short-circuit with empty result
            if any(len(lst) == 0 for lst in bundles_lists):
                schedule_fit_generated_total.labels(result="empty").inc()
                return []

            # Order by branching factor (fewest options first)
            ordered = sorted(
                zip(course_codes, bundles_lists),
                key=lambda x: len(x[1])
            )
            ordered_codes = [c for c, _ in ordered]
            options = [b for _, b in ordered]

            # Beam search
            best: List[RankedSchedule] = []
            beam: List[Tuple[int, List[SectionBundle], List[str]]] = [(100, [], [])]  # (optimistic_score, bundles, ids)
            node_count = 0
            found_conflict_free = False

            while options and beam:
                course_idx = len(beam[0][1])  # how many courses selected in each beam item
                # If all selected, break (shouldn't happen here)
                if course_idx == len(options):
                    break

                next_beam: List[Tuple[int, List[SectionBundle], List[str]]] = []
                candidate_bundles = options[course_idx]

                for optimistic, chosen_bundles, chosen_ids in beam:
                    if _now_ms() > deadline_ms:
                        schedule_fit_generated_total.labels(result="timeout").inc()
                        return best[:limit]
                    for b in candidate_bundles:
                        node_count += 1
                        if node_count > SCHEDULE_FIT_NODE_LIMIT:
                            schedule_fit_generated_total.labels(result="timeout").inc()
                            return best[:limit]

                        # Build meetings list with the new bundle
                        meetings = [m for cb in chosen_bundles for m in cb.meetings] + b.meetings

                        # Quick early conflict check
                        conflicts = _count_conflicts(meetings)
                        if found_conflict_free and conflicts > 0:
                            schedule_fit_pruned_total.labels(reason="partial_conflict_after_feasible").inc()
                            schedule_fit_candidates_total.labels(status="pruned").inc()
                            continue  # prune harder after we have at least one conflict-free solution

                        # Compute partial optimistic score (upper bound)
                        # Here we use a simple upper bound = 100 minus current penalties (ignoring future gaps).
                        partial_score, _ = _score_schedule(meetings, prefs)
                        next_beam.append((partial_score, chosen_bundles + [b], chosen_ids + [b.bundle_id]))

                # Keep top-N by optimistic score
                next_beam.sort(key=lambda x: (-x[0], tuple(x[2])))
                beam = next_beam[: SCHEDULE_FIT_BEAM_WIDTH]

                # If we just placed the last course, finalize candidates
                if course_idx + 1 == len(options):
                    finals: List[RankedSchedule] = []
                    for optimistic, bundles, ids in beam:
                        meetings = [m for b in bundles for m in b.meetings]
                        score, meta = _score_schedule(meetings, prefs)
                        reason = None
                        if meta["conflicts"] > 0:
                            # Provide specific conflicting course pairs
                            cps = _conflict_pairs(bundles)
                            if cps:
                                joined = ", ".join([f"{a}×{b}" for a, b in cps[:3]])
                                more = "" if len(cps) <= 3 else f" (+{len(cps)-3} more)"
                                reason = f"Conflicts: {joined}{more}"
                            else:
                                reason = "Time conflicts detected"
                            schedule_fit_candidates_total.labels(status="conflict").inc()
                        elif score < 70:  # Only show other reasons for significantly impacted schedules
                            if meta["gaps"] > 0:
                                reason = "Large mid-day gaps"
                            elif prefs.dislikes_morning and _has_early(meetings, SCHEDULE_FIT_EARLY_MIN):
                                reason = "Early morning starts"
                            elif prefs.no_fri and _has_friday(meetings):
                                reason = "Friday meetings"
                        finals.append(RankedSchedule(
                            section_bundle_ids=ids,
                            fit_score=score,
                            conflict_reason=reason,
                            total_gaps=meta["gaps"],
                            earliest_start=meta["earliest_start"]
                        ))
                        schedule_fit_candidates_total.labels(status="complete").inc()

                    # Sort & dedup identical IDs
                    finals.sort(key=lambda s: (-s.fit_score, s.total_gaps, s.earliest_start, tuple(s.section_bundle_ids)))
                    dedup: List[RankedSchedule] = []
                    seen = set()
                    for s in finals:
                        key = tuple(s.section_bundle_ids)
                        if key in seen: continue
                        seen.add(key)
                        dedup.append(s)
                    # Keep top limit
                    best = dedup[:limit]
                    found_conflict_free = any(s.fit_score == 100 or s.fit_score >= 85 for s in best)

                    break  # finished last layer

            schedule_fit_generated_total.labels(result="ok").inc()
            return best[:limit]
        except Exception:
            schedule_fit_generated_total.labels(result="error").inc()
            return []
        finally:
            schedule_fit_ms.observe((time.perf_counter() - t0) * 1000.0)