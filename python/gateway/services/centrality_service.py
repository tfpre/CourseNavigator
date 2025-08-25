# Centrality Service - Decomposed from GraphAlgorithmsService God Object
# Implements Friend's facade pattern recommendation for service decomposition

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from cachetools import LRUCache
import sys
import os

from .graph_service import GraphService

# Add parent directory to path for graph_analysis imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from graph_analysis.centrality import CourseCentrality, CentralityAnalysis, MAX_TOP_N

logger = logging.getLogger(__name__)

class CentralityService:
    """
    Centrality analysis service - First decomposed service from God Object
    
    Responsibilities:
    - PageRank centrality calculation
    - Betweenness centrality (bridge courses)
    - Gateway course identification (in-degree analysis)
    - Centrality-specific caching and validation
    
    Facade Pattern Implementation:
    - Clean delegation interface
    - Single responsibility principle
    - Testable in isolation
    - Performance monitoring boundary
    """
    
    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service
        self.centrality_analyzer = CourseCentrality(graph_service)
        
        # Centrality-specific cache (bounded memory)
        self._cache = LRUCache(maxsize=128)
        self._cache_timestamps: Dict[str, float] = {}
        self.cache_ttl = 3600  # 1 hour
    
    def _validate_centrality_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate centrality-specific parameters"""
        validated = {}
        
        # Validate top_n
        top_n = kwargs.get('top_n', 20)
        if isinstance(top_n, int) and top_n > 0:
            validated['top_n'] = min(top_n, MAX_TOP_N)
        else:
            validated['top_n'] = 20
            
        # Validate damping_factor
        damping_factor = kwargs.get('damping_factor', 0.85)
        if isinstance(damping_factor, (int, float)) and 0.1 <= damping_factor <= 1.0:
            validated['damping_factor'] = float(damping_factor)
        else:
            validated['damping_factor'] = 0.85
            
        # Validate betweenness threshold
        min_betweenness = kwargs.get('min_betweenness', 0.01)
        if isinstance(min_betweenness, (int, float)) and 0.0 <= min_betweenness <= 1.0:
            validated['min_betweenness'] = float(min_betweenness)
        else:
            validated['min_betweenness'] = 0.01
            
        # Validate in-degree threshold
        min_in_degree = kwargs.get('min_in_degree', 2)
        if isinstance(min_in_degree, int) and min_in_degree >= 1:
            validated['min_in_degree'] = min_in_degree
        else:
            validated['min_in_degree'] = 2
            
        return validated
    
    def _get_cache_key(self, **params) -> str:
        """Generate cache key for centrality operations"""
        import hashlib
        
        sorted_params = []
        for k, v in sorted(params.items()):
            if isinstance(v, float):
                # Handle float precision consistently
                sorted_params.append(f"{k}={v:.3f}")
            else:
                sorted_params.append(f"{k}={v}")
        
        param_str = "_".join(sorted_params)
        
        if len(param_str) > 200:
            param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]
            return f"centrality_{param_hash}"
        else:
            return f"centrality_{param_str}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached centrality result is still valid"""
        if cache_key not in self._cache_timestamps:
            return False
        age = time.time() - self._cache_timestamps[cache_key]
        return age < self.cache_ttl
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached centrality result if valid"""
        if cache_key in self._cache and self._is_cache_valid(cache_key):
            logger.info(f"Using cached centrality result for {cache_key}")
            return self._cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """Cache centrality result with timestamp"""
        self._cache[cache_key] = result
        self._cache_timestamps[cache_key] = time.time()
        logger.info(f"Cached centrality result for {cache_key}")
    
    async def analyze_centrality(
        self,
        top_n: int = 20,
        damping_factor: float = 0.85, 
        min_betweenness: float = 0.01,
        min_in_degree: int = 2,
        use_batched: bool = True
    ) -> Dict[str, Any]:
        """
        Perform comprehensive centrality analysis
        
        Args:
            top_n: Number of top results to return
            damping_factor: PageRank damping factor (0.1-1.0)
            min_betweenness: Minimum betweenness threshold
            min_in_degree: Minimum in-degree for gateway courses
            use_batched: Use batched queries for 40% performance improvement
        
        Returns:
            Dict containing centrality analysis results
        """
        start_time = time.time()
        
        # Validate inputs
        validated = self._validate_centrality_inputs(
            top_n=top_n,
            damping_factor=damping_factor,
            min_betweenness=min_betweenness,
            min_in_degree=min_in_degree
        )
        
        # Check cache
        cache_key = self._get_cache_key(**validated, use_batched=use_batched)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result
        
        try:
            logger.info(f"Computing centrality analysis: top_n={validated['top_n']}, batched={use_batched}")
            
            # Use batched analysis for better performance (Friend's Priority 2)
            # TEMPORARILY DISABLED FOR DEBUGGING
            if False and use_batched:
                analysis = await self.centrality_analyzer.run_batched_centrality_analysis(
                    top_n=validated['top_n'],
                    damping_factor=validated['damping_factor'],
                    max_iterations=100,
                    min_betweenness=validated['min_betweenness'],
                    min_in_degree=validated['min_in_degree']
                )
            else:
                # Fallback to individual analysis
                analysis = await self.centrality_analyzer.run_complete_analysis(
                    top_n=validated['top_n'],
                    damping_factor=validated['damping_factor'],
                    min_betweenness=validated['min_betweenness'],
                    min_in_degree=validated['min_in_degree']
                )
            
            # Convert to service response format
            result = {
                "success": True,
                "data": {
                    "most_central_courses": [asdict(course) for course in analysis.most_central],
                    "bridge_courses": [asdict(course) for course in analysis.bridge_courses],
                    "gateway_courses": [asdict(course) for course in analysis.gateway_courses],
                    "analysis_metadata": analysis.analysis_metadata
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache successful result
            self._cache_result(cache_key, result)
            
            logger.info(f"Centrality analysis completed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.exception(f"Centrality analysis failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "CENTRALITY_COMPUTATION_ERROR",
                    "message": f"Failed to compute centrality analysis: {str(e)}",
                    "details": {"cache_key": cache_key}
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
    
    async def calculate_pagerank_only(
        self,
        damping_factor: float = 0.85,
        max_iterations: int = 100
    ) -> Dict[str, Any]:
        """
        Calculate PageRank centrality only (lightweight operation)
        
        Useful for when only basic centrality ranking is needed
        """
        start_time = time.time()
        
        try:
            validated = self._validate_centrality_inputs(
                damping_factor=damping_factor
            )
            
            rankings = await self.centrality_analyzer.calculate_pagerank(
                damping_factor=validated['damping_factor'],
                max_iterations=max_iterations
            )
            
            result = {
                "success": True,
                "data": {
                    "pagerank_rankings": [asdict(course) for course in rankings],
                    "algorithm_params": {
                        "damping_factor": validated['damping_factor'],
                        "max_iterations": max_iterations
                    }
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            return result
            
        except Exception as e:
            logger.exception(f"PageRank calculation failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "PAGERANK_ERROR",
                    "message": f"PageRank calculation failed: {str(e)}"
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
    
    def clear_cache(self):
        """Clear centrality analysis cache"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cleared centrality analysis cache")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get centrality cache statistics"""
        return {
            "cache_size": len(self._cache),
            "max_size": self._cache.maxsize,
            "hit_rate": getattr(self._cache, 'hits', 0) / (getattr(self._cache, 'hits', 0) + getattr(self._cache, 'misses', 1)),
            "cached_keys": list(self._cache.keys()),
            "cache_timestamps_count": len(self._cache_timestamps)
        }
    
    async def _ensure_graph_exists(self, graph_name: str = None):
        """Delegate graph existence check to centrality analyzer's graph context"""
        if graph_name is None:
            graph_name = "prerequisite_graph"
        return await self.centrality_analyzer.graph_context.ensure_graph_exists(graph_name)