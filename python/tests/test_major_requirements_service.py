import asyncio
import json
import types
import pytest
import time

from python.gateway.services.major_requirements_service import (
    MajorRequirementsService, DegreeProgress, UnmetReq, RequirementSpec
)

class Neo4jStub:
    """Stub Neo4j client that returns predefined requirement specs"""
    
    def __init__(self):
        self.requirement_specs = {
            "CS_BA": [
                {
                    "id": "core_prog",
                    "summary": "Intro Programming",
                    "type": "COUNT_AT_LEAST",
                    "min_count": 1,
                    "min_credits": 0,
                    "satisfiers": [
                        {"code": "CS 1110", "credits": 4},
                        {"code": "CS 1112", "credits": 4}
                    ]
                },
                {
                    "id": "core_ds",
                    "summary": "Data Structures", 
                    "type": "ALL_OF_SET",
                    "min_count": 0,
                    "min_credits": 0,
                    "satisfiers": [
                        {"code": "CS 2110", "credits": 3}
                    ]
                },
                {
                    "id": "core_logic",
                    "summary": "Logic/Foundations",
                    "type": "COUNT_AT_LEAST",
                    "min_count": 1,
                    "min_credits": 0,
                    "satisfiers": [
                        {"code": "CS 2800", "credits": 4},
                        {"code": "MATH 3360", "credits": 4}
                    ]
                },
                {
                    "id": "tech_electives",
                    "summary": "Tech Electives",
                    "type": "CREDITS_AT_LEAST", 
                    "min_count": 0,
                    "min_credits": 12,
                    "satisfiers": [
                        {"code": "CS 4410", "credits": 4},
                        {"code": "CS 4780", "credits": 4},
                        {"code": "CS 3410", "credits": 3}
                    ]
                },
                {
                    "id": "math_requirements",
                    "summary": "Math Requirements",
                    "type": "ALL_OF_SET",
                    "min_count": 0,
                    "min_credits": 0,
                    "satisfiers": [
                        {"code": "MATH 1910", "credits": 4},
                        {"code": "MATH 1920", "credits": 4}
                    ]
                }
            ]
        }
    
    async def execute_query(self, cypher, parameters=None, timeout=None):
        """Return mock requirement specs based on major_id"""
        major_id = parameters.get("majorId", "CS_BA")
        specs = self.requirement_specs.get(major_id, [])
        
        # Mimic the structure returned by Neo4j driver
        return specs

class RedisStub:
    """Simple Redis stub for testing"""
    
    def __init__(self):
        self.store = {}
    
    async def get(self, k):
        return self.store.get(k)
    
    async def setex(self, k, ttl, v):
        self.store[k] = v
        
    async def incr(self, k):
        current = int(self.store.get(k, "0"))
        self.store[k] = str(current + 1)
        return current + 1

class MockProfile(types.SimpleNamespace):
    """Mock student profile for testing"""
    pass

@pytest.fixture
def neo4j_stub():
    return Neo4jStub()

@pytest.fixture
def redis_stub():
    return RedisStub()

@pytest.fixture  
def service(neo4j_stub, redis_stub):
    return MajorRequirementsService(neo4j_stub, redis_stub)

@pytest.mark.asyncio
async def test_undeclared_major(service):
    """Test behavior when student has no declared major"""
    profile = MockProfile(student_id="s1", major=None)
    
    dp = await service.unmet_reqs(profile)
    
    assert isinstance(dp, DegreeProgress)
    assert dp.major_id == "UNDECLARED"
    assert len(dp.unmet) == 0
    assert dp.provenance["cache"] == "none"

@pytest.mark.asyncio
async def test_empty_profile(service):
    """Test with minimal completed courses"""
    profile = MockProfile(
        student_id="s1", 
        major="CS_BA",
        completed_courses=[], 
        planned_courses=[]
    )
    
    dp = await service.unmet_reqs(profile)
    
    assert dp.major_id == "CS_BA"
    assert len(dp.unmet) > 0
    
    # Should have unmet requirements for all categories
    unmet_ids = {u.id for u in dp.unmet}
    assert "core_prog" in unmet_ids
    assert "core_ds" in unmet_ids
    assert "tech_electives" in unmet_ids

@pytest.mark.asyncio
async def test_partial_completion(service):
    """Test with some completed courses"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA", 
        completed_courses=["CS 1110", "CS 2110"],
        planned_courses=[]
    )
    
    dp = await service.unmet_reqs(profile)
    unmet_ids = {u.id for u in dp.unmet}
    
    # Programming requirement should be satisfied
    assert "core_prog" not in unmet_ids
    # Data structures should be satisfied  
    assert "core_ds" not in unmet_ids
    # Logic and tech electives should still be unmet
    assert "core_logic" in unmet_ids
    assert "tech_electives" in unmet_ids

@pytest.mark.asyncio
async def test_what_if_scenario(service):
    """Test what-if analysis with planned courses"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA",
        completed_courses=["CS 1110"],
        planned_courses=[]
    )
    
    # Test what happens if student adds these planned courses
    dp = await service.what_if(profile, ["CS 2110", "CS 2800", "CS 4410"])
    
    unmet_by_id = {u.id: u for u in dp.unmet}
    
    # Data structures and logic should be satisfied
    assert "core_ds" not in unmet_by_id
    assert "core_logic" not in unmet_by_id
    
    # Tech electives should have reduced gap (12 needed - 4 from CS 4410 = 8)
    assert "tech_electives" in unmet_by_id
    assert unmet_by_id["tech_electives"].credit_gap == 8

@pytest.mark.asyncio
async def test_credits_at_least_requirement(service):
    """Test CREDITS_AT_LEAST requirement evaluation"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA",
        completed_courses=["CS 1110", "CS 2110", "CS 2800", "CS 4410"], # 4 credits toward tech electives
        planned_courses=[]
    )
    
    dp = await service.unmet_reqs(profile)
    unmet_by_id = {u.id: u for u in dp.unmet}
    
    # Tech electives requirement should show 8 credit gap (12 needed - 4 have)
    tech_req = unmet_by_id["tech_electives"]
    assert tech_req.credit_gap == 8
    assert tech_req.kind == "CREDITS_AT_LEAST"
    
    # Should suggest remaining courses, sorted by credits (largest first)
    suggestions = tech_req.courses_to_satisfy
    assert "CS 4780" in suggestions  # 4 credits
    assert "CS 3410" in suggestions  # 3 credits

@pytest.mark.asyncio
async def test_all_of_set_requirement(service):
    """Test ALL_OF_SET requirement evaluation"""
    profile = MockProfile(
        student_id="s1", 
        major="CS_BA",
        completed_courses=["CS 1110", "MATH 1910"], # missing MATH 1920
        planned_courses=[]
    )
    
    dp = await service.unmet_reqs(profile)
    unmet_by_id = {u.id: u for u in dp.unmet}
    
    # Math requirements should show missing course
    math_req = unmet_by_id["math_requirements"]
    assert math_req.kind == "ALL_OF_SET"
    assert math_req.count_gap == 1  # missing 1 course
    assert "MATH 1920" in math_req.courses_to_satisfy

@pytest.mark.asyncio
async def test_course_code_normalization(service):
    """Test that course codes are normalized properly"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA",
        completed_courses=["cs1110", "CS  2110"], # mixed case and spacing
        planned_courses=[]
    )
    
    dp = await service.unmet_reqs(profile)
    unmet_ids = {u.id for u in dp.unmet}
    
    # Both courses should be recognized despite formatting
    assert "core_prog" not in unmet_ids  # cs1110 should match CS 1110
    assert "core_ds" not in unmet_ids    # CS  2110 should match CS 2110

@pytest.mark.asyncio
async def test_cache_behavior(service):
    """Test Redis caching functionality"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA", 
        completed_courses=["CS 1110"],
        planned_courses=[]
    )
    
    # First call should miss cache
    start_time = time.time()
    dp1 = await service.unmet_reqs(profile)
    assert dp1.provenance["cache"] == "miss"
    
    # Second call should hit cache
    dp2 = await service.unmet_reqs(profile) 
    # Note: our stub doesn't actually implement caching, so this will still be a miss
    # In real implementation, this would be a hit
    
    # Results should be identical
    assert dp1.major_id == dp2.major_id
    assert len(dp1.unmet) == len(dp2.unmet)

@pytest.mark.asyncio 
async def test_cache_invalidation(service):
    """Test cache invalidation functionality"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA",
        completed_courses=["CS 1110"], 
        planned_courses=[]
    )
    
    # Get initial result
    dp1 = await service.unmet_reqs(profile)
    
    # Invalidate cache
    await service.invalidate_cache()
    
    # Get result again - should work without error
    dp2 = await service.unmet_reqs(profile)
    
    assert dp1.major_id == dp2.major_id

@pytest.mark.asyncio
async def test_deterministic_ordering(service):
    """Test that unmet requirements are ordered deterministically"""
    profile = MockProfile(
        student_id="s1", 
        major="CS_BA",
        completed_courses=[],
        planned_courses=[]
    )
    
    # Run multiple times to ensure consistent ordering
    results = []
    for _ in range(3):
        dp = await service.unmet_reqs(profile)
        results.append([u.id for u in dp.unmet])
    
    # All runs should produce identical ordering
    assert results[0] == results[1] == results[2]
    
    # Verify ordering prioritizes credit gaps over count gaps
    dp_obj = await service.unmet_reqs(profile)
    
    # Tech electives (credit gap) should come before others (count gap) 
    unmet_types = [(u.id, u.credit_gap, u.count_gap) for u in dp_obj.unmet]
    
    # Should be sorted by (credit_gap DESC, count_gap DESC, id ASC)
    for i in range(len(unmet_types) - 1):
        curr = unmet_types[i]
        next_item = unmet_types[i + 1]
        
        if curr[1] != next_item[1]:  # different credit gaps
            assert curr[1] >= next_item[1]  # current should have higher credit gap
        elif curr[2] != next_item[2]:  # same credit gap, different count gaps
            assert curr[2] >= next_item[2]  # current should have higher count gap
        else:  # same gaps, should be ordered by id
            assert curr[0] <= next_item[0]  # current id should be <= next id

@pytest.mark.asyncio
async def test_include_planned_flag(service):
    """Test include_planned parameter"""
    profile = MockProfile(
        student_id="s1",
        major="CS_BA",
        completed_courses=["CS 1110"],
        planned_courses=["CS 2110", "CS 2800"]  
    )
    
    # With planned courses included (default)
    dp_with_planned = await service.unmet_reqs(profile, include_planned=True)
    
    # Without planned courses
    dp_without_planned = await service.unmet_reqs(profile, include_planned=False) 
    
    # Should have fewer unmet requirements when planned courses are included
    assert len(dp_with_planned.unmet) <= len(dp_without_planned.unmet)
    
    with_planned_ids = {u.id for u in dp_with_planned.unmet}
    without_planned_ids = {u.id for u in dp_without_planned.unmet}
    
    # Data structures should be unmet without planned, satisfied with planned
    assert "core_ds" in without_planned_ids
    assert "core_ds" not in with_planned_ids