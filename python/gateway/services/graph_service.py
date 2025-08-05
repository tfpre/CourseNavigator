"""
Graph service for Neo4j integration
Handles prerequisite relationships and graph queries
"""

import logging
from typing import List, Dict, Any, Optional, Set
import asyncio

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
except ImportError:
    # Graceful fallback if neo4j not available
    AsyncGraphDatabase = None
    AsyncDriver = None
    AsyncSession = None

from ..models import (
    CourseInfo, PrerequisiteEdge, GraphContext, 
    PrerequisitePathRequest, PrerequisitePathResponse
)

logger = logging.getLogger(__name__)

class GraphService:
    """Service for graph queries using Neo4j"""
    
    def __init__(self, uri: str, username: str, password: str):
        self.uri = uri
        self.username = username
        self.password = password
        self.driver: Optional[AsyncDriver] = None
        
        # Check for mock mode via environment variable first
        import os
        use_mock_services = os.getenv("USE_MOCK_SERVICES", "false").lower() == "true"
        
        if use_mock_services:
            logger.warning("Mock mode enabled via USE_MOCK_SERVICES environment variable")
            self._mock_mode = True
        elif AsyncGraphDatabase is None:
            logger.warning("neo4j driver not available, graph queries will be mocked")
            self._mock_mode = True
        else:
            self._mock_mode = False
    
    def enable_mock_mode(self):
        """Enable mock mode (useful when health checks fail)"""
        logger.warning("Enabling mock mode due to service unavailability")
        self._mock_mode = True
    
    async def _get_driver(self) -> AsyncDriver:
        """Get or create async Neo4j driver"""
        if self._mock_mode:
            raise RuntimeError("Neo4j driver not available")
            
        if self.driver is None:
            self.driver = AsyncGraphDatabase.driver(
                self.uri, 
                auth=(self.username, self.password)
            )
        return self.driver
    
    async def health_check(self) -> bool:
        """Check if Neo4j service is healthy"""
        if self._mock_mode:
            logger.info("Graph service in mock mode")
            return True
            
        try:
            driver = await self._get_driver()
            
            async with driver.session() as session:
                result = await session.run("RETURN 1 as test")
                record = await result.single()
                
                if record and record["test"] == 1:
                    logger.info("Neo4j health check passed")
                    return True
                else:
                    raise RuntimeError("Neo4j health check failed")
                    
        except Exception as e:
            logger.error(f"Neo4j health check failed: {e}")
            raise
    
    async def get_graph_context(
        self, 
        course_ids: List[str], 
        max_depth: int = 2
    ) -> GraphContext:
        """
        Get graph context for a set of courses
        
        Args:
            course_ids: List of course IDs to expand
            max_depth: Maximum depth for relationship expansion
            
        Returns:
            GraphContext with nodes and edges
        """
        if self._mock_mode:
            return await self._mock_graph_context(course_ids, max_depth)
            
        try:
            driver = await self._get_driver()
            
            async with driver.session() as session:
                # Query to get expanded graph context
                query = """
                MATCH (c:Course) 
                WHERE c.id IN $course_ids
                
                // Get direct prerequisites and dependents
                OPTIONAL MATCH (c)-[r1:REQUIRES]->(prereq:Course)
                OPTIONAL MATCH (dependent:Course)-[r2:REQUIRES]->(c)
                
                // Get course aliases
                OPTIONAL MATCH (c)-[:HAS_ALIAS]->(alias:Alias)
                
                RETURN 
                    c as course,
                    collect(DISTINCT prereq) as prerequisites,
                    collect(DISTINCT dependent) as dependents,
                    collect(DISTINCT r1) as prereq_edges,
                    collect(DISTINCT r2) as dependent_edges,
                    collect(DISTINCT alias) as aliases
                """
                
                result = await session.run(query, course_ids=course_ids)
                
                nodes = []
                edges = []
                node_ids_seen = set()
                
                async for record in result:
                    # Process main course
                    course = record["course"]
                    if course and course["id"] not in node_ids_seen:
                        nodes.append(self._neo4j_node_to_course_info(course))
                        node_ids_seen.add(course["id"])
                    
                    # Process prerequisites
                    for prereq in record["prerequisites"]:
                        if prereq and prereq["id"] not in node_ids_seen:
                            nodes.append(self._neo4j_node_to_course_info(prereq))
                            node_ids_seen.add(prereq["id"])
                    
                    # Process dependents
                    for dependent in record["dependents"]:
                        if dependent and dependent["id"] not in node_ids_seen:
                            nodes.append(self._neo4j_node_to_course_info(dependent))
                            node_ids_seen.add(dependent["id"])
                    
                    # Process prerequisite edges
                    for edge in record["prereq_edges"]:
                        if edge:
                            edges.append(self._neo4j_edge_to_prereq_edge(edge))
                    
                    # Process dependent edges  
                    for edge in record["dependent_edges"]:
                        if edge:
                            edges.append(self._neo4j_edge_to_prereq_edge(edge))
                
                logger.info(f"Graph context: {len(nodes)} nodes, {len(edges)} edges")
                
                return GraphContext(
                    nodes=nodes,
                    edges=edges
                )
                
        except Exception as e:
            logger.error(f"Graph context query failed: {e}")
            raise
    
    async def get_prerequisite_path(
        self, 
        request: PrerequisitePathRequest
    ) -> PrerequisitePathResponse:
        """
        Get full prerequisite path for a specific course
        
        Args:
            request: Prerequisite path request
            
        Returns:
            PrerequisitePathResponse with full dependency chain
        """
        if self._mock_mode:
            return await self._mock_prerequisite_path(request)
            
        try:
            driver = await self._get_driver()
            
            async with driver.session() as session:
                # Get the target course
                course_query = """
                MATCH (c:Course {id: $course_id})
                RETURN c
                """
                
                course_result = await session.run(course_query, course_id=request.course_id)
                course_record = await course_result.single()
                
                if not course_record:
                    return PrerequisitePathResponse(
                        success=False,
                        error={
                            "code": "COURSE_NOT_FOUND",
                            "message": f"Course {request.course_id} not found"
                        }
                    )
                
                target_course = self._neo4j_node_to_course_info(course_record["c"])
                
                # Get prerequisite path using optimized recursive query
                path_query = """
                MATCH path = (c:Course {id: $course_id})-[:REQUIRES*0..5]->(prereq:Course)
                WHERE length(path) <= $max_depth
                UNWIND nodes(path) as course_node
                UNWIND relationships(path) as prereq_edge
                RETURN collect(DISTINCT course_node) as all_nodes, collect(DISTINCT prereq_edge) as all_edges
                """
                
                path_result = await session.run(
                    path_query, 
                    course_id=request.course_id,
                    max_depth=request.max_depth
                )
                
                path_record = await path_result.single()
                
                if path_record:
                    nodes = []
                    edges = []
                    node_ids_seen = set()
                    
                    # Process nodes
                    for node in path_record["all_nodes"] or []:
                        if node and node["id"] not in node_ids_seen:
                            nodes.append(self._neo4j_node_to_course_info(node))
                            node_ids_seen.add(node["id"])
                    
                    # Process edges
                    for edge in path_record["all_edges"] or []:
                        if edge:
                            edges.append(self._neo4j_edge_to_prereq_edge(edge))
                    
                    prerequisite_path = GraphContext(nodes=nodes, edges=edges)
                else:
                    prerequisite_path = GraphContext(nodes=[target_course], edges=[])
                
                return PrerequisitePathResponse(
                    success=True,
                    course=target_course,
                    prerequisite_path=prerequisite_path,
                    missing_prerequisites=[],
                    recommendations=[],
                    path_metadata={"depth": request.max_depth}
                )
                
        except Exception as e:
            logger.error(f"Prerequisite path query failed: {e}")
            return PrerequisitePathResponse(
                success=False,
                error={
                    "code": "PREREQ_PATH_ERROR",
                    "message": str(e)
                }
            )
    
    def _neo4j_node_to_course_info(self, node) -> CourseInfo:
        """Convert Neo4j node to CourseInfo"""
        return CourseInfo(
            id=node.get("id", ""),
            subject=node.get("subject", ""),
            catalog_nbr=node.get("catalog_nbr", ""),
            title=node.get("title", ""),
            description=node.get("description"),
            credits=node.get("credits")
        )
    
    def _neo4j_edge_to_prereq_edge(self, edge) -> PrerequisiteEdge:
        """Convert Neo4j relationship to PrerequisiteEdge"""
        return PrerequisiteEdge(
            from_course_id=edge.start_node["id"],
            to_course_id=edge.end_node["id"],
            type=edge["type"] if "type" in edge else "REQUIRES",
            confidence=float(edge["confidence"] if "confidence" in edge else 1.0)
        )
    
    async def _mock_graph_context(
        self, 
        course_ids: List[str], 
        max_depth: int
    ) -> GraphContext:
        """Mock graph context for development"""
        logger.info(f"Mock graph context for {len(course_ids)} courses")
        
        # Create some mock relationships
        nodes = [
            CourseInfo(
                id="FA14-CS-4780-1",
                subject="CS",
                catalog_nbr="4780", 
                title="Machine Learning for Intelligent Systems"
            ),
            CourseInfo(
                id="FA14-CS-2110-1",
                subject="CS",
                catalog_nbr="2110",
                title="Object-Oriented Programming and Data Structures"
            ),
            CourseInfo(
                id="FA14-CS-2800-1",
                subject="CS", 
                catalog_nbr="2800",
                title="Discrete Structures"
            )
        ]
        
        edges = [
            PrerequisiteEdge(
                from_course_id="FA14-CS-4780-1",
                to_course_id="FA14-CS-2110-1",
                type="PREREQUISITE_OR",
                confidence=0.9
            ),
            PrerequisiteEdge(
                from_course_id="FA14-CS-4780-1", 
                to_course_id="FA14-CS-2800-1",
                type="PREREQUISITE_OR",
                confidence=0.85
            )
        ]
        
        return GraphContext(nodes=nodes, edges=edges)
    
    async def _mock_prerequisite_path(
        self, 
        request: PrerequisitePathRequest
    ) -> PrerequisitePathResponse:
        """Mock prerequisite path for development"""
        logger.info(f"Mock prerequisite path for {request.course_id}")
        
        target_course = CourseInfo(
            id=request.course_id,
            subject="CS",
            catalog_nbr="4780",
            title="Machine Learning for Intelligent Systems"
        )
        
        context = await self._mock_graph_context([request.course_id], request.max_depth)
        
        return PrerequisitePathResponse(
            success=True,
            course=target_course,
            prerequisite_path=context,
            missing_prerequisites=[],
            recommendations=[],
            path_metadata={"depth": request.max_depth, "mock": True}
        )
    
    async def _mock_query_response(self, query: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate mock response for graph queries"""
        import re
        
        # Mock data for common query patterns
        if "gds.graph.exists" in query:
            return [{"exists": True}]
        elif "pageRank" in query or "PAGERANK" in query:
            return [
                {"course_code": "CS 2110", "score": 0.95, "title": "Object-Oriented Programming", "subject": "CS", "level": 2110},
                {"course_code": "MATH 1920", "score": 0.89, "title": "Multivariable Calculus", "subject": "MATH", "level": 1920},
                {"course_code": "CS 3110", "score": 0.85, "title": "Data Structures & Functional Programming", "subject": "CS", "level": 3110},
                {"course_code": "CS 2800", "score": 0.82, "title": "Discrete Structures", "subject": "CS", "level": 2800},
                {"course_code": "PHYS 2213", "score": 0.78, "title": "Physics II", "subject": "PHYS", "level": 2213}
            ]
        elif "betweenness" in query or "BETWEENNESS" in query:
            return [
                {"course_code": "CS 2800", "score": 0.45, "title": "Discrete Structures", "subject": "CS", "level": 2800},
                {"course_code": "PHYS 2213", "score": 0.38, "title": "Physics II", "subject": "PHYS", "level": 2213},
                {"course_code": "ENGRD 2700", "score": 0.32, "title": "Basic Engineering Probability", "subject": "ENGRD", "level": 2700},
                {"course_code": "MATH 1920", "score": 0.28, "title": "Multivariable Calculus", "subject": "MATH", "level": 1920}
            ]
        elif "in_degree" in query or "indegree" in query:
            return [
                {"course_code": "CS 4780", "in_degree": 8, "rank": 1, "subject": "CS", "level": 4000, "title": "Machine Learning"},
                {"course_code": "CS 4410", "in_degree": 6, "rank": 2, "subject": "CS", "level": 4000, "title": "Operating Systems"},
                {"course_code": "CS 4820", "in_degree": 5, "rank": 3, "subject": "CS", "level": 4000, "title": "Introduction to Algorithms"}
            ]
        elif "louvain" in query or "LOUVAIN" in query:
            # Fixed community detection mock response with correct field names
            return [
                {"course_codes": ["CS 2110", "CS 3110", "CS 4780"], "community_id": 0, "modularity": 0.45},
                {"course_codes": ["MATH 1920", "MATH 2940", "ENGRD 2700"], "community_id": 1, "modularity": 0.38},
                {"course_codes": ["PHYS 2213", "PHYS 2214", "CHEM 2090"], "community_id": 2, "modularity": 0.31}
            ]
        elif "MATCH (from:Course)-[r:REQUIRES]" in query:
            # Fixed prerequisite relationship mock response with correct field names
            return [
                {"from_course": "CS 4780", "to_course": "CS 2110", "relationship_type": "PREREQUISITE", 
                 "from_title": "Machine Learning", "from_subject": "CS", "from_level": 4780,
                 "to_title": "Object-Oriented Programming", "to_subject": "CS", "to_level": 2110},
                {"from_course": "CS 4780", "to_course": "MATH 1920", "relationship_type": "PREREQUISITE_OR",
                 "from_title": "Machine Learning", "from_subject": "CS", "from_level": 4780,
                 "to_title": "Multivariable Calculus", "to_subject": "MATH", "to_level": 1920},
                {"from_course": "CS 3110", "to_course": "CS 2110", "relationship_type": "PREREQUISITE",
                 "from_title": "Data Structures & Functional Programming", "from_subject": "CS", "from_level": 3110,
                 "to_title": "Object-Oriented Programming", "to_subject": "CS", "to_level": 2110},
                {"from_course": "CS 4410", "to_course": "CS 2800", "relationship_type": "PREREQUISITE",
                 "from_title": "Operating Systems", "from_subject": "CS", "from_level": 4410,
                 "to_title": "Discrete Structures", "to_subject": "CS", "to_level": 2800},
                {"from_course": "CS 4820", "to_course": "CS 2800", "relationship_type": "PREREQUISITE",
                 "from_title": "Introduction to Algorithms", "from_subject": "CS", "from_level": 4820,
                 "to_title": "Discrete Structures", "to_subject": "CS", "to_level": 2800}
            ]
        elif "gds.graph.project" in query:
            return [{"nodeProjection": "Course", "relationshipProjection": "REQUIRES", "graphName": "prerequisite_graph"}]
        elif "gds.graph.list" in query:
            return [{"graphName": "prerequisite_graph", "nodeCount": 240, "relationshipCount": 154}]
        else:
            # Default mock response for unknown queries
            return [{"mock": True, "query_type": "unknown", "parameters": parameters}]
    
    async def execute_query(self, query: str, **parameters) -> List[Dict[str, Any]]:
        """Execute a raw Cypher query and return results"""
        logger.info(f"execute_query called: mock_mode={self._mock_mode}, query={query[:50]}...")
        if self._mock_mode:
            logger.info("Using mock query response")
            return await self._mock_query_response(query, parameters)
            
        try:
            driver = await self._get_driver()
            async with driver.session() as session:
                result = await session.run(query, parameters)
                records = await result.data()
                return records
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    async def close(self):
        """Close the driver connection"""
        if self.driver:
            await self.driver.close()
            self.driver = None