from __future__ import annotations

import asyncio
import json
import time
import re
import random
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple, Set

# Prometheus is optional—guard import so local devs without it don't crash.
try:
    from prometheus_client import Histogram, Counter
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_, **__): return self
        def observe(self, *_): pass
        def inc(self, *_): pass
    Histogram = Counter = _Noop  # type: ignore

# Prometheus metrics with duplicate registration protection
try:
    major_reqs_ms = Histogram(
        "major_reqs_ms", 
        "Time to evaluate major requirements", 
        buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5)
    )
    major_reqs_cache_hits = Counter("major_reqs_cache_hits_total", "Cache hits for major requirements")
    major_reqs_cache_misses = Counter("major_reqs_cache_misses_total", "Cache misses for major requirements")
except ValueError:
    # Metrics already registered, use noop
    class _Noop:
        def labels(self, *_, **__): return self
        def observe(self, *_): pass
        def inc(self, *_): pass
    major_reqs_ms = major_reqs_cache_hits = major_reqs_cache_misses = _Noop()  # type: ignore

# Default assumptions when course.credits is missing
DEFAULT_COURSE_CREDITS = 3

@dataclass
class RequirementSpec:
    id: str
    summary: str
    type: str                   # "COUNT_AT_LEAST" | "CREDITS_AT_LEAST" | "ALL_OF_SET"
    min_count: int = 0
    min_credits: int = 0
    # list of satisfier course codes with optional credits (sourced from Neo4j)
    satisfiers: List[Dict[str, Any]] = None

@dataclass
class UnmetReq:
    id: str
    summary: str
    kind: str                   # mirrors RequirementSpec.type
    count_gap: int = 0
    credit_gap: int = 0
    courses_to_satisfy: List[str] = None

@dataclass
class DegreeProgress:
    major_id: str
    unmet: List[UnmetReq]
    as_of: float
    provenance: Dict[str, Any]

class MajorRequirementsService:
    """
    Evaluates degree progress for a given major using the requirement graph in Neo4j.
    Caches computed results in Redis for 12h. No N+1 queries: one round-trip per evaluation.
    """
    def __init__(self, neo4j_client, redis_client, *, default_ttl_seconds: int = 12 * 3600):
        self.neo4j = neo4j_client
        self.redis = redis_client
        self.default_ttl = default_ttl_seconds

    # ---------- Public API ----------

    async def unmet_reqs(self, student_profile, *, include_planned: bool = True) -> DegreeProgress:
        """
        Compute unmet requirements for student's declared major.
        StudentProfile must expose: student_id, major (id/string), completed_courses (List[str]), planned_courses (List[str])
        """
        if not student_profile or not getattr(student_profile, "major", None):
            return DegreeProgress(major_id="UNDECLARED", unmet=[], as_of=time.time(),
                                  provenance={"source": "neo4j", "as_of": time.time(), "cache": "none"})

        major_id = student_profile.major
        completed: Set[str] = {self._norm(c) for c in (student_profile.completed_courses or [])}
        planned: Set[str] = {self._norm(c) for c in (student_profile.planned_courses or [])} if include_planned else set()
        have: Set[str] = completed | planned

        tagver = await self._get_tagver()
        cache_key = self._cache_key(student_profile.student_id, major_id, sorted(list(have)), tagver)
        cached = await self.redis.get(cache_key)
        if cached:
            major_reqs_cache_hits.inc()
            data = json.loads(cached)
            # Reconstruct UnmetReq objects from cached dicts
            unmet_reqs = [UnmetReq(**req_dict) for req_dict in data["unmet"]]
            data["unmet"] = unmet_reqs
            return DegreeProgress(**data)

        major_reqs_cache_misses.inc()
        start = time.perf_counter()
        try:
            specs = await self._load_requirement_specs(major_id)
            unmet = self._evaluate_unmet(specs, have)
            result = DegreeProgress(
                major_id=major_id,
                unmet=unmet,
                as_of=time.time(),
                provenance={"source": "neo4j", "as_of": time.time(), "cache": "miss"}
            )
            # Add TTL jitter to reduce stampedes
            ttl = self.default_ttl + random.randint(0, 300)  # + up to 5 min
            await self.redis.setex(cache_key, ttl, json.dumps(self._serialize(result)))
            return result
        finally:
            major_reqs_ms.observe(time.perf_counter() - start)

    async def what_if(self, student_profile, planned_courses: List[str]) -> DegreeProgress:
        """
        Evaluate 'what if' adding planned_courses (list of course codes like 'CS 3110').
        """
        planned_courses = planned_courses or []
        extended = type("Tmp", (), {})()
        for attr in ("student_id", "major", "completed_courses", "planned_courses"):
            setattr(extended, attr, getattr(student_profile, attr, None))
        extended.planned_courses = list(set((student_profile.planned_courses or []) + planned_courses))
        # bypass cache to reflect ad-hoc scenario
        specs = await self._load_requirement_specs(extended.major)
        have = {self._norm(c) for c in ((extended.completed_courses or []) + (extended.planned_courses or []))}
        unmet = self._evaluate_unmet(specs, have)
        return DegreeProgress(
            major_id=extended.major,
            unmet=unmet,
            as_of=time.time(),
            provenance={"source": "neo4j", "as_of": time.time(), "cache": "none", "what_if": planned_courses}
        )

    async def invalidate_cache(self, student_id: Optional[str] = None) -> None:
        """
        Version-based invalidation: bump tag version so stale keys expire naturally via TTL.
        """
        tag_key = "tagver:degree_reqs"
        await self.redis.incr(tag_key)

    # ---------- Internals ----------

    @staticmethod
    def _norm(code: str) -> str:
        """Normalize course codes to canonical SUBJ NNNN format"""
        if not code: return ""
        s = code.upper().replace("\xa0", " ").strip()
        s = " ".join(s.split())  # collapse spaces
        # insert a space if pattern like CS3110
        m = re.fullmatch(r"([A-Z]{2,4})\s*([0-9]{3,4}[A-Z]?)", s)
        return f"{m.group(1)} {m.group(2)}" if m else s

    def _cache_key(self, student_id: str, major_id: str, have_sorted: List[str], tagver: int) -> str:
        # versioned tag cache to avoid delete storms
        import hashlib
        h = hashlib.sha1("|".join(have_sorted).encode()).hexdigest()[:12]
        return f"degree_reqs:v{tagver}:sid:{student_id}:major:{major_id}:h:{h}"

    async def _get_tagver(self) -> int:
        """Get current tag version for cache invalidation"""
        try:
            v = await self.redis.get("tagver:degree_reqs")
            return int(v) if v else 1
        except Exception:
            return 1

    async def _load_requirement_specs(self, major_id: str) -> List[RequirementSpec]:
        """
        Single round-trip Cypher that returns requirement specs and satisfier course lists (code + credits).
        """
        cypher = """
        MATCH (m:Major {id: $majorId})-[:REQUIRES]->(r:Requirement)
        OPTIONAL MATCH (r)-[:SATISFIED_BY]->(c:Course)
        WITH r,
             collect(DISTINCT {code: c.code, credits: coalesce(c.credits, $defaultCredits)}) AS sat
        RETURN r.id AS id,
               coalesce(r.summary, r.id) AS summary,
               coalesce(r.type, 'COUNT_AT_LEAST') AS type,
               coalesce(r.min_count, 0) AS min_count,
               coalesce(r.min_credits, 0) AS min_credits,
               sat AS satisfiers
        ORDER BY id
        """
        rows = await self.neo4j.execute_query(
            cypher,
            parameters={"majorId": major_id, "defaultCredits": DEFAULT_COURSE_CREDITS},
            timeout=0.2  # 200ms safety
        )
        # Normalize to list[dict] - handle different Neo4j driver return shapes
        if hasattr(rows, "records"):
            it = (r.data() for r in rows.records)   # neo4j v5 EagerResult
        elif isinstance(rows, tuple) and hasattr(rows[0], "__iter__"):
            it = (r.data() if hasattr(r, "data") else r for r in rows[0])  # some wrappers return (records, summary, keys)
        else:
            it = iter(rows)

        specs: List[RequirementSpec] = []
        for row in it:
            specs.append(RequirementSpec(
                id=row["id"],
                summary=row["summary"],
                type=row["type"],
                min_count=row["min_count"],
                min_credits=row["min_credits"],
                satisfiers=row["satisfiers"] or []
            ))
        return specs

    def _evaluate_unmet(self, specs: List[RequirementSpec], have: Set[str]) -> List[UnmetReq]:
        """
        Pure-Python evaluation; tolerant to missing credits; deterministic output for prompt stability.
        """
        unmet: List[UnmetReq] = []
        have_upper = {self._norm(c) for c in have}

        for s in specs:
            sat_codes = [self._norm(x.get("code") or "") for x in (s.satisfiers or []) if x.get("code")]
            sat_credits = {
                self._norm(x.get("code") or ""): int(x.get("credits") or DEFAULT_COURSE_CREDITS)
                for x in (s.satisfiers or []) if x.get("code")
            }
            have_here = [code for code in sat_codes if code in have_upper]

            if s.type == "ALL_OF_SET":
                missing = [code for code in sat_codes if code not in have_here]
                if missing:
                    unmet.append(UnmetReq(
                        id=s.id,
                        summary=s.summary,
                        kind=s.type,
                        count_gap=len(missing),
                        credit_gap=0,
                        courses_to_satisfy=missing[:5]
                    ))
                continue

            if s.type == "COUNT_AT_LEAST":
                have_count = len(have_here)
                gap = max(0, int(s.min_count) - have_count)
                if gap > 0:
                    suggestions = [c for c in sat_codes if c not in have_here][:max(1, gap*2)]
                    unmet.append(UnmetReq(
                        id=s.id,
                        summary=s.summary,
                        kind=s.type,
                        count_gap=gap,
                        credit_gap=0,
                        courses_to_satisfy=suggestions
                    ))
                continue

            if s.type == "CREDITS_AT_LEAST":
                have_credits = sum(sat_credits.get(c, DEFAULT_COURSE_CREDITS) for c in have_here)
                gap = max(0, int(s.min_credits) - have_credits)
                if gap > 0:
                    # choose largest-credit remaining first
                    remaining = sorted(
                        [c for c in sat_codes if c not in have_here],
                        key=lambda c: -sat_credits.get(c, DEFAULT_COURSE_CREDITS)
                    )
                    unmet.append(UnmetReq(
                        id=s.id,
                        summary=s.summary,
                        kind=s.type,
                        count_gap=0,
                        credit_gap=gap,
                        courses_to_satisfy=remaining[:5]
                    ))
                continue

            # default: treat as COUNT_AT_LEAST 1
            if not have_here:
                suggestions = sat_codes[:3]
                unmet.append(UnmetReq(
                    id=s.id, summary=s.summary, kind="COUNT_AT_LEAST",
                    count_gap=1, credit_gap=0, courses_to_satisfy=suggestions
                ))

        # Stable ordering by largest gap then id; helps prompt determinism
        def _priority(u: UnmetReq) -> Tuple[int, int, str]:
            # Sort by credit_gap DESC, count_gap DESC, id ASC (alphabetical)
            return (-u.credit_gap, -u.count_gap, u.id)
        return sorted(unmet, key=_priority)

    def _serialize(self, dp: DegreeProgress) -> Dict[str, Any]:
        return {
            "major_id": dp.major_id,
            "unmet": [asdict(u) for u in dp.unmet],
            "as_of": dp.as_of,
            "provenance": dp.provenance,
        }