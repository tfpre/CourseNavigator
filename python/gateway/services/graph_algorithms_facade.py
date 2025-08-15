# Graph Algorithms Facade - Service Decomposition Implementation
# Implements Friend's facade pattern recommendation to break up God Object

import logging
import time
from typing import Dict, List, Optional, Any, Literal

from .graph_service import GraphService
from .centrality_service import CentralityService
from .community_service import CommunityService
# from .pathfinding_service import PathfindingService  # TODO: Create next

# Import legacy service for gradual migration
from .graph_algorithms_service import GraphAlgorithmsService as LegacyGraphAlgorithmsService

logger = logging.getLogger(__name__)

class GraphAlgorithmsFacade:
    """
    Facade for decomposed graph algorithm services
    
    FACADE PATTERN IMPLEMENTATION (Friend's Recommendation):
    
    Phase 1: Delegation Facade (CURRENT)
    - Maintains exact same public API as original God Object
    - Zero API drift for existing consumers  
    - Delegates to specialized service classes
    - Ready for incremental extraction without breaking imports/tests
    
    Phase 2: Incremental Logic Migration (NEXT)  
    - Move one domain per sprint (centrality → community → pathfinding)
    - Each domain becomes fully independent service
    - Legacy service shrinks until it's eliminated
    
    Phase 3: Full Decomposition (FUTURE)
    - Remove legacy service entirely
    - Each service becomes separately deployable microservice
    - Add performance monitoring boundaries (@performance_service.time_function)
    
    Benefits:
    - Zero breaking changes during migration
    - Testable service boundaries
    - Performance monitoring per domain
    - Independent scaling and deployment
    - Clear separation of concerns
    """
    
    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service
        
        # Initialize specialized services (Phase 1: Delegation)
        self.centrality_service = CentralityService(graph_service)
        self.community_service = CommunityService(graph_service)
        # self.pathfinding_service = PathfindingService(graph_service)  # TODO: Phase 2
        
        # Maintain legacy service for non-migrated functionality (Phase 1)
        self.legacy_service = LegacyGraphAlgorithmsService(graph_service)
        
        logger.info("Initialized Graph Algorithms Facade with service decomposition")
    
    # === CENTRALITY OPERATIONS (MIGRATED TO CentralityService) ===
    
    async def get_course_centrality(
        self, 
        top_n: int = 20,
        damping_factor: float = 0.85,
        min_betweenness: float = 0.01,
        min_in_degree: int = 2
    ) -> Dict[str, Any]:
        """
        MIGRATED: Delegates to CentralityService
        
        Get course centrality analysis including PageRank, bridge, and gateway courses.
        This method maintains the exact same signature as the original God Object.
        """
        logger.info("Delegating centrality analysis to CentralityService")
        
        try:
            # Delegate to specialized centrality service
            result = await self.centrality_service.analyze_centrality(
                top_n=top_n,
                damping_factor=damping_factor,
                min_betweenness=min_betweenness,
                min_in_degree=min_in_degree,
                use_batched=True  # Use optimized batched queries
            )
            
            logger.info(f"CentralityService completed in {result.get('computation_time_ms', 0)}ms")
            return result
            
        except Exception as e:
            logger.exception(f"Centrality facade delegation failed: {e}")
            # Fallback to legacy service (safety net during migration)
            logger.warning("Falling back to legacy centrality service")
            return await self.legacy_service.get_course_centrality(
                top_n=top_n,
                damping_factor=damping_factor,
                min_betweenness=min_betweenness,
                min_in_degree=min_in_degree
            )
    
    # === COMMUNITY OPERATIONS (MIGRATED TO CommunityService) ===
    
    async def get_course_communities(
        self,
        algorithm: Literal["louvain", "greedy_modularity"] = "louvain"
    ) -> Dict[str, Any]:
        """
        MIGRATED: Delegates to CommunityService
        
        Get course community detection analysis.
        This method maintains the exact same signature as the original God Object.
        """
        logger.info(f"Delegating community detection to CommunityService: algorithm={algorithm}")
        
        try:
            # Delegate to specialized community service
            result = await self.community_service.detect_communities(
                algorithm=algorithm,
                max_iterations=100,
                tolerance=1e-6,
                resolution=1.0
            )
            
            logger.info(f"CommunityService completed in {result.get('computation_time_ms', 0)}ms")
            return result
            
        except Exception as e:
            logger.exception(f"Community facade delegation failed: {e}")
            # Fallback to legacy service (safety net during migration)
            logger.warning("Falling back to legacy community service")
            return await self.legacy_service.get_course_communities(algorithm=algorithm)
    
    # === PATHFINDING OPERATIONS (TODO: MIGRATE TO PathfindingService) ===
    
    async def get_course_recommendations(
        self,
        course_code: str,
        num_recommendations: int = 5
    ) -> Dict[str, Any]:
        """
        TODO PHASE 2: Migrate to PathfindingService
        Currently delegates to legacy service
        """
        logger.info(f"Delegating course recommendations to legacy service (TODO: migrate to PathfindingService)")
        return await self.legacy_service.get_course_recommendations(
            course_code=course_code,
            num_recommendations=num_recommendations
        )
    
    async def get_shortest_path(
        self,
        target_course: str,
        completed_courses: List[str] = None
    ) -> Dict[str, Any]:
        """
        TODO PHASE 2: Migrate to PathfindingService
        Currently delegates to legacy service
        """
        logger.info(f"Delegating shortest path to legacy service (TODO: migrate to PathfindingService)")
        return await self.legacy_service.get_shortest_path(
            target_course=target_course,
            completed_courses=completed_courses or []
        )
    
    async def get_alternative_paths(
        self,
        target_course: str,
        completed_courses: List[str] = None,
        num_alternatives: int = 3
    ) -> Dict[str, Any]:
        """
        TODO PHASE 2: Migrate to PathfindingService
        Currently delegates to legacy service
        """
        logger.info(f"Delegating alternative paths to legacy service (TODO: migrate to PathfindingService)")
        return await self.legacy_service.get_alternative_paths(
            target_course=target_course,
            completed_courses=completed_courses or [],
            num_alternatives=num_alternatives
        )
    
    async def optimize_semester_plan(
        self,
        target_courses: List[str],
        completed_courses: List[str] = None,
        semesters_available: int = 8,
        max_credits_per_semester: int = 18
    ) -> Dict[str, Any]:
        """
        TODO PHASE 2: Migrate to PathfindingService
        Currently delegates to legacy service
        """
        logger.info(f"Delegating semester optimization to legacy service (TODO: migrate to PathfindingService)")
        return await self.legacy_service.optimize_semester_plan(
            target_courses=target_courses,
            completed_courses=completed_courses or [],
            semesters_available=semesters_available,
            max_credits_per_semester=max_credits_per_semester
        )
    
    # === SUBGRAPH OPERATIONS (TODO: DECIDE WHICH SERVICE OWNS THIS) ===
    
    async def get_graph_subgraph(
        self,
        max_nodes: int = 50,
        max_edges: int = 100,
        include_centrality: bool = True,
        include_communities: bool = True,
        filter_by_subject: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        TODO PHASE 2: Decide which service owns subgraph operations
        Currently delegates to legacy service
        
        This is a complex operation that combines centrality + community data.
        Options:
        1. Keep in facade (orchestrates multiple services)  
        2. Move to new SubgraphService
        3. Split by concern (centrality service handles centrality part, etc.)
        """
        logger.info(f"Delegating subgraph to legacy service (TODO: decide service ownership)")
        return await self.legacy_service.get_graph_subgraph(
            max_nodes=max_nodes,
            max_edges=max_edges,
            include_centrality=include_centrality,
            include_communities=include_communities,
            filter_by_subject=filter_by_subject
        )
    
    # === CACHE MANAGEMENT (DELEGATES TO ALL SERVICES) ===
    
    def clear_all_caches(self):
        """Clear caches across all services"""
        logger.info("Clearing caches across all decomposed services")
        
        self.centrality_service.clear_cache()
        self.community_service.clear_cache()
        # self.pathfinding_service.clear_cache()  # TODO: Phase 2
        
        # Also clear legacy service cache during transition
        if hasattr(self.legacy_service, '_cache'):
            for category in self.legacy_service._cache:
                self.legacy_service._cache[category].clear()
            logger.info("Cleared legacy service caches")
    
    def get_service_stats(self) -> Dict[str, Any]:
        """Get statistics from all decomposed services"""
        return {
            "facade_info": {
                "decomposition_phase": "Phase 1 - Delegation Facade",
                "migrated_services": ["centrality", "community"],
                "legacy_services": ["pathfinding", "subgraph"],
                "next_migration": "pathfinding_service"
            },
            "centrality_cache": self.centrality_service.get_cache_stats(),
            "community_cache": self.community_service.get_cache_stats(),
            # "pathfinding_cache": self.pathfinding_service.get_cache_stats(),  # TODO: Phase 2
            "performance_note": "Facade adds ~1ms delegation overhead per call"
        }