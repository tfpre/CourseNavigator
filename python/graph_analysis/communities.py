"""
Course Community Detection for Cornell Course Navigator
Implements Louvain algorithm and department overlap analysis using Neo4j GDS
"""

import logging
import time
import os
import asyncio
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict
from prometheus_client import Histogram

logger = logging.getLogger(__name__)

GDS_QUERY_TIMEOUT_MS = int(os.getenv("GDS_QUERY_TIMEOUT_MS", "300"))  # default 300ms
LOUVAIN_TIMEOUT_MS = int(os.getenv("LOUVAIN_TIMEOUT_MS", "2000")) # default 2000ms

# Graph similarity constants
MAX_LEVEL_DIFFERENCE = int(os.getenv("MAX_LEVEL_DIFFERENCE", "200"))  # max difference in course levels
MIN_SIMILARITY_WEIGHT = float(os.getenv("MIN_SIMILARITY_WEIGHT", "0.1"))  # minimum similarity threshold

# Prometheus metrics
community_cypher_ms = Histogram("community_cypher_ms", "Time for cohesion query")

@dataclass
class CourseCluster:
    """Course cluster from community detection"""
    cluster_id: int
    course_codes: List[str]
    cluster_size: int
    dominant_subjects: List[str]
    avg_course_level: float
    cohesion_score: float


@dataclass
class CourseRecommendation:
    """Course recommendation based on community membership"""
    course_code: str
    course_title: str
    recommendation_score: float
    reason: str
    shared_community: int


@dataclass
class DepartmentOverlap:
    """Inter-department connection analysis"""
    department_a: str
    department_b: str
    shared_courses: int
    connection_strength: float
    bridge_courses: List[str]


@dataclass
class CommunityAnalysis:
    """Complete community detection results"""
    clusters: List[CourseCluster]
    department_overlaps: List[DepartmentOverlap]
    modularity_score: float
    analysis_metadata: Dict[str, any]


class CourseCommunities:
    """Course community detection using Neo4j GDS algorithms"""
    
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service
        self.similarity_graph_name = "similarity_graph"
        # Memoize graph existence checks to avoid redundant DB calls
        self._graph_exists_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes
        
    def _is_graph_cache_valid(self) -> bool:
        """Check if graph existence cache is still valid"""
        if self._cache_timestamp is None:
            return False
        current_time = time.time()
        return (current_time - self._cache_timestamp) < self._cache_ttl

    async def _ensure_similarity_graph_exists(self) -> None:
        """
        Ensure similarity graph exists in GDS catalog.
        Modernized to use gds.graph.project.
        """
        # Check memoized cache first
        if self._is_graph_cache_valid() and self._graph_exists_cache.get(self.similarity_graph_name):
            return

        try:
            # Check if similarity graph exists
            check_query = "CALL gds.graph.exists($name) YIELD exists"
            res = await self.neo4j.execute_query(check_query, name=self.similarity_graph_name, timeout=GDS_QUERY_TIMEOUT_MS/1000)
            exists = res[0]["exists"] if res else False

            self._graph_exists_cache[self.similarity_graph_name] = exists
            self._cache_timestamp = time.time()

            if not exists:
                logger.info(f"Creating similarity graph projection: {self.similarity_graph_name}")
                project_query = """
                CALL gds.graph.project(
                    $name,
                    {Course: {properties: ['clusterId']}},
                    {SIMILAR_TO: {properties: ['similarity']}}
                )
                YIELD graphName, nodeCount, relationshipCount
                RETURN graphName, nodeCount, relationshipCount
                """
                result = await self.neo4j.execute_query(project_query, name=self.similarity_graph_name, timeout=GDS_QUERY_TIMEOUT_MS/1000)
                if result:
                    info = result[0]
                    logger.info(f"Created similarity graph: {info['nodeCount']} nodes, {info['relationshipCount']} relationships")
                    self._graph_exists_cache[self.similarity_graph_name] = True
                    self._cache_timestamp = time.time()

        except Exception as e:
            logger.error(f"Failed to ensure similarity graph exists: {e}")
            self._graph_exists_cache.pop(self.similarity_graph_name, None)
            raise
    
    async def detect_communities(self, algorithm: str = 'louvain') -> None:
        """
        Detect communities using Neo4j GDS algorithms and write them back to the graph.
        """
        logger.info(f"Detecting and writing communities using {algorithm} algorithm with GDS")
        start_time = time.time()

        try:
            await self._ensure_similarity_graph_exists()

            if algorithm == 'louvain':
                # Use GDS Louvain algorithm and write back the community id
                write_query = "CALL gds.louvain.write($name, { writeProperty: 'clusterId' }) YIELD communityCount"
                await self.neo4j.execute_query(write_query, name=self.similarity_graph_name, timeout=LOUVAIN_TIMEOUT_MS/1000)
            else:
                raise ValueError(f"Unsupported algorithm: {algorithm}. Only 'louvain' is supported with GDS.")

            detection_time = time.time() - start_time
            logger.info(f"Community detection and writeback completed in {detection_time:.2f}s")

        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            raise
    
    async def write_communities(self, algorithm: str = 'louvain') -> None:
        """
        Wrapper method to maintain compatibility with run_complete_analysis.
        """
        await self.detect_communities(algorithm)
    
    @community_cypher_ms.time()
    async def compute_cohesion(self) -> Dict[int, float]:
        """
        One-pass cohesion calculation.
        """
        q = """
        MATCH (c1:Course)-[r:SIMILAR_TO]->(c2:Course)
        WITH c1.clusterId AS a, c2.clusterId AS b, r.similarity AS w
        WITH a, sum(CASE WHEN a=b THEN w ELSE 0 END) AS intra, sum(w) AS total
        RETURN a AS clusterId,
               CASE WHEN total = 0 THEN 0.0 ELSE intra / total END AS cohesion
        """
        try:
            res = await self.neo4j.execute_query(q, timeout=GDS_QUERY_TIMEOUT_MS/1000)
            return {row["clusterId"]: row["cohesion"] for row in res}
        except asyncio.TimeoutError:
            logger.warning("Cohesion query timed out; returning empty dict")
            return {}

    async def analyze_clusters(self, communities: List[Set[str]]) -> List[CourseCluster]:
        """
        Analyze detected communities and extract cluster characteristics using Neo4j queries
        """
        logger.info("Analyzing community clusters")
        
        try:
            clusters = []
            
            for cluster_id, community in enumerate(communities):
                course_codes = list(community)
                cluster_size = len(course_codes)
                
                if cluster_size == 0:
                    continue
                
                # Get course information for the cluster
                cluster_info_query = """
                MATCH (c:Course)
                WHERE c.code IN $course_codes
                RETURN c.code as code, c.subject as subject, c.catalog_nbr as level
                """
                
                course_results = await self.neo4j.execute_query(
                    cluster_info_query,
                    course_codes=course_codes
                )
                
                # Analyze subject distribution
                subject_counts = defaultdict(int)
                level_sum = 0
                valid_levels = 0
                
                for record in course_results:
                    subject = record.get("subject", "")
                    if subject:
                        subject_counts[subject] += 1
                    
                    try:
                        level = int(record.get("level", 0))
                        if level > 0:
                            level_sum += level
                            valid_levels += 1
                    except (ValueError, TypeError):
                        pass
                
                # Get dominant subjects (top 3)
                dominant_subjects = [
                    subject for subject, count in 
                    sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                ]
                
                # Calculate average course level
                avg_level = level_sum / valid_levels if valid_levels > 0 else 0.0
                
                # Cohesion score will be calculated in a separate step
                cohesion_score = 0.0
                
                clusters.append(CourseCluster(
                    cluster_id=cluster_id,
                    course_codes=course_codes,
                    cluster_size=cluster_size,
                    dominant_subjects=dominant_subjects,
                    avg_course_level=avg_level,
                    cohesion_score=cohesion_score
                ))
            
            # Sort clusters by size (largest first)
            clusters.sort(key=lambda x: x.cluster_size, reverse=True)
            
            logger.info(f"Analyzed {len(clusters)} clusters")
            return clusters
            
        except Exception as e:
            logger.error(f"Cluster analysis failed: {e}")
            raise
    
    async def analyze_department_overlap(self) -> List[DepartmentOverlap]:
        """
        Analyze how departments overlap through prerequisite and similarity connections
        """
        logger.info("Analyzing department overlap")
        start_time = time.time()
        
        try:
            await self._ensure_similarity_graph_exists()
            
            # Get department connections using GDS graph
            overlap_query = f"""
            // Get all department pairs with connections
            CALL gds.graph.relationshipProperty.stream('{self.similarity_graph_name}', 'weight')
            YIELD sourceNodeId, targetNodeId, propertyValue
            
            // Get course information for connected nodes
            MATCH (source:Course), (target:Course)
            WHERE elementId(source) = sourceNodeId AND elementId(target) = targetNodeId
            AND source.subject <> target.subject  // Only cross-department connections
            
            WITH source.subject as dept_a, target.subject as dept_b,
                 source.code as course_a, target.code as course_b,
                 propertyValue as weight
            
            // Group by department pairs
            WITH dept_a, dept_b, 
                 collect(DISTINCT course_a) + collect(DISTINCT course_b) as bridge_courses,
                 count(*) as connection_count,
                 avg(weight) as avg_weight
            
            // Get department sizes for normalization
            MATCH (ca:Course {subject: dept_a}), (cb:Course {subject: dept_b})
            WITH dept_a, dept_b, bridge_courses, connection_count, avg_weight,
                 count(DISTINCT ca) as size_a, count(DISTINCT cb) as size_b
            
            // Calculate connection strength
            WITH dept_a, dept_b, bridge_courses, connection_count, avg_weight,
                 toFloat(connection_count) / toFloat(apoc.coll.min([size_a, size_b])) as connection_strength
            
            WHERE connection_count > 0
            RETURN dept_a, dept_b, bridge_courses, connection_count, connection_strength
            ORDER BY connection_strength DESC
            """
            
            result = await self.neo4j.execute_query(overlap_query)
            
            overlaps = []
            for record in result:
                overlaps.append(DepartmentOverlap(
                    department_a=record["dept_a"],
                    department_b=record["dept_b"],
                    shared_courses=record["connection_count"],
                    connection_strength=float(record["connection_strength"]),
                    bridge_courses=record["bridge_courses"]
                ))
            
            analysis_time = time.time() - start_time
            logger.info(f"Department overlap analysis completed in {analysis_time:.2f}s: "
                       f"{len(overlaps)} department pairs with connections")
            
            return overlaps
            
        except Exception as e:
            logger.error(f"Department overlap analysis failed: {e}")
            raise
    
    async def get_course_recommendations(
        self, 
        course_code: str, 
        num_recommendations: int = 5
    ) -> List[CourseRecommendation]:
        """
        Recommend courses based on community membership and similarity connections
        """
        logger.info(f"Getting recommendations for course: {course_code}")
        
        try:
            await self._ensure_similarity_graph_exists()
            
            # Check if course exists
            course_check_query = """
            MATCH (c:Course {code: $course_code})
            RETURN c.subject as subject, c.catalog_nbr as level, c.title as title
            """
            
            course_result = await self.neo4j.execute_query(
                course_check_query,
                course_code=course_code
            )
            
            if not course_result:
                logger.warning(f"Course {course_code} not found")
                return []
            
            target_info = course_result[0]
            target_subject = target_info.get("subject", "")
            target_level = int(target_info.get("level", 0) or 0)
            
            # Detect communities to find the target course's community
            communities, _ = await self.detect_communities()
            
            # Find which community the target course belongs to
            target_community = None
            community_id = -1
            
            for i, community in enumerate(communities):
                if course_code in community:
                    target_community = community
                    community_id = i
                    break
            
            if target_community is None:
                logger.warning(f"Course {course_code} not found in any community")
                return []
            
            # Get recommendations from the same community
            community_courses = list(target_community - {course_code})
            
            if not community_courses:
                return []
            
            # Get detailed information for candidate courses
            recommendations_query = f"""
            MATCH (c:Course)
            WHERE c.code IN $community_courses
            
            // Check for direct connection in similarity graph
            OPTIONAL MATCH (target:Course {{code: $target_code}})
            CALL gds.graph.relationshipProperty.stream('{self.similarity_graph_name}', 'weight')
            YIELD sourceNodeId, targetNodeId, propertyValue
            WITH c, target, sourceNodeId, targetNodeId, propertyValue
            WHERE (elementId(c) = sourceNodeId AND elementId(target) = targetNodeId) OR 
                  (elementId(c) = targetNodeId AND elementId(target) = sourceNodeId)
            
            RETURN c.code as code, c.title as title, c.subject as subject, 
                   c.catalog_nbr as level, propertyValue as connection_weight
            
            UNION
            
            // Also get courses without direct connections
            MATCH (c:Course)
            WHERE c.code IN $community_courses
            AND NOT EXISTS {{
                MATCH (target:Course {{code: $target_code}})
                CALL gds.graph.relationshipProperty.stream('{self.similarity_graph_name}', 'weight')
                YIELD sourceNodeId, targetNodeId
                WHERE (elementId(c) = sourceNodeId AND elementId(target) = targetNodeId) OR 
                      (elementId(c) = targetNodeId AND elementId(target) = sourceNodeId)
                RETURN 1 LIMIT 1
            }}
            RETURN c.code as code, c.title as title, c.subject as subject, 
                   c.catalog_nbr as level, null as connection_weight
            """
            
            candidate_results = await self.neo4j.execute_query(
                recommendations_query,
                community_courses=community_courses,
                target_code=course_code
            )
            
            # Score candidates
            recommendations = []
            
            for record in candidate_results:
                candidate_code = record["code"]
                candidate_subject = record.get("subject", "")
                candidate_level = int(record.get("level", 0) or 0)
                connection_weight = record.get("connection_weight")
                
                # Calculate recommendation score
                score = 0.0
                reason_parts = []
                
                # Same community bonus
                score += 0.5
                reason_parts.append("same community")
                
                # Direct connection bonus
                if connection_weight is not None:
                    score += float(connection_weight) * 0.3
                    if connection_weight >= 2.0:
                        reason_parts.append("prerequisite relationship")
                    else:
                        reason_parts.append("subject similarity")
                
                # Subject similarity bonus
                if candidate_subject == target_subject:
                    score += 0.3
                    reason_parts.append("same subject")
                
                # Level proximity bonus
                level_diff = abs(candidate_level - target_level)
                if level_diff <= 100:
                    level_bonus = max(0, 0.2 - (level_diff * 0.002))
                    score += level_bonus
                    reason_parts.append("similar level")
                
                if score > 0:
                    recommendations.append(CourseRecommendation(
                        course_code=candidate_code,
                        course_title=record.get("title", ""),
                        recommendation_score=score,
                        reason=", ".join(reason_parts),
                        shared_community=community_id
                    ))
            
            # Sort by score and return top N
            recommendations.sort(key=lambda x: x.recommendation_score, reverse=True)
            top_recommendations = recommendations[:num_recommendations]
            
            logger.info(f"Generated {len(top_recommendations)} recommendations for {course_code}")
            return top_recommendations
            
        except Exception as e:
            logger.error(f"Course recommendation failed: {e}")
            raise
    
    async def run_complete_analysis(self, algorithm: str = 'louvain') -> CommunityAnalysis:
        """
        Run complete community analysis using Neo4j GDS including clustering and department overlap
        """
        logger.info(f"Starting complete community analysis with {algorithm} algorithm")
        overall_start = time.time()

        try:
            await self._ensure_similarity_graph_exists()
            await self.write_communities(algorithm)
            cohesion_scores = await self.compute_cohesion()

            # Get clusters from graph
            get_clusters_query = """
            MATCH (c:Course)
            WHERE c.clusterId IS NOT NULL
            WITH c.clusterId as clusterId, c.code as course_code
            RETURN clusterId, collect(course_code) as course_codes
            ORDER BY clusterId
            """
            clusters_result = await self.neo4j.execute_query(get_clusters_query)
            
            communities = []
            for record in clusters_result:
                communities.append(set(record["course_codes"]))

            # Analyze clusters
            clusters = await self.analyze_clusters(communities)
            
            # Add cohesion scores to clusters
            for cluster in clusters:
                cluster.cohesion_score = cohesion_scores.get(cluster.cluster_id, 0.0)

            # Analyze department overlaps
            # Temporarily disabled due to performance issues
            department_overlaps = []

            total_time = time.time() - overall_start

            # Get graph statistics
            stats_query = f"""
            CALL gds.graph.list('{self.similarity_graph_name}')
            YIELD nodeCount, relationshipCount
            RETURN nodeCount, relationshipCount
            """
            
            stats_result = await self.neo4j.execute_query(stats_query)
            stats = stats_result[0] if stats_result else {"nodeCount": 0, "relationshipCount": 0}

            # Get modularity score
            modularity_query = f"""
            CALL gds.louvain.stats('{self.similarity_graph_name}', {{
                relationshipWeightProperty: 'weight'
            }})
            YIELD modularity
            RETURN modularity
            """
            modularity_result = await self.neo4j.execute_query(modularity_query)
            modularity = modularity_result[0]["modularity"] if modularity_result else 0.0

            # Prepare metadata
            metadata = {
                "total_courses": stats["nodeCount"],
                "total_connections": stats["relationshipCount"],
                "algorithm_used": algorithm,
                "algorithm_implementation": "neo4j_gds",
                "num_communities": len(communities),
                "modularity_score": modularity,
                "analysis_time_seconds": total_time,
                "largest_community_size": max(len(c) for c in communities) if communities else 0,
                "smallest_community_size": min(len(c) for c in communities) if communities else 0,
                "avg_community_size": sum(len(c) for c in communities) / len(communities) if communities else 0,
            }

            logger.info(f"Complete community analysis finished in {total_time:.2f}s")

            return CommunityAnalysis(
                clusters=clusters,
                department_overlaps=department_overlaps,
                modularity_score=modularity,
                analysis_metadata=metadata
            )

        except Exception as e:
            logger.error(f"Complete community analysis failed: {e}")
            raise
    
    async def clear_cache(self):
        """Clear GDS graph projections and reset cache"""
        # Clear memoized graph existence cache
        self._graph_exists_cache.clear()
        self._cache_timestamp = None
        
        try:
            # Drop similarity graph projection
            drop_query = f"""
            CALL gds.graph.exists('{self.similarity_graph_name}') YIELD exists
            CALL apoc.do.when(exists, 
                "CALL gds.graph.drop($graphName) YIELD graphName RETURN graphName",
                "RETURN null as graphName",
                {{graphName: $graphName}}
            ) YIELD value
            RETURN value.graphName as dropped
            """
            
            await self.neo4j.execute_query(drop_query, graphName=self.similarity_graph_name)
            logger.info("Similarity graph projection cleared")
            
        except Exception as e:
            logger.warning(f"Failed to clear similarity graph (may not exist): {e}")
    
    async def get_graph_stats(self) -> Dict[str, any]:
        """Get current similarity graph statistics"""
        try:
            await self._ensure_similarity_graph_exists()
            
            stats_query = f"""
            CALL gds.graph.list('{self.similarity_graph_name}')
            YIELD nodeCount, relationshipCount, memoryUsage
            RETURN nodeCount, relationshipCount, memoryUsage
            """
            
            result = await self.neo4j.execute_query(stats_query)
            if result:
                return {
                    "node_count": result[0]["nodeCount"],
                    "relationship_count": result[0]["relationshipCount"], 
                    "memory_usage": result[0]["memoryUsage"],
                    "graph_name": self.similarity_graph_name,
                    "edge_explosion_prevention": {
                        "max_level_difference": MAX_LEVEL_DIFFERENCE,
                        "min_similarity_weight": MIN_SIMILARITY_WEIGHT
                    }
                }
            else:
                return {"error": "No graph statistics available"}
                
        except Exception as e:
            logger.error(f"Failed to get similarity graph stats: {e}")
            return {"error": str(e)}