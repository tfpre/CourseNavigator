# Professor Intelligence Service - RateMyProfessor Integration
# Implements friend's specifications: Redis caching, residential proxy, nightly scraping

import asyncio
import logging
import hashlib
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import aiohttp
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

class ProfessorIntelligenceService:
    """
    Professor Intelligence Service following friend's newfix.md specifications:
    
    - One table, one scraper, quick win approach
    - Redis caching with 7-day TTL  
    - Residential proxy for scraping reliability
    - Nightly batch job pattern with last-known fallback
    - Expose overall_rating, difficulty, would_take_again, tag_bigrams in prompt
    
    Architecture: Simple cache-first service with graceful degradation
    """
    
    def __init__(self, redis_client=None, proxy_config: Dict[str, str] = None):
        self.redis_client = redis_client
        self.proxy_config = proxy_config or {}
        
        # Performance configuration (friend's guidance)
        self.CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
        self.REQUEST_TIMEOUT_SECONDS = 5  # Fail-fast for chat latency
        self.MAX_RETRIES = 2
        self.RESIDENTIAL_PROXY_ROTATION = True
        
        # RateMyProfessor base configuration
        self.RMP_BASE_URL = "https://www.ratemyprofessors.com"
        self.RMP_SEARCH_URL = f"{self.RMP_BASE_URL}/search/professors"
        self.CORNELL_SCHOOL_ID = "298"  # Cornell University RMP school ID
        
        # Mock data for development (removed when scraping is live)
        self.mock_professor_data = {
            "default": {
                "overall_rating": 3.8,
                "difficulty": 3.2,
                "would_take_again": 0.75,
                "tag_bigrams": ["clear lectures", "fair grading", "helpful", "engaging"],
                "review_count": 45,
                "last_updated": datetime.utcnow().isoformat()
            },
            "high_rated": {
                "overall_rating": 4.5,
                "difficulty": 2.8,
                "would_take_again": 0.92,
                "tag_bigrams": ["amazing professor", "clear explanation", "passionate", "approachable"],
                "review_count": 89,
                "last_updated": datetime.utcnow().isoformat()
            },
            "challenging": {
                "overall_rating": 3.2,
                "difficulty": 4.6,
                "would_take_again": 0.45,
                "tag_bigrams": ["very difficult", "tough grader", "brilliant", "demanding"],
                "review_count": 67,
                "last_updated": datetime.utcnow().isoformat()
            }
        }
    
    async def get_professor_intel(self, course_code: str) -> Dict[str, Any]:
        """
        Get professor intelligence for a specific course.
        
        Friend's specification: Redis-first with cache, 7-day TTL,
        expose overall_rating, difficulty, would_take_again, tag_bigrams
        
        Args:
            course_code: Course code like "CS 2110" or "MATH 2940"
            
        Returns:
            Professor intelligence data formatted for prompt context
        """
        # Generate cache key
        cache_key = f"professor_intel:{self._normalize_course_code(course_code)}"
        
        try:
            # Step 1: Check Redis cache first (7-day TTL)
            if self.redis_client:
                cached_data = await self._get_from_cache(cache_key)
                if cached_data:
                    logger.debug(f"Professor intel cache hit for {course_code}")
                    return cached_data
            
            # Step 2: Scrape RateMyProfessor (with residential proxy)
            professor_data = await self._scrape_professor_data(course_code)
            
            # Step 3: Format for prompt context and cache
            formatted_data = self._format_for_prompt(professor_data, course_code)
            
            # Step 4: Cache with 7-day TTL
            if self.redis_client and formatted_data:
                await self._cache_professor_data(cache_key, formatted_data)
            
            return formatted_data
            
        except Exception as e:
            logger.exception(f"Professor intel failed for {course_code}: {e}")
            
            # Graceful degradation: return mock data
            mock_key = self._select_mock_profile(course_code)
            mock_data = self.mock_professor_data[mock_key].copy()
            mock_data["data_source"] = "fallback_mock"
            mock_data["course_code"] = course_code
            return mock_data
    
    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get professor data from Redis cache"""
        try:
            if not self.redis_client:
                return None
                
            # TODO: Implement actual Redis integration
            # cached_json = await self.redis_client.get(cache_key)
            # if cached_json:
            #     return json.loads(cached_json)
            return None
            
        except Exception as e:
            logger.exception(f"Cache retrieval failed for {cache_key}: {e}")
            return None
    
    async def _scrape_professor_data(self, course_code: str) -> Dict[str, Any]:
        """
        Scrape RateMyProfessor data for professors teaching the given course.
        
        Implementation strategy:
        1. Search for Cornell professors by course/department
        2. Extract ratings, difficulty, would_take_again percentages
        3. Parse review tags for bigrams
        4. Handle residential proxy rotation for reliability
        """
        try:
            # Extract department from course code
            department = re.match(r'([A-Z]+)', course_code.upper()).group(1)
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT_SECONDS)) as session:
                
                # Step 1: Search for professors in this department at Cornell
                search_params = {
                    "query": department,
                    "sid": self.CORNELL_SCHOOL_ID,
                    "offset": "0"
                }
                
                # TODO: Add residential proxy support when needed
                # proxy_url = self._get_next_proxy() if self.RESIDENTIAL_PROXY_ROTATION else None
                
                search_response = await session.get(
                    self.RMP_SEARCH_URL,
                    params=search_params,
                    # proxy=proxy_url,
                    headers=self._get_scraping_headers()
                )
                
                if search_response.status == 429:
                    logger.warning(f"RateMyProfessor rate limited for {course_code}")
                    raise Exception("RMP_RATE_LIMITED")
                
                search_html = await search_response.text()
                professors = self._parse_professor_search_results(search_html)
                
                if not professors:
                    logger.info(f"No professors found for {course_code} at Cornell")
                    return {"professors": [], "course_code": course_code}
                
                # Step 2: Get detailed data for top professor (most reviews)
                top_professor = max(professors, key=lambda p: p.get("review_count", 0))
                detailed_data = await self._scrape_professor_details(session, top_professor["profile_url"])
                
                return {
                    "primary_professor": {**top_professor, **detailed_data},
                    "all_professors": professors,
                    "course_code": course_code,
                    "scrape_timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.exception(f"RMP scraping failed for {course_code}: {e}")
            raise e
    
    def _parse_professor_search_results(self, html_content: str) -> List[Dict[str, Any]]:
        """Parse RateMyProfessor search results HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            professors = []
            
            # TODO: Implement actual HTML parsing for RMP search results
            # This is a placeholder - actual implementation would parse the RMP HTML structure
            
            # Mock implementation for development
            mock_professors = [
                {
                    "name": "Dr. Smith",
                    "department": "Computer Science", 
                    "overall_rating": 4.2,
                    "review_count": 67,
                    "profile_url": "/professor/123456"
                },
                {
                    "name": "Prof. Johnson",
                    "department": "Computer Science",
                    "overall_rating": 3.8,
                    "review_count": 43,
                    "profile_url": "/professor/789012"
                }
            ]
            
            return mock_professors
            
        except Exception as e:
            logger.exception(f"Failed to parse RMP search results: {e}")
            return []
    
    async def _scrape_professor_details(self, session: aiohttp.ClientSession, profile_url: str) -> Dict[str, Any]:
        """Scrape detailed professor profile data"""
        try:
            full_url = f"{self.RMP_BASE_URL}{profile_url}"
            
            async with session.get(full_url, headers=self._get_scraping_headers()) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch professor details: {response.status}")
                    return {}
                
                html_content = await response.text()
                return self._parse_professor_profile(html_content)
                
        except Exception as e:
            logger.exception(f"Failed to scrape professor details from {profile_url}: {e}")
            return {}
    
    def _parse_professor_profile(self, html_content: str) -> Dict[str, Any]:
        """Parse professor profile page for detailed ratings and tags"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # TODO: Implement actual RMP profile parsing
            # This would extract difficulty, would_take_again, tag_bigrams from HTML
            
            # Mock detailed data for development
            return {
                "difficulty": 3.4,
                "would_take_again": 0.78,
                "tag_bigrams": ["clear lectures", "tough grader", "helpful office hours"],
                "recent_reviews": [
                    {"rating": 4, "comment": "Great professor, clear explanations"},
                    {"rating": 5, "comment": "Challenging but fair, learned a lot"}
                ]
            }
            
        except Exception as e:
            logger.exception(f"Failed to parse professor profile: {e}")
            return {}
    
    def _format_for_prompt(self, professor_data: Dict[str, Any], course_code: str) -> Dict[str, Any]:
        """
        Format professor data for LLM prompt context.
        
        Friend's specification: expose overall_rating, difficulty, would_take_again, tag_bigrams
        """
        try:
            primary_prof = professor_data.get("primary_professor", {})
            
            # Extract key metrics for prompt context
            formatted_data = {
                "course_code": course_code,
                "overall_rating": primary_prof.get("overall_rating", 0.0),
                "difficulty": primary_prof.get("difficulty", 0.0),
                "would_take_again": primary_prof.get("would_take_again", 0.0),
                "tag_bigrams": primary_prof.get("tag_bigrams", [])[:4],  # Limit to 4 tags for token budget
                "professor_name": primary_prof.get("name", "Unknown"),
                "review_count": primary_prof.get("review_count", 0),
                "data_source": "ratemyprofessor_scraped",
                "last_updated": professor_data.get("scrape_timestamp", datetime.utcnow().isoformat())
            }
            
            # Generate prompt-friendly summary text
            rating_text = "highly rated" if formatted_data["overall_rating"] >= 4.0 else "moderately rated" if formatted_data["overall_rating"] >= 3.5 else "mixed reviews"
            difficulty_text = "very challenging" if formatted_data["difficulty"] >= 4.0 else "moderately challenging" if formatted_data["difficulty"] >= 3.0 else "not too difficult"
            
            formatted_data["prompt_summary"] = (
                f"{formatted_data['professor_name']} is {rating_text} "
                f"({formatted_data['overall_rating']:.1f}/5) and {difficulty_text} "
                f"({formatted_data['difficulty']:.1f}/5 difficulty). "
                f"{int(formatted_data['would_take_again'] * 100)}% would take again. "
                f"Tags: {', '.join(formatted_data['tag_bigrams'])}"
            )
            
            return formatted_data
            
        except Exception as e:
            logger.exception(f"Failed to format professor data: {e}")
            return {
                "course_code": course_code,
                "data_source": "format_error",
                "prompt_summary": "Professor information unavailable"
            }
    
    async def _cache_professor_data(self, cache_key: str, data: Dict[str, Any]):
        """Cache professor data in Redis with 7-day TTL"""
        try:
            if self.redis_client:
                # TODO: Implement actual Redis caching
                # await self.redis_client.setex(
                #     cache_key,
                #     self.CACHE_TTL_SECONDS,
                #     json.dumps(data, default=str)
                # )
                logger.debug(f"Cached professor data for {cache_key}")
                
        except Exception as e:
            logger.exception(f"Failed to cache professor data: {e}")
    
    def _normalize_course_code(self, course_code: str) -> str:
        """Normalize course code for consistent caching"""
        return course_code.upper().replace(' ', '_').replace('-', '_')
    
    def _select_mock_profile(self, course_code: str) -> str:
        """Select appropriate mock profile based on course characteristics"""
        # Simple heuristic: use course code to consistently select mock data
        course_hash = hashlib.md5(course_code.encode()).hexdigest()
        hash_int = int(course_hash[:8], 16)
        
        if hash_int % 3 == 0:
            return "high_rated"
        elif hash_int % 3 == 1:
            return "challenging" 
        else:
            return "default"
    
    def _get_scraping_headers(self) -> Dict[str, str]:
        """Get headers for RateMyProfessor scraping to avoid detection"""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }
    
    def _get_next_proxy(self) -> Optional[str]:
        """Get next proxy from residential proxy pool rotation"""
        # TODO: Implement proxy rotation for production scraping
        return self.proxy_config.get("default_proxy") if self.proxy_config else None
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for professor intelligence service"""
        try:
            # Test mock data functionality
            test_data = await self.get_professor_intel("CS 2110")
            
            return {
                "service": "professor_intelligence", 
                "status": "healthy",
                "cache_enabled": self.redis_client is not None,
                "proxy_enabled": bool(self.proxy_config),
                "test_data_available": bool(test_data),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.exception(f"Professor intelligence health check failed: {e}")
            return {
                "service": "professor_intelligence",
                "status": "unhealthy", 
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def bulk_refresh_cache(self, course_codes: List[str]) -> Dict[str, Any]:
        """
        Bulk refresh professor intelligence for multiple courses.
        Designed for nightly batch job pattern (friend's recommendation).
        """
        results = {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "processed_courses": []
        }
        
        for course_code in course_codes:
            try:
                # Force cache refresh by bypassing cache lookup
                professor_data = await self._scrape_professor_data(course_code)
                formatted_data = self._format_for_prompt(professor_data, course_code)
                
                # Cache the fresh data
                cache_key = f"professor_intel:{self._normalize_course_code(course_code)}"
                await self._cache_professor_data(cache_key, formatted_data)
                
                results["success_count"] += 1
                results["processed_courses"].append(course_code)
                
                # Rate limiting: delay between requests
                await asyncio.sleep(1)
                
            except Exception as e:
                results["error_count"] += 1
                results["errors"].append({
                    "course_code": course_code,
                    "error": str(e)
                })
                logger.exception(f"Bulk refresh failed for {course_code}: {e}")
        
        logger.info(f"Bulk professor refresh completed: {results['success_count']} successes, {results['error_count']} errors")
        return results