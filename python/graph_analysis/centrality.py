"""
Course Centrality Analysis for Cornell Course Navigator
Implements PageRank, betweenness centrality, and gateway course detection using Neo4j GDS
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

# Removed direct Neo4j dependency - use GraphService abstraction instead

logger = logging.getLogger(__name__)

# Input validation constants
MAX_TOP_N = 1000
MAX_DAMPING_FACTOR = 0.99
MIN_DAMPING_FACTOR = 0.01
MAX_ITERATIONS = 1000


@dataclass
class CourseRanking:
    """Course ranking with centrality score"""
    course_code: str
    course_title: str
    centrality_score: float
    rank: int
    subject: str
    level: int


@dataclass
class CentralityAnalysis:
    """Complete centrality analysis results"""
    most_central: List[CourseRanking]
    bridge_courses: List[CourseRanking]
    gateway_courses: List[CourseRanking]
    analysis_metadata: Dict[str, any]


class CourseCentrality:
    """Course centrality analysis using Neo4j GDS algorithms"""
    
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service
        self.graph_name = "prerequisite_graph"
        # Memoize graph existence checks to avoid redundant DB calls
        self._graph_exists_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes
        
    def _validate_top_n(self, top_n: int) -> int:
        """Validate and clamp top_n parameter"""
        if top_n <= 0:
            return 20  # Default
        return min(top_n, MAX_TOP_N)
    
    def _validate_damping_factor(self, damping_factor: float) -> float:
        """Validate and clamp damping factor"""
        return max(MIN_DAMPING_FACTOR, min(damping_factor, MAX_DAMPING_FACTOR))
    
    def _validate_iterations(self, max_iterations: int) -> int:
        """Validate and clamp max iterations"""
        return max(1, min(max_iterations, MAX_ITERATIONS))
    
    def _is_graph_cache_valid(self) -> bool:
        """Check if graph existence cache is still valid"""
        if self._cache_timestamp is None:
            return False
        current_time = time.time()
        return (current_time - self._cache_timestamp) < self._cache_ttl

    async def _ensure_graph_exists(self) -> None:
        """Ensure prerequisite graph exists in GDS catalog with memoization"""
        # Check memoized cache first
        if self._is_graph_cache_valid() and self._graph_exists_cache.get(self.graph_name):
            return
            
        try:
            # Check if graph exists in Neo4j
            check_query = f"""
            CALL gds.graph.exists('{self.graph_name}') YIELD exists
            RETURN exists
            """
            
            result = await self.neo4j.execute_query(check_query)
            exists = result[0]["exists"] if result else False
            
            # Cache the result
            self._graph_exists_cache[self.graph_name] = exists
            self._cache_timestamp = time.time()
            
            if not exists:
                logger.info(f"Creating GDS graph projection: {self.graph_name}")
                
                # Create graph projection with explicit weight defaults
                create_query = f"""
                CALL gds.graph.project(
                    '{self.graph_name}',
                    'Course',
                    {{
                        REQUIRES: {{
                            type: 'REQUIRES',
                            properties: {{
                                confidence: {{
                                    property: 'confidence',
                                    defaultValue: 1.0
                                }},
                                weight: {{
                                    property: 'weight', 
                                    defaultValue: 1.0
                                }}
                            }}
                        }}
                    }}
                ) 
                YIELD graphName, nodeCount, relationshipCount
                RETURN graphName, nodeCount, relationshipCount
                """
                
                result = await self.neo4j.execute_query(create_query)
                if result:
                    info = result[0]
                    logger.info(f"Created GDS graph: {info['nodeCount']} nodes, {info['relationshipCount']} relationships")
                    # Update cache to reflect that graph now exists
                    self._graph_exists_cache[self.graph_name] = True
                    self._cache_timestamp = time.time()
                
        except Exception as e:
            logger.error(f"Failed to ensure graph exists: {e}")
            # Clear cache on error to force recheck next time
            self._graph_exists_cache.pop(self.graph_name, None)
            raise
    
    async def calculate_pagerank(self, damping_factor: float = 0.85, max_iterations: int = 100) -> List[CourseRanking]:
        """
        Calculate PageRank centrality using Neo4j GDS
        Higher scores indicate courses that are central to the curriculum
        """
        # Validate inputs
        damping_factor = self._validate_damping_factor(damping_factor)
        max_iterations = self._validate_iterations(max_iterations)
        
        logger.info(f"Calculating PageRank with damping_factor={damping_factor}, max_iterations={max_iterations}")
        start_time = time.time()
        
        try:
            await self._ensure_graph_exists()
            
            # Run PageRank using GDS
            pagerank_query = f"""
            CALL gds.pageRank.stream('{self.graph_name}', {{
                dampingFactor: $damping_factor,
                maxIterations: $max_iterations,
                tolerance: 1e-6
            }})
            YIELD nodeId, score
            
            // Get course information
            MATCH (c:Course) WHERE id(c) = nodeId
            RETURN c.code as course_code, c.title as title, c.subject as subject, 
                   c.catalog_nbr as level, score
            ORDER BY score DESC
            """
            
            result = await self.neo4j.execute_query(
                pagerank_query, 
                damping_factor=damping_factor,
                max_iterations=max_iterations
            )
            
            # Convert to ranked list
            rankings = []
            for rank, record in enumerate(result, 1):
                try:
                    level = int(record.get("level", 0))
                except (ValueError, TypeError):
                    level = 0
                    
                rankings.append(CourseRanking(
                    course_code=record["course_code"],
                    course_title=record.get("title", ""),
                    centrality_score=float(record["score"]),
                    rank=rank,
                    subject=record.get("subject", ""),
                    level=level
                ))
            
            calculation_time = time.time() - start_time
            logger.info(f"PageRank completed in {calculation_time:.2f}s for {len(rankings)} courses")
            
            return rankings
            
        except Exception as e:
            logger.error(f"PageRank calculation failed: {e}")
            raise
    
    async def get_bridge_courses(self, min_betweenness: float = 0.01) -> List[CourseRanking]:
        """
        Identify bridge courses using betweenness centrality with Neo4j GDS
        High betweenness = courses that connect different curriculum areas
        Uses undirected view for better bridge detection in DAGs
        """
        logger.info(f"Calculating bridge courses with min_betweenness={min_betweenness}")
        start_time = time.time()
        
        try:
            await self._ensure_graph_exists()
            
            # Create undirected projection for better bridge detection
            undirected_graph_name = f"{self.graph_name}_undirected"
            
            # Check if undirected graph exists, create if not
            check_undirected_query = f"""
            CALL gds.graph.exists('{undirected_graph_name}') YIELD exists
            RETURN exists
            """
            
            result = await self.neo4j.execute_query(check_undirected_query)
            undirected_exists = result[0]["exists"] if result else False
            
            if not undirected_exists:
                create_undirected_query = f"""
                CALL gds.graph.project(
                    '{undirected_graph_name}',
                    'Course',
                    {{
                        REQUIRES: {{
                            type: 'REQUIRES',
                            orientation: 'UNDIRECTED',
                            properties: ['confidence']
                        }}
                    }}
                ) 
                YIELD graphName, nodeCount, relationshipCount
                RETURN graphName, nodeCount, relationshipCount
                """
                
                await self.neo4j.execute_query(create_undirected_query)
                logger.info(f"Created undirected GDS graph projection: {undirected_graph_name}")
            
            # Calculate betweenness centrality on undirected graph
            betweenness_query = f"""
            CALL gds.betweenness.stream('{undirected_graph_name}')
            YIELD nodeId, score
            
            // Get course information and filter by minimum threshold
            MATCH (c:Course) WHERE id(c) = nodeId AND score >= $min_betweenness
            RETURN c.code as course_code, c.title as title, c.subject as subject, 
                   c.catalog_nbr as level, score
            ORDER BY score DESC
            """
            
            result = await self.neo4j.execute_query(
                betweenness_query,
                min_betweenness=min_betweenness
            )
            
            # Convert to ranked list
            bridge_courses = []
            for rank, record in enumerate(result, 1):
                try:
                    level = int(record.get("level", 0))
                except (ValueError, TypeError):
                    level = 0
                    
                bridge_courses.append(CourseRanking(
                    course_code=record["course_code"],
                    course_title=record.get("title", ""),
                    centrality_score=float(record["score"]),
                    rank=rank,
                    subject=record.get("subject", ""),
                    level=level
                ))
            
            calculation_time = time.time() - start_time
            logger.info(f"Bridge course analysis completed in {calculation_time:.2f}s, found {len(bridge_courses)} bridge courses")
            
            return bridge_courses
            
        except Exception as e:
            logger.error(f"Bridge course calculation failed: {e}")
            raise
    
    async def get_gateway_courses(self, min_in_degree: int = 2) -> List[CourseRanking]:
        """
        Identify gateway courses with high in-degree (courses that unlock many others)
        Current definition: courses with many incoming prerequisite relationships
        """
        logger.info(f"Calculating gateway courses with min_in_degree={min_in_degree}")
        start_time = time.time()
        
        try:
            # Direct Cypher query for in-degree calculation
            gateway_query = """
            MATCH (c:Course)
            WITH c, size([(c)<-[:REQUIRES]-() | 1]) as in_degree
            WHERE in_degree >= $min_in_degree
            RETURN c.code as course_code, c.title as title, c.subject as subject, 
                   c.catalog_nbr as level, in_degree
            ORDER BY in_degree DESC
            """
            
            result = await self.neo4j.execute_query(
                gateway_query,
                min_in_degree=min_in_degree
            )
            
            # Convert to ranked list
            gateway_courses = []
            for rank, record in enumerate(result, 1):
                try:
                    level = int(record.get("level", 0))
                except (ValueError, TypeError):
                    level = 0
                    
                gateway_courses.append(CourseRanking(
                    course_code=record["course_code"],
                    course_title=record.get("title", ""),
                    centrality_score=float(record["in_degree"]),
                    rank=rank,
                    subject=record.get("subject", ""),
                    level=level
                ))
            
            calculation_time = time.time() - start_time
            logger.info(f"Gateway course analysis completed in {calculation_time:.2f}s, found {len(gateway_courses)} gateway courses")
            
            return gateway_courses
            
        except Exception as e:
            logger.error(f"Gateway course calculation failed: {e}")
            raise
    
    async def run_complete_analysis(
        self, 
        top_n: int = 20,
        damping_factor: float = 0.85,
        min_betweenness: float = 0.01,
        min_in_degree: int = 2
    ) -> CentralityAnalysis:
        """
        Run complete centrality analysis using Neo4j GDS and return top results
        """
        # Validate inputs
        top_n = self._validate_top_n(top_n)
        damping_factor = self._validate_damping_factor(damping_factor)
        
        logger.info(f"Starting complete centrality analysis with top_n={top_n}")
        overall_start = time.time()
        
        try:
            await self._ensure_graph_exists()
            
            # Calculate all centrality measures
            pagerank_results = await self.calculate_pagerank(damping_factor)
            bridge_results = await self.get_bridge_courses(min_betweenness)  
            gateway_results = await self.get_gateway_courses(min_in_degree)
            
            # Get top N results for each category
            most_central = pagerank_results[:top_n]
            bridge_courses = bridge_results[:top_n]
            gateway_courses = gateway_results[:top_n]
            
            total_time = time.time() - overall_start
            
            # Get graph statistics
            stats_query = f"""
            CALL gds.graph.list('{self.graph_name}')
            YIELD nodeCount, relationshipCount
            RETURN nodeCount, relationshipCount
            """
            
            stats_result = await self.neo4j.execute_query(stats_query)
            stats = stats_result[0] if stats_result else {"nodeCount": 0, "relationshipCount": 0}
            
            # Prepare metadata
            metadata = {
                "total_courses": stats["nodeCount"],
                "total_prerequisites": stats["relationshipCount"],
                "analysis_time_seconds": total_time,
                "algorithm_implementation": "neo4j_gds",
                "parameters": {
                    "top_n": top_n,
                    "damping_factor": damping_factor,
                    "min_betweenness": min_betweenness,
                    "min_in_degree": min_in_degree
                },
                "algorithm_details": {
                    "pagerank_method": "gds.pageRank.stream",
                    "betweenness_method": "gds.betweenness.stream",
                    "gateway_method": "cypher_in_degree",
                    "undirected_betweenness": True
                }
            }
            
            logger.info(f"Complete centrality analysis finished in {total_time:.2f}s")
            
            return CentralityAnalysis(
                most_central=most_central,
                bridge_courses=bridge_courses,
                gateway_courses=gateway_courses,
                analysis_metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Complete centrality analysis failed: {e}")
            raise
    
    async def clear_cache(self):
        """Clear GDS graph projections and reset cache"""
        # Clear memoized graph existence cache
        self._graph_exists_cache.clear()
        self._cache_timestamp = None
        
        try:
            # Drop main graph projection
            drop_query = f"""
            CALL gds.graph.exists('{self.graph_name}') YIELD exists
            CALL apoc.do.when(exists, 
                "CALL gds.graph.drop($graphName) YIELD graphName RETURN graphName",
                "RETURN null as graphName",
                {{graphName: $graphName}}
            ) YIELD value
            RETURN value.graphName as dropped
            """
            
            await self.neo4j.execute_query(drop_query, graphName=self.graph_name)
            
            # Drop undirected graph projection  
            undirected_graph_name = f"{self.graph_name}_undirected"
            drop_undirected_query = f"""
            CALL gds.graph.exists('{undirected_graph_name}') YIELD exists
            CALL apoc.do.when(exists, 
                "CALL gds.graph.drop($graphName) YIELD graphName RETURN graphName",
                "RETURN null as graphName",
                {{graphName: $graphName}}
            ) YIELD value
            RETURN value.graphName as dropped
            """
            
            await self.neo4j.execute_query(drop_undirected_query, graphName=undirected_graph_name)
            
            logger.info("GDS graph projections cleared")
            
        except Exception as e:
            logger.warning(f"Failed to clear GDS graphs (may not exist): {e}")
    
    async def get_graph_stats(self) -> Dict[str, any]:
        """Get current graph statistics"""
        try:
            await self._ensure_graph_exists()
            
            stats_query = f"""
            CALL gds.graph.list('{self.graph_name}')
            YIELD nodeCount, relationshipCount, memoryUsage
            RETURN nodeCount, relationshipCount, memoryUsage
            """
            
            result = await self.neo4j.execute_query(stats_query)
            if result:
                return {
                    "node_count": result[0]["nodeCount"],
                    "relationship_count": result[0]["relationshipCount"], 
                    "memory_usage": result[0]["memoryUsage"],
                    "graph_name": self.graph_name
                }
            else:
                return {"error": "No graph statistics available"}
                
        except Exception as e:
            logger.error(f"Failed to get graph stats: {e}")
            return {"error": str(e)}