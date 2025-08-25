# Community Service - Decomposed from GraphAlgorithmsService God Object
# Implements Friend's facade pattern recommendation for service decomposition

import logging
import time
from typing import Dict, List, Optional, Any, Literal
from dataclasses import asdict
from cachetools import LRUCache

from gateway.services.graph_service import GraphService
from graph_analysis.communities import CourseCommunities, CommunityAnalysis

logger = logging.getLogger(__name__)

class CommunityService:
    """
    Community detection service - Second decomposed service from God Object
    
    Responsibilities:
    - Louvain community detection
    - Greedy modularity optimization
    - Community structure analysis and validation
    - Department overlap analysis
    - Community-specific caching and validation
    
    Facade Pattern Implementation:
    - Focused on community detection algorithms only
    - Clean separation from centrality concerns
    - Independent caching strategy optimized for community results
    - Testable in isolation with mock graph data
    """
    
    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service
        self.community_analyzer = CourseCommunities(graph_service)
        
        # Community-specific cache (smaller than centrality - communities change less)
        self._cache = LRUCache(maxsize=64)
        self._cache_timestamps: Dict[str, float] = {}
        self.cache_ttl = 7200  # 2 hours (communities are more stable)
    
    def _validate_community_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate community detection parameters"""
        validated = {}
        
        # Validate algorithm choice
        algorithm = kwargs.get('algorithm', 'louvain')
        if algorithm in ['louvain', 'greedy_modularity']:
            validated['algorithm'] = algorithm
        else:
            validated['algorithm'] = 'louvain'  # Default to Louvain
            
        # Validate max iterations for Louvain
        max_iterations = kwargs.get('max_iterations', 100)
        if isinstance(max_iterations, int) and 10 <= max_iterations <= 1000:
            validated['max_iterations'] = max_iterations
        else:
            validated['max_iterations'] = 100
            
        # Validate tolerance for convergence
        tolerance = kwargs.get('tolerance', 1e-6)
        if isinstance(tolerance, (int, float)) and 1e-10 <= tolerance <= 1e-3:
            validated['tolerance'] = float(tolerance)
        else:
            validated['tolerance'] = 1e-6
            
        # Validate resolution parameter (for Louvain)
        resolution = kwargs.get('resolution', 1.0)
        if isinstance(resolution, (int, float)) and 0.1 <= resolution <= 5.0:
            validated['resolution'] = float(resolution)
        else:
            validated['resolution'] = 1.0
            
        return validated
    
    def _get_cache_key(self, **params) -> str:
        """Generate cache key for community detection operations"""
        import hashlib
        
        sorted_params = []
        for k, v in sorted(params.items()):
            if isinstance(v, float):
                if k == 'tolerance':
                    # Scientific notation for tolerance
                    sorted_params.append(f"{k}={v:.0e}")
                else:
                    sorted_params.append(f"{k}={v:.3f}")
            else:
                sorted_params.append(f"{k}={v}")
        
        param_str = "_".join(sorted_params)
        
        if len(param_str) > 200:
            param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]
            return f"community_{param_hash}"
        else:
            return f"community_{param_str}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached community result is still valid"""
        if cache_key not in self._cache_timestamps:
            return False
        age = time.time() - self._cache_timestamps[cache_key]
        return age < self.cache_ttl
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached community result if valid"""
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            logger.info(f"Using cached community result for {cache_key}")
            return self._cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """Cache community result with timestamp"""
        self._cache[cache_key] = result
        self._cache_timestamps[cache_key] = time.time()
        logger.info(f"Cached community result for {cache_key}")
    
    async def detect_communities(
        self,
        algorithm: Literal["louvain", "greedy_modularity"] = "louvain",
        max_iterations: int = 100,
        tolerance: float = 1e-6,
        resolution: float = 1.0
    ) -> Dict[str, Any]:
        """
        Perform community detection analysis
        
        Args:
            algorithm: Community detection algorithm ("louvain" or "greedy_modularity")
            max_iterations: Maximum iterations for convergence
            tolerance: Convergence tolerance for Louvain
            resolution: Resolution parameter for community granularity
            
        Returns:
            Dict containing community detection results
        """
        start_time = time.time()
        
        # Validate inputs
        validated = self._validate_community_inputs(
            algorithm=algorithm,
            max_iterations=max_iterations,
            tolerance=tolerance,
            resolution=resolution
        )
        
        # Check cache
        cache_key = self._get_cache_key(**validated)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result
        
        try:
            logger.info(f"Computing community detection: algorithm={validated['algorithm']}")
            
            # Run community detection
            analysis = await self.community_analyzer.run_complete_analysis(
                algorithm=validated['algorithm']
            )
            
            # Convert to service response format
            result = {
                "success": True,
                "data": {
                    "communities": analysis.communities,
                    "community_assignments": analysis.community_assignments,
                    "modularity_score": analysis.modularity_score,
                    "num_communities": analysis.num_communities,
                    "algorithm_metadata": analysis.algorithm_metadata,
                    "department_overlap": analysis.department_overlap if hasattr(analysis, 'department_overlap') else {}
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache successful result
            self._cache_result(cache_key, result)
            
            logger.info(f"Community detection completed in {result['computation_time_ms']}ms, found {analysis.num_communities} communities")
            return result
            
        except Exception as e:
            logger.exception(f"Community detection failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "COMMUNITY_DETECTION_ERROR",
                    "message": f"Failed to detect communities: {str(e)}",
                    "details": {"cache_key": cache_key, "algorithm": validated['algorithm']}
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
    
    async def analyze_department_overlap(self) -> Dict[str, Any]:
        """
        Analyze how academic departments cluster into communities
        
        Useful for understanding curriculum structure and interdisciplinary relationships
        """
        start_time = time.time()
        
        try:
            # First detect communities
            community_result = await self.detect_communities()
            
            if not community_result['success']:
                return community_result
            
            communities = community_result['data']['communities']
            
            # Analyze department distribution within communities
            department_analysis = {}
            
            for community_id, courses in communities.items():
                dept_counts = {}
                for course in courses:
                    subject = course.get('subject', 'UNKNOWN')
                    dept_counts[subject] = dept_counts.get(subject, 0) + 1
                
                # Calculate department diversity metrics
                total_courses = len(courses)
                dept_diversity = len(dept_counts)  # Number of different departments
                
                # Calculate dominant department percentage
                max_dept_count = max(dept_counts.values()) if dept_counts else 0
                dominant_dept_pct = (max_dept_count / total_courses) * 100 if total_courses > 0 else 0
                
                department_analysis[community_id] = {
                    "department_counts": dept_counts,
                    "total_courses": total_courses,
                    "department_diversity": dept_diversity,
                    "dominant_department_pct": round(dominant_dept_pct, 1),
                    "is_interdisciplinary": dept_diversity > 2 and dominant_dept_pct < 70
                }
            
            result = {
                "success": True,
                "data": {
                    "department_analysis": department_analysis,
                    "summary": {
                        "total_communities": len(department_analysis),
                        "interdisciplinary_communities": sum(1 for analysis in department_analysis.values() if analysis["is_interdisciplinary"]),
                        "single_dept_communities": sum(1 for analysis in department_analysis.values() if analysis["department_diversity"] == 1)
                    }
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            return result
            
        except Exception as e:
            logger.exception(f"Department overlap analysis failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "DEPT_OVERLAP_ERROR", 
                    "message": f"Failed to analyze department overlap: {str(e)}"
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
    
    async def get_community_for_course(self, course_code: str) -> Dict[str, Any]:
        """
        Get community assignment for a specific course
        
        Args:
            course_code: Course code (e.g., "CS 2110")
            
        Returns:
            Community information for the course
        """
        start_time = time.time()
        
        try:
            # Get latest community detection
            community_result = await self.detect_communities()
            
            if not community_result['success']:
                return community_result
            
            communities = community_result['data']['communities']
            
            # Find course in communities
            for community_id, courses in communities.items():
                for course in courses:
                    if course.get('course_code') == course_code:
                        # Get community peers
                        peer_courses = [c for c in courses if c.get('course_code') != course_code]
                        
                        result = {
                            "success": True,
                            "data": {
                                "course_code": course_code,
                                "community_id": community_id,
                                "community_size": len(courses),
                                "peer_courses": peer_courses[:10],  # Limit to top 10 peers
                                "total_peers": len(peer_courses)
                            },
                            "computation_time_ms": int((time.time() - start_time) * 1000)
                        }
                        
                        return result
            
            # Course not found
            return {
                "success": False,
                "error": {
                    "code": "COURSE_NOT_FOUND",
                    "message": f"Course {course_code} not found in community analysis"
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.exception(f"Community lookup failed for {course_code}: {e}")
            return {
                "success": False,
                "error": {
                    "code": "COMMUNITY_LOOKUP_ERROR",
                    "message": f"Failed to find community for course: {str(e)}"
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
    
    def clear_cache(self):
        """Clear community detection cache"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cleared community detection cache")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get community cache statistics"""
        return {
            "cache_size": len(self._cache),
            "max_size": self._cache.maxsize,
            "hit_rate": getattr(self._cache, 'hits', 0) / (getattr(self._cache, 'hits', 0) + getattr(self._cache, 'misses', 1)),
            "cached_keys": list(self._cache.keys()),
            "cache_timestamps_count": len(self._cache_timestamps),
            "cache_ttl_hours": self.cache_ttl / 3600
        }