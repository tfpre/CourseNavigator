"""
Tests for PrerequisitePaths critical validation functions
"""

import pytest
from unittest.mock import Mock, AsyncMock

from graph_analysis.pathfinding import PrerequisitePaths


class TestPrerequisitePathsValidation:
    """Test suite for PrerequisitePaths input validation functions"""
    
    @pytest.fixture
    def pathfinding_service(self, mock_neo4j_service):
        """Create pathfinding service with mocked dependencies"""
        return PrerequisitePaths(mock_neo4j_service)
    
    def test_validate_inputs_num_alternatives(self, pathfinding_service):
        """Test validation of num_alternatives parameter"""
        # Valid range
        result = pathfinding_service._validate_inputs(num_alternatives=3)
        assert result["num_alternatives"] == 3
        
        # Too high - should clamp to MAX_ALTERNATIVES
        result = pathfinding_service._validate_inputs(num_alternatives=50)
        assert result["num_alternatives"] == 10  # MAX_ALTERNATIVES
        
        # Too low - should clamp to 1
        result = pathfinding_service._validate_inputs(num_alternatives=0)
        assert result["num_alternatives"] == 1
        
        # Negative - should clamp to 1
        result = pathfinding_service._validate_inputs(num_alternatives=-5)
        assert result["num_alternatives"] == 1
    
    def test_validate_inputs_semesters_available(self, pathfinding_service):
        """Test validation of semesters_available parameter"""
        # Valid range
        result = pathfinding_service._validate_inputs(semesters_available=8)
        assert result["semesters_available"] == 8
        
        # Too high - should clamp to MAX_SEMESTERS
        result = pathfinding_service._validate_inputs(semesters_available=50)
        assert result["semesters_available"] == 20  # MAX_SEMESTERS
        
        # Too low - should clamp to 1
        result = pathfinding_service._validate_inputs(semesters_available=0)
        assert result["semesters_available"] == 1
    
    def test_validate_inputs_max_credits_per_semester(self, pathfinding_service):
        """Test validation of max_credits_per_semester parameter"""
        # Valid range
        result = pathfinding_service._validate_inputs(max_credits_per_semester=18)
        assert result["max_credits_per_semester"] == 18
        
        # Too high - should clamp to MAX_CREDITS_PER_SEMESTER
        result = pathfinding_service._validate_inputs(max_credits_per_semester=50)
        assert result["max_credits_per_semester"] == 30  # MAX_CREDITS_PER_SEMESTER
        
        # Too low - should clamp to 1
        result = pathfinding_service._validate_inputs(max_credits_per_semester=0)
        assert result["max_credits_per_semester"] == 1
    
    def test_validate_inputs_target_courses_list(self, pathfinding_service):
        """Test validation of target_courses list"""
        # Valid list
        courses = ["CS 4780", "CS 4740", "CS 3110"]
        result = pathfinding_service._validate_inputs(target_courses=courses)
        assert result["target_courses"] == courses
        
        # Too many courses - should truncate to MAX_TARGET_COURSES
        long_list = [f"CS {1000 + i}" for i in range(100)]  # 100 courses
        result = pathfinding_service._validate_inputs(target_courses=long_list)
        assert len(result["target_courses"]) == 50  # MAX_TARGET_COURSES
        assert result["target_courses"] == long_list[:50]
        
        # Non-list input - should return empty list
        result = pathfinding_service._validate_inputs(target_courses="not a list")
        assert result["target_courses"] == []
        
        # None input - should return empty list
        result = pathfinding_service._validate_inputs(target_courses=None)
        assert result["target_courses"] == []
    
    def test_validate_inputs_completed_courses_deduplication(self, pathfinding_service):
        """Test validation and deduplication of completed_courses list"""
        # List with duplicates
        courses_with_dupes = ["CS 2110", "MATH 2940", "CS 2110", "CS 3110", "MATH 2940"]
        result = pathfinding_service._validate_inputs(completed_courses=courses_with_dupes)
        
        # Should remove duplicates
        assert len(result["completed_courses"]) == 3
        assert set(result["completed_courses"]) == {"CS 2110", "MATH 2940", "CS 3110"}
        
        # Should handle large lists by truncating to 1000
        large_list = [f"CS {i}" for i in range(2000)]
        result = pathfinding_service._validate_inputs(completed_courses=large_list)
        assert len(result["completed_courses"]) <= 1000
        
        # Non-list input - should return empty list
        result = pathfinding_service._validate_inputs(completed_courses="not a list")
        assert result["completed_courses"] == []
    
    def test_validate_inputs_comprehensive(self, pathfinding_service):
        """Test comprehensive input validation with multiple parameters"""
        inputs = {
            "num_alternatives": 15,  # Too high
            "semesters_available": 0,  # Too low
            "max_credits_per_semester": 50,  # Too high
            "target_courses": ["CS 4780"] * 100,  # Too many
            "completed_courses": ["CS 2110", "CS 2110", "MATH 2940"],  # Duplicates
        }
        
        result = pathfinding_service._validate_inputs(**inputs)
        
        assert result["num_alternatives"] == 10  # Clamped to MAX_ALTERNATIVES
        assert result["semesters_available"] == 1  # Clamped to minimum
        assert result["max_credits_per_semester"] == 30  # Clamped to MAX_CREDITS
        assert len(result["target_courses"]) == 50  # Truncated to MAX_TARGET_COURSES
        assert len(result["completed_courses"]) == 2  # Deduplicated
        assert set(result["completed_courses"]) == {"CS 2110", "MATH 2940"}
    
    def test_is_graph_cache_valid(self, pathfinding_service):
        """Test graph cache validity checking"""
        # Initially invalid (no timestamp)
        assert not pathfinding_service._is_graph_cache_valid()
        
        # Set timestamp to current time
        import time
        pathfinding_service._cache_timestamp = time.time()
        
        # Should be valid now
        assert pathfinding_service._is_graph_cache_valid()
        
        # Set timestamp to old time (beyond TTL)
        pathfinding_service._cache_timestamp = time.time() - 400  # 400 seconds ago
        
        # Should be invalid now (TTL is 300 seconds)
        assert not pathfinding_service._is_graph_cache_valid()
    
    def test_topological_sort_cypher_basic(self, pathfinding_service):
        """Test topological sorting algorithm with basic dependency chain"""
        courses = {"CS 2110", "CS 3110", "CS 4780"}
        predecessors = {
            "CS 2110": set(),  # No prerequisites
            "CS 3110": {"CS 2110"},  # Requires CS 2110
            "CS 4780": {"CS 2110", "CS 3110"}  # Requires both
        }
        
        topo_order = pathfinding_service._topological_sort_cypher(courses, predecessors)
        
        # Should respect dependency order
        assert len(topo_order) == 3
        assert topo_order.index("CS 2110") < topo_order.index("CS 3110")
        assert topo_order.index("CS 2110") < topo_order.index("CS 4780")
        assert topo_order.index("CS 3110") < topo_order.index("CS 4780")
    
    def test_topological_sort_cypher_no_dependencies(self, pathfinding_service):
        """Test topological sorting with courses that have no dependencies"""
        courses = {"MATH 1110", "PHYS 2213", "CHEM 2090"}
        predecessors = {
            "MATH 1110": set(),
            "PHYS 2213": set(), 
            "CHEM 2090": set()
        }
        
        topo_order = pathfinding_service._topological_sort_cypher(courses, predecessors)
        
        # All courses should be included
        assert len(topo_order) == 3
        assert set(topo_order) == courses
    
    def test_topological_sort_cypher_partial_cycle_handling(self, pathfinding_service):
        """Test topological sorting handles cases where not all courses can be ordered"""
        courses = {"A", "B", "C", "D"}
        
        # Create a situation that might have cycles or missing dependencies
        predecessors = {
            "A": set(),
            "B": {"A"},
            "C": {"B"},
            "D": {"E"}  # E is not in courses set - external dependency
        }
        
        topo_order = pathfinding_service._topological_sort_cypher(courses, predecessors)
        
        # Should include all courses even if some can't be properly ordered
        assert len(topo_order) == 4
        assert set(topo_order) == courses
        
        # Should respect the dependencies that can be satisfied
        if "A" in topo_order and "B" in topo_order:
            assert topo_order.index("A") < topo_order.index("B")
        if "B" in topo_order and "C" in topo_order:
            assert topo_order.index("B") < topo_order.index("C")