"""
Chaos Test: RateMyProfessor Unavailable Fallback

Tests system resilience when RMP scraping fails or is unavailable.
Verifies graceful degradation to enhanced mock data with proper selection_reason.
"""

import asyncio
import pytest
import pytest_asyncio
import aiohttp
from unittest.mock import AsyncMock, patch

try:
    import fakeredis.aioredis as fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False

from gateway.services.professor_intelligence_service import ProfessorIntelligenceService

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def fake_redis():
    """Fixture providing fake Redis client for testing"""
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis.aioredis not installed")
    
    r = fakeredis.FakeRedis(decode_responses=True)
    yield r
    await r.flushall()
    await r.aclose()

@pytest_asyncio.fixture
async def professor_service(fake_redis):
    """Fixture providing ProfessorIntelligenceService with fake Redis"""
    return ProfessorIntelligenceService(redis_client=fake_redis)

class TestRMPChaos:
    """Chaos tests for RateMyProfessor unavailability scenarios"""
    
    async def test_rmp_scraping_timeout_fallback(self, professor_service):
        """Test fallback when RMP scraping times out"""
        
        # Mock the scraping method to raise a timeout
        async def mock_scrape_timeout(*args, **kwargs):
            raise asyncio.TimeoutError("RMP scraping timed out")
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_scrape_timeout):
            result = await professor_service.get_professor_intel("CS 4780")
        
        # Should return enhanced mock data
        assert result is not None
        assert result["course_code"] == "CS 4780"
        
        # Should indicate fallback was used
        assert result["selection_reason"] == "enhanced_mock_deterministic"
        assert result["data_source"] == "enhanced_mock"
        
        # Should contain formatted professor data structure
        assert "professor_name" in result
        assert "overall_rating" in result
        assert "review_count" in result
        assert result["review_count"] > 0  # Enhanced mock has review counts
        assert isinstance(result["overall_rating"], (int, float))
        assert result["overall_rating"] >= 3.0  # Enhanced mock has reasonable ratings
    
    async def test_rmp_network_error_fallback(self, professor_service):
        """Test fallback when RMP has network errors"""
        
        # Mock network failure
        async def mock_network_error(*args, **kwargs):
            raise aiohttp.ClientError("Network unreachable")
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_network_error):
            result = await professor_service.get_professor_intel("CS 2110")
        
        # Should gracefully fall back to mock data
        assert result is not None
        assert result["selection_reason"] == "enhanced_mock_deterministic"
        assert result["data_source"] == "enhanced_mock"
        assert result["course_code"] == "CS 2110"
        
        # Mock data should be deterministic
        assert "professor_name" in result
        assert isinstance(result["overall_rating"], (int, float))
        assert result["overall_rating"] >= 3.0  # Enhanced mock has reasonable ratings
    
    async def test_rmp_http_error_fallback(self, professor_service):
        """Test fallback when RMP returns HTTP errors"""
        
        # Mock HTTP error response
        async def mock_http_error(*args, **kwargs):
            import aiohttp
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=(),
                status=503,
                message="Service Unavailable"
            )
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_http_error):
            result = await professor_service.get_professor_intel("MATH 1920")
        
        # Should handle HTTP errors gracefully
        assert result is not None
        assert result["selection_reason"] == "enhanced_mock_deterministic"
        assert result["data_source"] == "enhanced_mock"
        
        # Should cache the fallback result
        cached_result = await professor_service.get_professor_intel("MATH 1920")
        assert cached_result["selection_reason"] == "enhanced_mock_deterministic"
    
    async def test_rmp_malformed_response_fallback(self, professor_service):
        """Test fallback when RMP returns malformed data"""
        
        # Mock malformed HTML response
        async def mock_malformed_response(*args, **kwargs):
            return {
                "html": "<html><body>Not the expected RMP structure</body></html>",
                "status": 200
            }
        
        with patch.object(professor_service, '_scrape_professor_data', return_value=mock_malformed_response()):
            with patch.object(professor_service, '_parse_professor_search_results', return_value=[]):
                result = await professor_service.get_professor_intel("ECE 3140")
        
        # Should fall back when parsing returns empty results
        assert result is not None
        assert result["selection_reason"] == "enhanced_mock_deterministic"
    
    async def test_redis_unavailable_during_fallback(self, professor_service):
        """Test system behavior when both RMP and Redis are unavailable"""
        
        # Mock RMP failure
        async def mock_rmp_failure(*args, **kwargs):
            raise Exception("RMP completely unavailable")
        
        # Mock Redis failure 
        async def mock_redis_failure(*args, **kwargs):
            raise Exception("Redis connection failed")
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_rmp_failure):
            with patch.object(professor_service, '_cache_professor_data', side_effect=mock_redis_failure):
                # Should still return data even if caching fails
                result = await professor_service.get_professor_intel("CS 3110")
        
        assert result is not None
        assert result["selection_reason"] == "enhanced_mock_deterministic"
        
        # Should work without caching (cache writes are non-fatal)
        assert "all_professors" in result
    
    async def test_selection_reason_consistency(self, professor_service):
        """Test that selection_reason is consistent across fallback scenarios"""
        
        courses = ["CS 4780", "CS 2110", "ECE 3140", "MATH 1920"]
        
        # Mock all RMP calls to fail
        async def mock_rmp_always_fails(*args, **kwargs):
            raise Exception("RMP service unavailable")
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_rmp_always_fails):
            results = []
            for course in courses:
                result = await professor_service.get_professor_intel(course)
                results.append(result)
        
        # All should have consistent fallback selection reason
        for result in results:
            assert result is not None
            assert result["selection_reason"] == "enhanced_mock_deterministic"
            assert result["data_source"] == "enhanced_mock"
            assert "professor_name" in result
    
    async def test_fallback_quality_vs_empty_response(self, professor_service):
        """Test that fallback provides better data than empty responses"""
        
        # Mock RMP to return empty data
        async def mock_empty_response(*args, **kwargs):
            return {"professors": [], "course_code": "CS 4780"}
        
        with patch.object(professor_service, '_scrape_professor_data', return_value=mock_empty_response()):
            with patch.object(professor_service, '_parse_professor_search_results', return_value=[]):
                result = await professor_service.get_professor_intel("CS 4780")
        
        # Enhanced mock should provide meaningful data
        assert result is not None
        assert len(result["all_professors"]) > 0
        
        # Should have realistic rating distributions
        ratings = [p["overall_rating"] for p in result["all_professors"]]
        assert all(3.0 <= rating <= 5.0 for rating in ratings)
        
        # Should have reasonable review counts
        review_counts = [p["review_count"] for p in result["all_professors"]]
        assert all(count > 0 for count in review_counts)
    
    async def test_chaos_concurrent_failures(self, professor_service):
        """Test system under concurrent RMP failures"""
        
        async def mock_random_failure(*args, **kwargs):
            import random
            failure_types = [
                asyncio.TimeoutError("Timeout"),
                Exception("Network error"),
                ValueError("Parse error")
            ]
            raise random.choice(failure_types)
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_random_failure):
            # Fire multiple concurrent requests
            courses = ["CS 4780", "CS 2110", "CS 3110", "ECE 3140", "MATH 1920"]
            tasks = [professor_service.get_professor_intel(course) for course in courses]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed with fallback data
        for result in results:
            assert not isinstance(result, Exception), f"Unexpected exception: {result}"
            assert result is not None
            assert result["selection_reason"] == "enhanced_mock_deterministic"
    
    async def test_cache_isolation_during_chaos(self, professor_service):
        """Test that cache corruption doesn't spread during failures"""
        
        # First, get successful cached data
        with patch.object(professor_service, '_scrape_professor_data') as mock_scrape:
            mock_scrape.return_value = {
                "professors": [{"name": "Prof Test", "overall_rating": 4.5, "review_count": 100}],
                "course_code": "CS 1110"
            }
            
            good_result = await professor_service.get_professor_intel("CS 1110")
            assert good_result["selection_reason"] == "most_reviews_then_rating"
        
        # Then cause chaos for different course
        async def mock_chaos_failure(*args, **kwargs):
            raise Exception("Chaos failure")
        
        with patch.object(professor_service, '_scrape_professor_data', side_effect=mock_chaos_failure):
            chaos_result = await professor_service.get_professor_intel("CS 9999")
            assert chaos_result["selection_reason"] == "enhanced_mock_deterministic"
        
        # Original cached data should remain intact
        cached_good = await professor_service.get_professor_intel("CS 1110")
        assert cached_good["selection_reason"] == "most_reviews_then_rating"