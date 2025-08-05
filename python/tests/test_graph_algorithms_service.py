"""
Tests for GraphAlgorithmsService critical utility functions
"""

import pytest
import time
import hashlib
from unittest.mock import Mock, AsyncMock, patch

from gateway.services.graph_algorithms_service import GraphAlgorithmsService


class TestGraphAlgorithmsService:
    """Test suite for GraphAlgorithmsService utility functions"""
    
    @pytest.fixture
    def service(self, mock_neo4j_service):
        """Create service instance with mocked dependencies"""
        return GraphAlgorithmsService(mock_neo4j_service)
    
    def test_get_cache_key_basic(self, service):
        """Test cache key generation with basic parameters"""
        operation = "centrality"
        params = {"top_n": 20, "damping_factor": 0.85}
        
        key = service._get_cache_key(operation, **params)
        
        # Should be deterministic
        key2 = service._get_cache_key(operation, **params)
        assert key == key2
        
        # Should include operation and sorted parameters
        assert "centrality" in key
        assert "damping_factor=0.85" in key
        assert "top_n=20" in key
    
    def test_get_cache_key_with_lists(self, service):
        """Test cache key generation with list parameters (critical for stability)"""
        operation = "paths"
        
        # Same lists in different order should produce same key
        params1 = {"completed_courses": ["CS 2110", "MATH 2940"]}
        params2 = {"completed_courses": ["MATH 2940", "CS 2110"]}
        
        key1 = service._get_cache_key(operation, **params1)
        key2 = service._get_cache_key(operation, **params2)
        
        assert key1 == key2  # Critical: order should not matter
    
    def test_get_cache_key_empty_lists(self, service):
        """Test cache key generation with empty lists"""
        operation = "test"
        params = {"empty_list": [], "normal_param": "value"}
        
        key = service._get_cache_key(operation, **params)
        
        # Should handle empty lists gracefully
        assert key is not None
        assert "empty_list=" in key
        assert "normal_param=value" in key
    
    def test_get_cache_key_long_params(self, service):
        """Test cache key generation with long parameter string"""
        operation = "test"
        params = {
            "very_long_param": "x" * 500,  # Long string that will trigger SHA256
            "courses": ["CS " + str(i) for i in range(100)]  # Long list
        }
        
        key = service._get_cache_key(operation, **params)
        
        # Should use SHA256 for long strings
        assert len(key) == 64  # SHA256 hex digest length
        
        # Should be deterministic
        key2 = service._get_cache_key(operation, **params)
        assert key == key2
    
    def test_validate_inputs_top_n(self, service):
        """Test input validation for top_n parameter"""
        # Valid range
        result = service._validate_inputs(top_n=50)
        assert result["top_n"] == 50
        
        # Too high - should clamp
        result = service._validate_inputs(top_n=2000)
        assert result["top_n"] == 1000  # MAX_TOP_N
        
        # Too low - should clamp
        result = service._validate_inputs(top_n=-5)
        assert result["top_n"] == 20  # Default
        
        # Zero - should default
        result = service._validate_inputs(top_n=0)
        assert result["top_n"] == 20
    
    def test_validate_inputs_damping_factor(self, service):
        """Test input validation for damping factor"""
        # Valid range
        result = service._validate_inputs(damping_factor=0.85)
        assert result["damping_factor"] == 0.85
        
        # Too high - should clamp
        result = service._validate_inputs(damping_factor=1.5)
        assert result["damping_factor"] == 0.99  # MAX_DAMPING_FACTOR
        
        # Too low - should clamp
        result = service._validate_inputs(damping_factor=-0.1)
        assert result["damping_factor"] == 0.01  # MIN_DAMPING_FACTOR
    
    def test_validate_inputs_algorithm(self, service):
        """Test input validation for algorithm parameter"""
        # Valid algorithm
        result = service._validate_inputs(algorithm="louvain")
        assert result["algorithm"] == "louvain"
        
        # Invalid algorithm - should default
        result = service._validate_inputs(algorithm="invalid_algo")
        assert result["algorithm"] == "louvain"  # Default
        
        # Empty string - should default
        result = service._validate_inputs(algorithm="")
        assert result["algorithm"] == "louvain"
    
    def test_validate_inputs_comprehensive(self, service):
        """Test comprehensive input validation with multiple parameters"""
        inputs = {
            "top_n": 1500,  # Too high
            "damping_factor": 2.0,  # Too high
            "algorithm": "invalid",  # Invalid
            "min_betweenness": 0.05,  # Valid
        }
        
        result = service._validate_inputs(**inputs)
        
        assert result["top_n"] == 1000  # Clamped
        assert result["damping_factor"] == 0.99  # Clamped
        assert result["algorithm"] == "louvain"  # Defaulted
        assert result["min_betweenness"] == 0.05  # Unchanged
    
    def test_cache_operations(self, service):
        """Test cache set/get operations"""
        category = "test"
        key = "test_key"
        value = {"data": "test_value", "timestamp": time.time()}
        
        # Set cache
        service._cache_set(category, key, value)
        
        # Get cache - should return the value
        cached = service._cache_get(category, key)
        assert cached == value
        
        # Get non-existent key - should return None
        cached = service._cache_get(category, "non_existent")
        assert cached is None
        
        # Get from non-existent category - should return None
        cached = service._cache_get("non_existent", key)
        assert cached is None
    
    def test_cache_ttl_expiry(self, service):
        """Test cache TTL expiration"""
        # Set a short TTL for testing
        original_ttl = service.cache_ttl
        service.cache_ttl = 0.1  # 100ms
        
        try:
            category = "test"
            key = "test_key"
            value = {"data": "test_value"}
            
            # Set cache
            service._cache_set(category, key, value)
            
            # Should be available immediately
            cached = service._cache_get(category, key)
            assert cached == value
            
            # Wait for expiry
            time.sleep(0.2)
            
            # Should be expired now
            cached = service._cache_get(category, key)
            assert cached is None
            
        finally:
            # Restore original TTL
            service.cache_ttl = original_ttl
    
    @pytest.mark.asyncio
    async def test_centrality_integration(self, service, mock_neo4j_service):
        """Integration test for centrality analysis with known graph"""
        # Mock the centrality service to return predictable results
        mock_centrality_service = Mock()
        mock_centrality_service.run_complete_analysis = AsyncMock(return_value=Mock(
            most_central=[
                Mock(course_code="CS 2110", course_title="OOP", centrality_score=0.856, rank=1, subject="CS", level=2110),
                Mock(course_code="CS 3110", course_title="FP", centrality_score=0.742, rank=2, subject="CS", level=3110),
            ],
            bridge_courses=[],
            gateway_courses=[],
            analysis_metadata={
                "total_courses": 240,
                "total_prerequisites": 154,
                "analysis_time_seconds": 0.5
            }
        ))
        
        service.centrality_service = mock_centrality_service
        
        result = await service.get_course_centrality(top_n=2)
        
        assert result["success"] is True
        assert len(result["data"]["most_central_courses"]) == 2
        assert result["data"]["most_central_courses"][0]["course_code"] == "CS 2110"
        assert result["data"]["analysis_metadata"]["total_courses"] == 240
        
        # Verify caching was attempted
        mock_centrality_service.run_complete_analysis.assert_called_once()
    
    def test_performance_constants(self, service):
        """Test that performance constants are within reasonable bounds"""
        # Import constants to test
        from gateway.services.graph_algorithms_service import (
            MAX_TOP_N, MIN_DAMPING_FACTOR, MAX_DAMPING_FACTOR, 
            MAX_ALTERNATIVES, MAX_ITERATIONS
        )
        
        # Sanity checks for constants
        assert MAX_TOP_N >= 100  # Should support reasonable result sets
        assert MAX_TOP_N <= 10000  # Should prevent DoS
        
        assert 0 < MIN_DAMPING_FACTOR < MAX_DAMPING_FACTOR < 1  # PageRank valid range
        
        assert 1 <= MAX_ALTERNATIVES <= 50  # Reasonable path alternatives
        
        assert MAX_ITERATIONS >= 50  # Enough for convergence
        assert MAX_ITERATIONS <= 10000  # Prevent infinite loops