import os, asyncio, json, logging
from typing import Optional, Dict, Any, List
from ..models import StudentProfile
from prometheus_client import Counter

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = int(os.getenv("STUDENT_PROFILE_TTL_DAYS", "30"))
REDIS_OP_TIMEOUT_MS = int(os.getenv("REDIS_OP_TIMEOUT_MS", "25"))  # tighter for hot path

try:
    profile_redis_hit = Counter("profile_redis_hit_total", "Redis hits for profile service")
    profile_redis_miss = Counter("profile_redis_miss_total", "Redis misses for profile service")
    profile_merge_total = Counter("profile_merge_total", "Total profile merges")
except ValueError:
    # metrics already registered
    pass

import re

def normalize_course_code(course_code: str) -> str:
    return re.sub(r'\s+', ' ', course_code.strip().upper())

class StudentProfileService:
    """
    Canonical store for student profiles.
    Keys:
      - student_profile:{student_id} -> JSON(StudentProfile)
    """

    def __init__(self, redis_client):
        self.r = redis_client
        self.ttl = DEFAULT_TTL_DAYS * 24 * 3600

    def _key(self, student_id: str) -> str:
        return f"student_profile:{student_id}"

    async def _get(self, key: str) -> Optional[str]:
        try:
            return await asyncio.wait_for(self.r.get(key), timeout=REDIS_OP_TIMEOUT_MS/1000)
        except Exception as e:
            logger.warning(f"StudentProfile GET failed for {key}: {e}")
            return None

    async def _setex(self, key: str, ttl: int, value: str) -> bool:
        try:
            await asyncio.wait_for(self.r.setex(key, ttl, value), timeout=REDIS_OP_TIMEOUT_MS/1000)
            return True
        except Exception as e:
            logger.warning(f"StudentProfile SETEX failed for {key}: {e}")
            return False

    async def get(self, student_id: str) -> Optional[StudentProfile]:
        key = self._key(student_id)
        raw = await self._get(key)
        if not raw:
            profile_redis_miss.inc()
            return None
        
        profile_redis_hit.inc()
        # Refresh TTL on read
        try:
            await asyncio.wait_for(self.r.expire(key, self.ttl), timeout=REDIS_OP_TIMEOUT_MS/1000)
        except Exception as e:
            logger.warning(f"StudentProfile EXPIRE failed for {key}: {e}")
        data = json.loads(raw)
        return StudentProfile(**data)

    async def put(self, profile: StudentProfile) -> bool:
        profile.completed_courses = [normalize_course_code(c) for c in (profile.completed_courses or [])]
        profile.current_courses = [normalize_course_code(c) for c in (profile.current_courses or [])]
        payload = json.dumps({
            "student_id": profile.student_id,
            "major": profile.major,
            "track": profile.track,
            "minor": profile.minor,
            "year": profile.year,
            "completed_courses": profile.completed_courses or [],
            "current_courses": profile.current_courses or [],
            "interests": profile.interests or [],
            "gpa": profile.gpa,
            "gpa_goal": profile.gpa_goal,
            "risk_tolerance": profile.risk_tolerance,
            "blocked_times": profile.blocked_times or [],
            "preferences": profile.preferences or {}
        })
        return await self._setex(self._key(profile.student_id), self.ttl, payload)

    async def patch(self, student_id: str, updates: Dict[str, Any]) -> Optional[StudentProfile]:
        current = await self.get(student_id)
        if not current:
            # create minimal shell if not exists
            current = StudentProfile(
                student_id=student_id,
                major=updates.get("major"),
                track=updates.get("track"),
                minor=updates.get("minor"),
                year=updates.get("year"),
                completed_courses=updates.get("completed_courses", []),
                current_courses=updates.get("current_courses", []),
                interests=updates.get("interests", []),
                gpa=updates.get("gpa"),
                gpa_goal=updates.get("gpa_goal"),
                risk_tolerance=updates.get("risk_tolerance"),
                blocked_times=updates.get("blocked_times", []),
                preferences=updates.get("preferences", {}),
            )
        else:
            # shallow merge with explicit fields only (avoid surprise attributes)
            if "major" in updates: current.major = updates["major"]
            if "track" in updates: current.track = updates["track"]
            if "minor" in updates: current.minor = updates["minor"]
            if "year" in updates: current.year = updates["year"]
            if "completed_courses" in updates: current.completed_courses = [normalize_course_code(c) for c in updates["completed_courses"]] or []
            if "current_courses" in updates: current.current_courses = [normalize_course_code(c) for c in updates["current_courses"]] or []
            if "interests" in updates: current.interests = updates["interests"] or []
            if "gpa" in updates: current.gpa = updates["gpa"]
            if "gpa_goal" in updates: current.gpa_goal = updates["gpa_goal"]
            if "risk_tolerance" in updates: current.risk_tolerance = updates["risk_tolerance"]
            if "blocked_times" in updates: current.blocked_times = updates["blocked_times"] or []
            if "preferences" in updates: current.preferences = updates["preferences"] or {}

        await self.put(current)
        return current

    async def merge_atomic(self, incoming: StudentProfile) -> StudentProfile:
        """
        Atomic merge using Lua script with CAS semantics.
        Prevents race conditions in concurrent profile updates.
        """
        profile_merge_total.inc()
        if not incoming or not incoming.student_id:
            raise ValueError("merge requires StudentProfile with student_id")
        
        key = self._key(incoming.student_id)
        
        # Lua script for atomic compare-and-swap merge
        lua_script = """
        local key = KEYS[1]
        local ttl = ARGV[1]
        local incoming_json = ARGV[2]
        
        local existing = redis.call('GET', key)
        local incoming = cjson.decode(incoming_json)
        
        local merged
        if existing == false then
            -- No existing profile, use incoming
            merged = incoming
        else
            local existing_data = cjson.decode(existing)
            -- Merge logic: prefer incoming non-empty values
            merged = {
                student_id = existing_data.student_id,
                major = (incoming.major ~= nil and incoming.major ~= "") and incoming.major or existing_data.major,
                track = (incoming.track ~= nil and incoming.track ~= "") and incoming.track or existing_data.track,
                minor = (incoming.minor ~= nil and incoming.minor ~= "") and incoming.minor or existing_data.minor,
                year = (incoming.year ~= nil and incoming.year ~= "") and incoming.year or existing_data.year,
                completed_courses = (#incoming.completed_courses > 0) and incoming.completed_courses or existing_data.completed_courses,
                current_courses = (#incoming.current_courses > 0) and incoming.current_courses or existing_data.current_courses,
                interests = (#incoming.interests > 0) and incoming.interests or existing_data.interests,
                gpa = (incoming.gpa ~= nil) and incoming.gpa or existing_data.gpa,
                gpa_goal = (incoming.gpa_goal ~= nil) and incoming.gpa_goal or existing_data.gpa_goal,
                risk_tolerance = (incoming.risk_tolerance ~= nil and incoming.risk_tolerance ~= "") and incoming.risk_tolerance or existing_data.risk_tolerance,
                blocked_times = (#incoming.blocked_times > 0) and incoming.blocked_times or existing_data.blocked_times,
                preferences = (next(incoming.preferences) ~= nil) and incoming.preferences or existing_data.preferences
            }
        end
        
        local merged_json = cjson.encode(merged)
        redis.call('SETEX', key, ttl, merged_json)
        return merged_json
        """
        
        try:
            # Prepare incoming data
            incoming_data = {
                "student_id": incoming.student_id,
                "major": incoming.major,
                "track": incoming.track,
                "minor": incoming.minor,
                "year": incoming.year,
                "completed_courses": [normalize_course_code(c) for c in (incoming.completed_courses or [])],
                "current_courses": [normalize_course_code(c) for c in (incoming.current_courses or [])],
                "interests": incoming.interests or [],
                "gpa": incoming.gpa,
                "gpa_goal": incoming.gpa_goal,
                "risk_tolerance": incoming.risk_tolerance,
                "blocked_times": incoming.blocked_times or [],
                "preferences": incoming.preferences or {}
            }
            
            result = await asyncio.wait_for(
                self.r.eval(lua_script, 1, key, self.ttl, json.dumps(incoming_data)),
                timeout=REDIS_OP_TIMEOUT_MS/1000
            )
            
            merged_data = json.loads(result)
            return StudentProfile(**merged_data)
            
        except Exception as e:
            logger.error(f"Atomic merge failed for {incoming.student_id}: {e}")
            # Fallback to non-atomic merge
            return await self.merge_fallback(incoming)
    
    async def merge_fallback(self, incoming: StudentProfile) -> StudentProfile:
        """Non-atomic fallback merge for when Lua script fails."""
        existing = await self.get(incoming.student_id)
        if not existing:
            await self.put(incoming)
            return incoming

        # resolve fields
        merged = StudentProfile(
            student_id=existing.student_id,
            major=incoming.major or existing.major,
            track=incoming.track or existing.track,
            minor=incoming.minor or existing.minor,
            year=incoming.year or existing.year,
            completed_courses=[normalize_course_code(c) for c in incoming.completed_courses] if incoming.completed_courses else existing.completed_courses or [],
            current_courses=[normalize_course_code(c) for c in incoming.current_courses] if incoming.current_courses else existing.current_courses or [],
            interests=incoming.interests if incoming.interests else existing.interests or [],
            gpa=incoming.gpa if incoming.gpa is not None else existing.gpa,
            gpa_goal=incoming.gpa_goal if incoming.gpa_goal is not None else existing.gpa_goal,
            risk_tolerance=incoming.risk_tolerance or existing.risk_tolerance,
            blocked_times=incoming.blocked_times if incoming.blocked_times else existing.blocked_times or [],
            preferences=incoming.preferences if incoming.preferences else existing.preferences or {},
        )
        await self.put(merged)
        return merged
    
    # Keep old merge method for backwards compatibility
    async def merge(self, incoming: StudentProfile) -> StudentProfile:
        """Atomic merge with fallback - preferred method."""
        return await self.merge_atomic(incoming)
    
    def to_prompt_budget(self, profile: StudentProfile, max_tokens: int = 200) -> str:
        """
        Prompt budgeter v2: Convert profile to token-efficient prompt format.
        Stores IDs and expands lazily per requirement, staying within token budget.
        """
        if not profile:
            return "Student: Anonymous (no profile data)"
        
        # Core identity (always include)
        parts = [f"Student: {profile.major or 'Undeclared'}"]
        if profile.year:
            parts[0] += f" {profile.year}"
        if profile.track:
            parts[0] += f" ({profile.track} track)"
        
        # Academic progress (high priority)
        if profile.completed_courses:
            completed_count = len(profile.completed_courses)
            if completed_count <= 6:  # Show all if few
                parts.append(f"Completed: {', '.join(profile.completed_courses[:6])}")
            else:  # Summarize if many
                recent = profile.completed_courses[-3:]  # Last 3 as most relevant
                parts.append(f"Completed: {completed_count} courses (recent: {', '.join(recent)})")
        
        # Current load (medium priority)
        if profile.current_courses:
            current_count = len(profile.current_courses)
            if current_count <= 4:
                parts.append(f"Current: {', '.join(profile.current_courses)}")
            else:
                parts.append(f"Current: {current_count} courses")
        
        # Goals and constraints (contextual priority)
        constraints = []
        if profile.gpa_goal:
            constraints.append(f"GPA goal: {profile.gpa_goal}")
        if profile.risk_tolerance:
            constraints.append(f"prefers {profile.risk_tolerance} difficulty")
        if profile.blocked_times:
            blocked_count = len(profile.blocked_times)
            if blocked_count <= 2:
                constraints.append(f"avoids: {', '.join(profile.blocked_times)}")
            else:
                constraints.append(f"has {blocked_count} time constraints")
        
        if constraints:
            parts.append(f"Goals: {'; '.join(constraints)}")
        
        # Interests (lowest priority, space permitting)
        if profile.interests and len(profile.interests) <= 3:
            parts.append(f"Interests: {', '.join(profile.interests[:3])}")
        
        # Assemble with token estimation (rough: 4 chars per token)
        result = ". ".join(parts) + "."
        
        # Truncate if over budget (keep core identity + completed courses)
        if len(result) > max_tokens * 4:
            core = parts[0]
            if len(parts) > 1:  # Add completed courses if possible
                completed_part = parts[1] if parts[1].startswith("Completed:") else ""
                available = max_tokens * 4 - len(core) - 10  # Buffer
                if completed_part and len(completed_part) < available:
                    core += ". " + completed_part
            result = core + "."
        
        return result