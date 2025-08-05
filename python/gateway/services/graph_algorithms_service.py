"""
Graph Algorithms Service for Cornell Course Navigator
Provides centrality analysis, community detection, and pathfinding algorithms
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from cachetools import LRUCache

from gateway.services.graph_service import GraphService
from graph_analysis.centrality import CourseCentrality, CentralityAnalysis, MAX_TOP_N
from graph_analysis.communities import CourseCommunities, CommunityAnalysis
from graph_analysis.pathfinding import PrerequisitePaths, PrerequisitePath, OptimizedSchedule, MAX_ALTERNATIVES, MAX_TARGET_COURSES

logger = logging.getLogger(__name__)

# Service-level validation constants
MAX_SERVICE_TOP_N = 500  # Service layer limit (lower than algorithm limit)
MAX_SERVICE_ALTERNATIVES = 5  # Service layer limit for k-shortest paths


class GraphAlgorithmsService:
    """Service for running advanced graph algorithms on course data"""
    
    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service
        self.centrality_analyzer = CourseCentrality(graph_service)
        self.community_analyzer = CourseCommunities(graph_service)
        self.path_analyzer = PrerequisitePaths(graph_service)
        
        # LRU cache for expensive computations (V2 Architecture - bounded memory)
        # Prevents memory leaks while maintaining performance for popular queries
        self._cache: Dict[str, LRUCache] = {
            "centrality": LRUCache(maxsize=128),
            "communities": LRUCache(maxsize=64), 
            "paths": LRUCache(maxsize=256),
            "subgraph": LRUCache(maxsize=32)
        }
        self._cache_timestamps: Dict[str, float] = {}
        self.cache_ttl = 3600  # 1 hour cache TTL
    
    def _validate_service_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate inputs at service layer to prevent resource exhaustion"""
        validated = {}
        
        # Validate top_n at service level
        if 'top_n' in kwargs:
            top_n = kwargs['top_n']
            if isinstance(top_n, int) and top_n > 0:
                validated['top_n'] = min(top_n, MAX_SERVICE_TOP_N)
            else:
                validated['top_n'] = 20  # Default
        
        # Validate num_alternatives
        if 'num_alternatives' in kwargs:
            num_alternatives = kwargs['num_alternatives']
            if isinstance(num_alternatives, int) and num_alternatives > 0:
                validated['num_alternatives'] = min(num_alternatives, MAX_SERVICE_ALTERNATIVES)
            else:
                validated['num_alternatives'] = 3  # Default
        
        # Validate course lists
        for list_param in ['target_courses', 'completed_courses']:
            if list_param in kwargs:
                course_list = kwargs[list_param]
                if isinstance(course_list, list):
                    # Remove duplicates and limit size
                    unique_courses = list(set(course_list))
                    if list_param == 'target_courses':
                        validated[list_param] = unique_courses[:MAX_TARGET_COURSES]
                    else:
                        validated[list_param] = unique_courses[:1000]
                else:
                    validated[list_param] = []
        
        # Pass through other parameters unchanged
        for key, value in kwargs.items():
            if key not in validated:
                validated[key] = value
                
        return validated
        
    def _get_cache_key(self, operation: str, **params) -> str:
        """Generate stable cache key for operation with parameters"""
        import hashlib
        
        # Sort parameters and handle lists properly
        sorted_params = []
        for k, v in sorted(params.items()):
            if isinstance(v, list):
                # Sort lists to ensure consistent ordering
                v = sorted(v) if v else []
                v_str = ",".join(str(item) for item in v)
            else:
                v_str = str(v)
            sorted_params.append(f"{k}={v_str}")
        
        param_str = "_".join(sorted_params)
        
        # Use hash for very long parameter strings to prevent key length issues
        if len(param_str) > 200:
            param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:16]
            return f"{operation}_{param_hash}"
        else:
            return f"{operation}_{param_str}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid"""
        if cache_key not in self._cache_timestamps:
            return False
        age = time.time() - self._cache_timestamps[cache_key]
        return age < self.cache_ttl
    
    def _get_cached_result(self, category: str, cache_key: str) -> Optional[Any]:
        """Get cached result if valid"""
        if cache_key in self._cache[category] and self._is_cache_valid(cache_key):
            logger.info(f"Using cached result for {cache_key}")
            return self._cache[category][cache_key]
        return None
    
    def _cache_result(self, category: str, cache_key: str, result: Any):
        """Cache result with timestamp"""
        self._cache[category][cache_key] = result
        self._cache_timestamps[cache_key] = time.time()
        logger.info(f"Cached result for {cache_key}")
    
    async def get_course_centrality(
        self, 
        top_n: int = 20,
        damping_factor: float = 0.85,
        min_betweenness: float = 0.01,
        min_in_degree: int = 2
    ) -> Dict[str, Any]:
        """
        Get course centrality analysis including PageRank, bridge, and gateway courses
        """
        cache_key = self._get_cache_key(
            "centrality",
            top_n=top_n,
            damping_factor=damping_factor,
            min_betweenness=min_betweenness,
            min_in_degree=min_in_degree
        )
        
        # Check cache first
        cached_result = self._get_cached_result("centrality", cache_key)
        if cached_result:
            return cached_result
        
        logger.info("Computing course centrality analysis")
        start_time = time.time()
        
        try:
            # Run complete centrality analysis
            analysis = await self.centrality_analyzer.run_complete_analysis(
                top_n=top_n,
                damping_factor=damping_factor,
                min_betweenness=min_betweenness,
                min_in_degree=min_in_degree
            )
            
            # Convert to serializable format
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
            
            # Cache the result
            self._cache_result("centrality", cache_key, result)
            
            logger.info(f"Centrality analysis completed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.error(f"Centrality analysis failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "CENTRALITY_ANALYSIS_ERROR",
                    "message": "Failed to compute course centrality",
                    "details": {"error": str(e)}
                }
            }
    
    async def get_course_communities(
        self, 
        algorithm: str = 'louvain'
    ) -> Dict[str, Any]:
        """
        Get course community detection analysis
        """
        cache_key = self._get_cache_key("communities", algorithm=algorithm)
        
        # Check cache first
        cached_result = self._get_cached_result("communities", cache_key)
        if cached_result:
            return cached_result
        
        logger.info(f"Computing community analysis using {algorithm}")
        start_time = time.time()
        
        try:
            # Run complete community analysis
            analysis = await self.community_analyzer.run_complete_analysis(algorithm)
            
            # Convert to serializable format
            result = {
                "success": True,
                "data": {
                    "clusters": [asdict(cluster) for cluster in analysis.clusters],
                    "department_overlaps": [asdict(overlap) for overlap in analysis.department_overlaps],
                    "modularity_score": analysis.modularity_score,
                    "analysis_metadata": analysis.analysis_metadata
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache the result
            self._cache_result("communities", cache_key, result)
            
            logger.info(f"Community analysis completed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.error(f"Community analysis failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "COMMUNITY_ANALYSIS_ERROR",
                    "message": "Failed to compute course communities",
                    "details": {"error": str(e)}
                }
            }
    
    async def get_course_recommendations(
        self, 
        course_code: str, 
        num_recommendations: int = 5
    ) -> Dict[str, Any]:
        """
        Get course recommendations based on community membership
        """
        cache_key = self._get_cache_key(
            "recommendations", 
            course_code=course_code, 
            num_recommendations=num_recommendations
        )
        
        # Check cache first (shorter TTL for recommendations)
        if cache_key in self._cache["communities"] and self._is_cache_valid(cache_key):
            cached_result = self._cache["communities"][cache_key]
            logger.info(f"Using cached recommendations for {course_code}")
            return cached_result
        
        logger.info(f"Computing recommendations for course: {course_code}")
        start_time = time.time()
        
        try:
            # Get recommendations
            recommendations = await self.community_analyzer.get_course_recommendations(
                course_code, num_recommendations
            )
            
            # Convert to serializable format
            result = {
                "success": True,
                "data": {
                    "target_course": course_code,
                    "recommendations": [asdict(rec) for rec in recommendations],
                    "num_found": len(recommendations)
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache with shorter TTL
            self._cache["communities"][cache_key] = result
            self._cache_timestamps[cache_key] = time.time()
            
            logger.info(f"Recommendations computed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.error(f"Course recommendations failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "RECOMMENDATION_ERROR",
                    "message": "Failed to generate course recommendations",
                    "details": {"error": str(e)}
                }
            }
    
    async def get_shortest_path(
        self, 
        target_course: str, 
        completed_courses: List[str] = None
    ) -> Dict[str, Any]:
        """
        Get shortest prerequisite path to target course
        """
        if completed_courses is None:
            completed_courses = []
            
        cache_key = self._get_cache_key(
            "shortest_path",
            target_course=target_course,
            completed_courses="_".join(sorted(completed_courses))
        )
        
        # Check cache first
        cached_result = self._get_cached_result("paths", cache_key)
        if cached_result:
            return cached_result
        
        logger.info(f"Computing shortest path to {target_course}")
        start_time = time.time()
        
        try:
            # Get shortest path
            path = await self.path_analyzer.shortest_path_to_course(
                target_course, completed_courses
            )
            
            # Convert to serializable format
            result = {
                "success": True,
                "data": {
                    "path": asdict(path)
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache the result
            self._cache_result("paths", cache_key, result)
            
            logger.info(f"Shortest path computed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.error(f"Shortest path calculation failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "SHORTEST_PATH_ERROR",
                    "message": "Failed to compute shortest path",
                    "details": {"error": str(e)}
                }
            }
    
    async def get_alternative_paths(
        self, 
        target_course: str, 
        completed_courses: List[str] = None,
        num_alternatives: int = 3
    ) -> Dict[str, Any]:
        """
        Get multiple alternative prerequisite paths
        """
        if completed_courses is None:
            completed_courses = []
            
        cache_key = self._get_cache_key(
            "alternative_paths",
            target_course=target_course,
            completed_courses="_".join(sorted(completed_courses)),
            num_alternatives=num_alternatives
        )
        
        # Check cache first
        cached_result = self._get_cached_result("paths", cache_key)
        if cached_result:
            return cached_result
        
        logger.info(f"Computing {num_alternatives} alternative paths to {target_course}")
        start_time = time.time()
        
        try:
            # Get alternative paths
            paths = await self.path_analyzer.find_alternative_paths(
                target_course, completed_courses, num_alternatives
            )
            
            # Convert to serializable format
            result = {
                "success": True,
                "data": {
                    "target_course": target_course,
                    "alternative_paths": [asdict(path) for path in paths],
                    "num_paths_found": len(paths)
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache the result
            self._cache_result("paths", cache_key, result)
            
            logger.info(f"Alternative paths computed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.error(f"Alternative paths calculation failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "ALTERNATIVE_PATHS_ERROR",
                    "message": "Failed to compute alternative paths",
                    "details": {"error": str(e)}
                }
            }
    
    async def optimize_semester_plan(
        self, 
        target_courses: List[str], 
        completed_courses: List[str] = None,
        semesters_available: int = 8,
        max_credits_per_semester: int = 18
    ) -> Dict[str, Any]:
        """
        Optimize course schedule across multiple semesters
        """
        if completed_courses is None:
            completed_courses = []
            
        cache_key = self._get_cache_key(
            "semester_plan",
            target_courses="_".join(sorted(target_courses)),
            completed_courses="_".join(sorted(completed_courses)),
            semesters_available=semesters_available,
            max_credits_per_semester=max_credits_per_semester
        )
        
        # Check cache first
        cached_result = self._get_cached_result("paths", cache_key)
        if cached_result:
            return cached_result
        
        logger.info(f"Optimizing semester plan for {len(target_courses)} courses")
        start_time = time.time()
        
        try:
            # Get optimized schedule
            schedule = await self.path_analyzer.optimize_semester_plan(
                target_courses, completed_courses, semesters_available, max_credits_per_semester
            )
            
            # Convert to serializable format
            result = {
                "success": True,
                "data": {
                    "optimized_schedule": asdict(schedule)
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }
            
            # Cache the result
            self._cache_result("paths", cache_key, result)
            
            logger.info(f"Semester optimization computed in {result['computation_time_ms']}ms")
            return result
            
        except Exception as e:
            logger.error(f"Semester optimization failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "SEMESTER_OPTIMIZATION_ERROR",
                    "message": "Failed to optimize semester plan",
                    "details": {"error": str(e)}
                }
            }
    
    def clear_cache(self):
        """Clear all cached results"""
        self._cache = {"centrality": {}, "communities": {}, "paths": {}}
        self._cache_timestamps = {}
        
        # Also clear algorithm-specific caches
        self.centrality_analyzer.clear_cache()
        self.community_analyzer.clear_cache()
        self.path_analyzer.clear_cache()
        
        logger.info("All graph algorithms caches cleared")
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for graph algorithms service"""
        try:
            # Test basic graph service connectivity
            await self.graph_service.health_check()
            
            return {
                "status": "healthy",
                "cache_stats": {
                    "centrality_cached_items": len(self._cache["centrality"]),
                    "communities_cached_items": len(self._cache["communities"]),
                    "paths_cached_items": len(self._cache["paths"]),
                    "cache_ttl_seconds": self.cache_ttl
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def get_graph_subgraph(
        self,
        max_nodes: int = 50,
        max_edges: int = 100,
        include_centrality: bool = True,
        include_communities: bool = True,
        filter_by_subject: List[str] = None
    ) -> Dict[str, any]:
        """
        Get graph subgraph data for visualization, combining centrality and community data
        """
        operation = "subgraph"
        params = {
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "include_centrality": include_centrality,
            "include_communities": include_communities,
            "filter_by_subject": filter_by_subject or []
        }
        
        # Check cache first
        cache_key = self._get_cache_key(operation, **params)
        cached_result = self._get_cached_result("subgraph", cache_key)
        if cached_result:
            logger.info(f"Returning cached subgraph data")
            return cached_result
            
        logger.info(f"Computing graph subgraph: max_nodes={max_nodes}, max_edges={max_edges}")
        start_time = time.time()
        
        try:
            nodes_data = []
            edges_data = []
            
            # Get centrality data if requested
            centrality_scores = {}
            community_mapping = {}
            
            if include_centrality:
                centrality_result = await self.get_course_centrality(top_n=max_nodes * 2)
                if centrality_result["success"]:
                    for course in centrality_result["data"]["most_central_courses"]:
                        centrality_scores[course["course_code"]] = course["centrality_score"]
            
            # Get community data if requested
            if include_communities:
                community_result = await self.get_course_communities()
                if community_result["success"]:
                    for i, cluster in enumerate(community_result["data"]["clusters"]):
                        for course_code in cluster["course_codes"]:
                            community_mapping[course_code] = i
            
            # Get prerequisite relationships from graph service
            try:
                prereq_query = """
                MATCH (from:Course)-[r:REQUIRES]->(to:Course)
                WHERE r.type IN ['PREREQUISITE', 'PREREQUISITE_OR', 'COREQUISITE']
                RETURN from.code as from_course, to.code as to_course, r.type as relationship_type,
                       from.title as from_title, from.subject as from_subject, from.catalog_nbr as from_level,
                       to.title as to_title, to.subject as to_subject, to.catalog_nbr as to_level
                """
                
                if filter_by_subject:
                    prereq_query += f" AND (from.subject IN {filter_by_subject} OR to.subject IN {filter_by_subject})"
                
                prereq_query += " LIMIT $max_edges"
                
                prereq_results = await self.graph_service.execute_query(
                    prereq_query,
                    max_edges=max_edges * 2  # Get extra to ensure we have enough after filtering
                )
                
                # Build set of course codes that appear in relationships
                course_codes_in_graph = set()
                valid_edges = []
                
                for record in prereq_results:
                    from_course = record["from_course"]
                    to_course = record["to_course"]
                    
                    # Apply subject filter if specified
                    if filter_by_subject:
                        from_subject = record.get("from_subject", "")
                        to_subject = record.get("to_subject", "")
                        if not (from_subject in filter_by_subject or to_subject in filter_by_subject):
                            continue
                    
                    course_codes_in_graph.add(from_course)
                    course_codes_in_graph.add(to_course)
                    
                    valid_edges.append({
                        "from_course": from_course,
                        "to_course": to_course,
                        "relationship_type": record["relationship_type"],
                        "from_title": record.get("from_title", ""),
                        "from_subject": record.get("from_subject", ""),
                        "from_level": record.get("from_level", 0),
                        "to_title": record.get("to_title", ""),
                        "to_subject": record.get("to_subject", ""),
                        "to_level": record.get("to_level", 0)
                    })
                
                # Prioritize nodes by centrality score and limit to max_nodes
                prioritized_courses = []
                for course_code in course_codes_in_graph:
                    score = centrality_scores.get(course_code, 0.0)
                    prioritized_courses.append((course_code, score))
                
                # Sort by centrality score (highest first) and take top max_nodes
                prioritized_courses.sort(key=lambda x: x[1], reverse=True)
                selected_courses = set(course[0] for course in prioritized_courses[:max_nodes])
                
                # Build nodes data
                node_info_map = {}
                for edge in valid_edges:
                    # Add from_course info
                    if edge["from_course"] in selected_courses and edge["from_course"] not in node_info_map:
                        node_info_map[edge["from_course"]] = {
                            "course_code": edge["from_course"],
                            "course_title": edge["from_title"],
                            "subject": edge["from_subject"],
                            "level": int(edge["from_level"]) if edge["from_level"] else 0,
                            "centrality_score": centrality_scores.get(edge["from_course"]),
                            "community_id": community_mapping.get(edge["from_course"])
                        }
                    
                    # Add to_course info
                    if edge["to_course"] in selected_courses and edge["to_course"] not in node_info_map:
                        node_info_map[edge["to_course"]] = {
                            "course_code": edge["to_course"],
                            "course_title": edge["to_title"],
                            "subject": edge["to_subject"],
                            "level": int(edge["to_level"]) if edge["to_level"] else 0,
                            "centrality_score": centrality_scores.get(edge["to_course"]),
                            "community_id": community_mapping.get(edge["to_course"])
                        }
                
                nodes_data = list(node_info_map.values())
                
                # Filter edges to only include those between selected nodes and limit count
                filtered_edges = []
                for edge in valid_edges:
                    if (edge["from_course"] in selected_courses and 
                        edge["to_course"] in selected_courses and 
                        len(filtered_edges) < max_edges):
                        
                        filtered_edges.append({
                            "from_course": edge["from_course"],
                            "to_course": edge["to_course"],
                            "relationship_type": edge["relationship_type"]
                        })
                
                edges_data = filtered_edges
                
            except Exception as e:
                logger.warning(f"Failed to get prerequisite relationships: {e}")
                # Return empty graph on failure
                nodes_data = []
                edges_data = []
            
            computation_time_ms = int((time.time() - start_time) * 1000)
            
            result = {
                "success": True,
                "data": {
                    "courses": nodes_data,
                    "prerequisites": edges_data,
                    "centrality_scores": centrality_scores,
                    "communities": community_mapping,
                    "metadata": {
                        "node_count": len(nodes_data),
                        "edge_count": len(edges_data),
                        "computation_time_ms": computation_time_ms,
                        "filtered_by_subject": filter_by_subject,
                        "include_centrality": include_centrality,
                        "include_communities": include_communities
                    }
                },
                "computation_time_ms": computation_time_ms
            }
            
            # Cache the result
            self._cache_result("subgraph", cache_key, result)
            
            logger.info(f"Graph subgraph computation completed in {computation_time_ms}ms: "
                       f"{len(nodes_data)} nodes, {len(edges_data)} edges")
            
            return result
            
        except Exception as e:
            logger.error(f"Graph subgraph computation failed: {e}")
            return {
                "success": False,
                "error": {
                    "code": "SUBGRAPH_ERROR",
                    "message": "Failed to compute graph subgraph",
                    "details": {"error": str(e)}
                },
                "computation_time_ms": int((time.time() - start_time) * 1000)
            }