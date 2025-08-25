"""
Prerequisite Path Optimization for Cornell Course Navigator
Implements shortest path algorithms and semester planning optimization using Neo4j GDS
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# Input validation constants
MAX_ALTERNATIVES = 10
MAX_SEMESTERS = 20
MAX_CREDITS_PER_SEMESTER = 30
MAX_TARGET_COURSES = 50


@dataclass
class CoursePathStep:
    """Single step in a prerequisite path"""
    course_code: str
    course_title: str
    semester_position: int
    prerequisites_satisfied: List[str]
    is_corequisite: bool = False


@dataclass
class PrerequisitePath:
    """Complete prerequisite path to a target course"""
    target_course: str
    path_steps: List[CoursePathStep]
    total_semesters: int
    total_courses: int
    path_cost: float
    alternative_rank: int = 1


@dataclass
class SemesterPlan:
    """Course plan for a specific semester"""
    semester_number: int
    courses: List[str]
    course_titles: List[str]
    total_credits: int
    prerequisite_violations: List[str]


@dataclass
class OptimizedSchedule:
    """Optimized multi-semester course schedule"""
    semester_plans: List[SemesterPlan]
    total_semesters: int
    total_courses: int
    unscheduled_courses: List[str]
    optimization_metadata: Dict[str, any]


class PrerequisitePaths:
    """Prerequisite path finding and semester optimization using Neo4j GDS"""
    
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service
        self.graph_name = "prerequisite_graph"
        # Memoize graph existence checks to avoid redundant DB calls
        self._graph_exists_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes
        
        # Initialize cache attributes to prevent AttributeError under concurrency
        self._graph_cache = None
        self._course_info_cache = None
        
    def _validate_inputs(self, **kwargs) -> Dict[str, any]:
        """Validate and sanitize all inputs to prevent DoS attacks"""
        validated = {}
        
        # Validate num_alternatives
        if 'num_alternatives' in kwargs:
            validated['num_alternatives'] = max(1, min(kwargs['num_alternatives'], MAX_ALTERNATIVES))
        
        # Validate max_semesters
        if 'semesters_available' in kwargs:
            validated['semesters_available'] = max(1, min(kwargs['semesters_available'], MAX_SEMESTERS))
        
        # Validate max_credits_per_semester  
        if 'max_credits_per_semester' in kwargs:
            validated['max_credits_per_semester'] = max(1, min(kwargs['max_credits_per_semester'], MAX_CREDITS_PER_SEMESTER))
        
        # Validate target_courses list length
        if 'target_courses' in kwargs:
            target_courses = kwargs['target_courses']
            if isinstance(target_courses, list):
                validated['target_courses'] = target_courses[:MAX_TARGET_COURSES]
            else:
                validated['target_courses'] = []
        
        # Validate completed_courses list (remove duplicates, sanitize)
        if 'completed_courses' in kwargs:
            completed_courses = kwargs['completed_courses']
            if isinstance(completed_courses, list):
                # Remove duplicates and limit size
                validated['completed_courses'] = list(set(completed_courses))[:1000]
            else:
                validated['completed_courses'] = []
        
        return validated
    
    def _is_graph_cache_valid(self) -> bool:
        """Check if graph existence cache is still valid"""
        if self._cache_timestamp is None:
            return False
        current_time = time.time()
        return (current_time - self._cache_timestamp) < self._cache_ttl

    async def _ensure_prerequisite_graph_exists(self) -> None:
        """Ensure prerequisite graph exists in GDS catalog with memoization"""
        # Check memoized cache first
        if self._is_graph_cache_valid() and self._graph_exists_cache.get(self.graph_name):
            return
            
        try:
            # Check if graph exists
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
            logger.error(f"Failed to ensure prerequisite graph exists: {e}")
            # Clear cache on error to force recheck next time
            self._graph_exists_cache.pop(self.graph_name, None)
            raise
    
    async def _create_path_object(
        self,
        path_codes: List[str],
        target_course: str,
        total_cost: float,
        rank: int
    ) -> PrerequisitePath:
        """Create PrerequisitePath object from course codes"""
        
        # Get course information
        course_info_query = """
        MATCH (c:Course)
        WHERE c.code IN $path_codes
        RETURN c.code as code, c.title as title, c.credits as credits
        """
        
        course_results = await self.neo4j.execute_query(
            course_info_query,
            path_codes=path_codes
        )
        
        # Create lookup for course info
        course_info = {r["code"]: r for r in course_results}
        
        # Create path steps with basic semester assignment
        path_steps = []
        for i, course_code in enumerate(path_codes):
            info = course_info.get(course_code, {})
            
            path_steps.append(CoursePathStep(
                course_code=course_code,
                course_title=info.get("title", ""),
                semester_position=i + 1,  # Simple sequential assignment
                prerequisites_satisfied=[],
                is_corequisite=False
            ))
        
        return PrerequisitePath(
            target_course=target_course,
            path_steps=path_steps,
            total_semesters=len(path_steps),
            total_courses=len(path_steps),
            path_cost=total_cost,
            alternative_rank=rank
        )
        
    async def _build_prerequisite_graph_cypher(self) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
        """
        Build prerequisite relationship mappings using pure Cypher queries (no NetworkX)
        Returns: (predecessors_map, course_info_map)
        """
        if self._graph_cache is not None and self._course_info_cache is not None:
            logger.info("Using cached prerequisite graph data")
            return self._graph_cache, self._course_info_cache
            
        logger.info("Building prerequisite mappings from Neo4j using Cypher")
        start_time = time.time()
        
        # Query for all courses and their metadata
        course_query = """
        MATCH (c:Course)
        RETURN c.code as code, c.title as title, c.subject as subject, 
               c.catalog_nbr as level, c.description as description,
               c.credits as credits
        """
        
        # Query for prerequisite relationships - get predecessors for each course
        prereq_query = """
        MATCH (prereq:Course)-[r:REQUIRES]->(course:Course)
        WHERE r.type IN ['PREREQUISITE', 'PREREQUISITE_OR', 'COREQUISITE']
        RETURN course.code as course_code, 
               collect({
                   prereq: prereq.code, 
                   type: r.type, 
                   confidence: r.confidence
               }) as prerequisites
        """
        
        try:
            # Get courses
            course_results = await self.neo4j.execute_query(course_query)
            courses = {}
            for record in course_results:
                code = record["code"]
                credits = record.get("credits", 3)  # Default to 3 credits
                try:
                    credits = int(credits) if credits else 3
                except (ValueError, TypeError):
                    credits = 3
                    
                courses[code] = {
                    "title": record.get("title", ""),
                    "subject": record.get("subject", ""),
                    "level": int(record.get("level", 0)),
                    "credits": credits
                }
            
            # Get prerequisite relationships
            prereq_results = await self.neo4j.execute_query(prereq_query)
            
            # Build predecessor mapping: course -> set of prerequisite courses
            predecessors = {}
            for record in prereq_results:
                course_code = record["course_code"]
                prereqs = record["prerequisites"]
                
                predecessors[course_code] = set()
                for prereq_info in prereqs:
                    prereq_code = prereq_info["prereq"]
                    rel_type = prereq_info["type"]
                    
                    # Only include hard prerequisites for topological ordering
                    if rel_type in ["PREREQUISITE", "PREREQUISITE_OR"]:
                        predecessors[course_code].add(prereq_code)
            
            # Ensure all courses have an entry in predecessors map
            for course_code in courses:
                if course_code not in predecessors:
                    predecessors[course_code] = set()
                        
            build_time = time.time() - start_time
            logger.info(f"Built prerequisite mappings: {len(courses)} courses, {sum(len(p) for p in predecessors.values())} prerequisite relationships in {build_time:.2f}s")
            
            # Cache the results
            self._graph_cache = predecessors
            self._course_info_cache = courses
            
            return predecessors, courses
            
        except Exception as e:
            logger.error(f"Failed to build prerequisite mappings: {e}")
            raise
    
    async def shortest_path_to_course(
        self, 
        target_course: str, 
        completed_courses: List[str] = None
    ) -> PrerequisitePath:
        """
        Find shortest prerequisite path to target course using Neo4j GDS
        """
        if completed_courses is None:
            completed_courses = []
            
        logger.info(f"Finding shortest path to {target_course} with {len(completed_courses)} completed courses")
        start_time = time.time()
        
        try:
            # Use GDS shortest path directly (already implemented in find_alternative_paths)
            paths = await self.find_alternative_paths(target_course, completed_courses, 1)
            
            if not paths:
                # Check if target is already completed
                if target_course in completed_courses:
                    # Get course info
                    course_info_query = """
                    MATCH (c:Course {code: $course_code})
                    RETURN c.title as title
                    """
                    course_result = await self.neo4j.execute_query(course_info_query, course_code=target_course)
                    course_title = course_result[0]["title"] if course_result else ""
                    
                    return PrerequisitePath(
                        target_course=target_course,
                        path_steps=[CoursePathStep(
                            course_code=target_course,
                            course_title=course_title,
                            semester_position=0,
                            prerequisites_satisfied=[],
                            is_corequisite=False
                        )],
                        total_semesters=0,
                        total_courses=0,
                        path_cost=0.0
                    )
                else:
                    raise ValueError(f"No path found to {target_course}")
            
            calculation_time = time.time() - start_time
            logger.info(f"Shortest path calculation completed in {calculation_time:.2f}s")
            
            return paths[0]  # Return the shortest path
            
        except Exception as e:
            logger.error(f"Shortest path calculation failed: {e}")
            raise
    
    def _topological_sort_cypher(self, courses: Set[str], predecessors: Dict[str, Set[str]]) -> List[str]:
        """
        Perform topological sort using Kahn's algorithm (no NetworkX dependency)
        """
        from collections import deque
        
        # Filter predecessors to only include courses we're scheduling
        filtered_predecessors = {}
        in_degree = {}
        
        for course in courses:
            course_prereqs = predecessors.get(course, set())
            # Only count prerequisites that are also in our scheduling set
            relevant_prereqs = course_prereqs.intersection(courses)
            filtered_predecessors[course] = relevant_prereqs
            in_degree[course] = len(relevant_prereqs)
        
        # Kahn's algorithm for topological sorting
        queue = deque([course for course in courses if in_degree[course] == 0])
        topo_order = []
        
        while queue:
            current = queue.popleft()
            topo_order.append(current)
            
            # Update in-degrees for courses that depend on current
            for course in courses:
                if current in filtered_predecessors[course]:
                    in_degree[course] -= 1
                    if in_degree[course] == 0:
                        queue.append(course)
        
        # If we couldn't order all courses, there might be cycles
        if len(topo_order) != len(courses):
            logger.warning(f"Topological sort incomplete: {len(topo_order)}/{len(courses)} courses ordered")
            # Add remaining courses in arbitrary order
            remaining = courses - set(topo_order)
            topo_order.extend(remaining)
        
        return topo_order
    
    async def find_alternative_paths(
        self, 
        target_course: str, 
        completed_courses: List[str] = None,
        num_alternatives: int = 3
    ) -> List[PrerequisitePath]:
        """
        Find multiple alternative prerequisite paths using proper k-shortest paths algorithm
        """
        if completed_courses is None:
            completed_courses = []
            
        # Validate inputs
        validated = self._validate_inputs(
            num_alternatives=num_alternatives,
            completed_courses=completed_courses
        )
        num_alternatives = validated.get('num_alternatives', num_alternatives)
        completed_courses = validated.get('completed_courses', completed_courses)
        
        logger.info(f"Finding {num_alternatives} alternative paths to {target_course}")
        start_time = time.time()
        
        try:
            # Use Neo4j GDS for shortest path calculation
            await self._ensure_prerequisite_graph_exists()
            
            # Get course node IDs
            course_id_query = """
            MATCH (c:Course {code: $target_course})
            RETURN elementId(c) as target_id
            """
            
            target_result = await self.neo4j.execute_query(course_id_query, target_course=target_course)
            if not target_result:
                raise ValueError(f"Target course {target_course} not found")
            
            target_node_id = target_result[0]["target_id"]
            
            # Get completed course node IDs
            completed_node_ids = []
            if completed_courses:
                completed_query = """
                MATCH (c:Course)
                WHERE c.code IN $completed_courses
                RETURN elementId(c) as node_id, c.code as code
                """
                
                completed_result = await self.neo4j.execute_query(
                    completed_query, 
                    completed_courses=completed_courses
                )
                completed_node_ids = [r["node_id"] for r in completed_result]
            
            # If no completed courses, find courses with no prerequisites as starting points
            if not completed_node_ids:
                # Use random sampling to avoid bias toward specific departments
                no_prereq_query = f"""
                MATCH (c:Course)
                WHERE NOT (c)<-[:REQUIRES]-()
                WITH c, rand() as random_value
                ORDER BY random_value
                RETURN elementId(c) AS nodeId
                LIMIT 10
                """
                
                no_prereq_result = await self.neo4j.execute_query(no_prereq_query)
                completed_node_ids = [r["nodeId"] for r in no_prereq_result]
            
            # Use GDS k-shortest paths (Yen's algorithm implementation)
            alternative_paths = []
            
            for i, source_node_id in enumerate(completed_node_ids[:5]):  # Limit source nodes
                if i >= num_alternatives:
                    break
                    
                try:
                    # Calculate shortest path from this source
                    path_query = f"""
                    CALL gds.shortestPath.dijkstra.stream('{self.graph_name}', {{
                        sourceNode: $source_id,
                        targetNode: $target_id,
                        relationshipWeightProperty: 'weight'
                    }})
                    YIELD sourceNode, targetNode, totalCost, nodeIds, costs
                    
                    // Convert node IDs to course codes
                    UNWIND nodeIds as nodeId
                    MATCH (c:Course) WHERE elementId(c) = nodeId
                    RETURN collect(c.code) as path_codes, totalCost
                    """
                    
                    path_result = await self.neo4j.execute_query(
                        path_query,
                        source_id=source_node_id,
                        target_id=target_node_id
                    )
                    
                    if path_result and path_result[0]["path_codes"]:
                        path_codes = path_result[0]["path_codes"]
                        total_cost = path_result[0]["totalCost"]
                        
                        # Convert to PrerequisitePath object
                        path_obj = await self._create_path_object(
                            path_codes, 
                            target_course, 
                            total_cost, 
                            len(alternative_paths) + 1
                        )
                        alternative_paths.append(path_obj)
                        
                except Exception as e:
                    logger.warning(f"Failed to find path from source {source_node_id}: {e}")
                    continue
            
            # If we need more alternatives, use Yen's k-shortest paths
            if len(alternative_paths) < num_alternatives and completed_node_ids:
                try:
                    # Use the best source node for k-shortest paths
                    best_source = completed_node_ids[0] if completed_node_ids else None
                    
                    if best_source:
                        yen_query = f"""
                        CALL gds.shortestPath.yens.stream('{self.graph_name}', {{
                            sourceNode: $source_id,
                            targetNode: $target_id,
                            k: $k_paths,
                            relationshipWeightProperty: 'weight'
                        }})
                        YIELD sourceNode, targetNode, totalCost, nodeIds, path
                        
                        // Convert node IDs to course codes
                        UNWIND nodeIds as nodeId
                        MATCH (c:Course) WHERE elementId(c) = nodeId
                        WITH path, totalCost, collect(c.code) as path_codes
                        RETURN path_codes, totalCost
                        ORDER BY totalCost
                        """
                        
                        yen_result = await self.neo4j.execute_query(
                            yen_query,
                            source_id=best_source,
                            target_id=target_node_id,
                            k_paths=num_alternatives
                        )
                        
                        # Replace with Yen's results (proper k-shortest paths)
                        alternative_paths = []
                        for i, record in enumerate(yen_result[:num_alternatives], 1):
                            path_codes = record["path_codes"]
                            total_cost = record["totalCost"]
                            
                            path_obj = await self._create_path_object(
                                path_codes, 
                                target_course, 
                                total_cost, 
                                i
                            )
                            alternative_paths.append(path_obj)
                            
                except Exception as e:
                    logger.warning(f"Yen's k-shortest paths failed, using simple alternatives: {e}")
            
            calculation_time = time.time() - start_time
            logger.info(f"Alternative paths calculation completed in {calculation_time:.2f}s: "
                       f"{len(alternative_paths)} paths found")
            
            return alternative_paths
            
        except Exception as e:
            logger.error(f"Alternative paths calculation failed: {e}")
            raise
    
    
    async def optimize_semester_plan(
        self, 
        target_courses: List[str], 
        completed_courses: List[str] = None,
        semesters_available: int = 8,
        max_credits_per_semester: int = 18
    ) -> OptimizedSchedule:
        """
        Optimize course sequence across multiple semesters for multiple target courses
        """
        if completed_courses is None:
            completed_courses = []
            
        logger.info(f"Optimizing semester plan for {len(target_courses)} target courses "
                   f"across {semesters_available} semesters")
        start_time = time.time()
        
        try:
            predecessors, courses = await self._build_prerequisite_graph_cypher()
            
            # Collect all courses needed for all targets using Cypher queries
            all_needed_courses = set()
            
            for target in target_courses:
                if target not in courses:
                    logger.warning(f"Target course {target} not found in graph")
                    continue
                
                # Find all prerequisites for this target using Cypher
                try:
                    # Get all ancestor courses (prerequisites) recursively
                    ancestors_query = """
                    MATCH path = (prereq:Course)-[:REQUIRES*]->(target:Course {code: $target_code})
                    WHERE ALL(r in relationships(path) WHERE r.type IN ['PREREQUISITE', 'PREREQUISITE_OR'])
                    RETURN collect(DISTINCT prereq.code) as ancestors
                    """
                    
                    ancestors_result = await self.neo4j.execute_query(ancestors_query, target_code=target)
                    ancestors = ancestors_result[0]["ancestors"] if ancestors_result else []
                    
                    all_needed_courses.update(ancestors)
                    all_needed_courses.add(target)  # Include the target itself
                    
                except Exception as e:
                    logger.warning(f"Could not find prerequisites for {target}: {e}")
                    all_needed_courses.add(target)
            
            # Remove already completed courses
            completed_set = set(completed_courses)
            courses_to_schedule = all_needed_courses - completed_set
            
            if not courses_to_schedule:
                # All courses already completed
                return OptimizedSchedule(
                    semester_plans=[],
                    total_semesters=0,
                    total_courses=0,
                    unscheduled_courses=[],
                    optimization_metadata={
                        "optimization_time_seconds": time.time() - start_time,
                        "all_targets_completed": True
                    }
                )
            
            # Implement topological sorting using Kahn's algorithm (no NetworkX)
            topo_order = self._topological_sort_cypher(courses_to_schedule, predecessors)
            
            # Greedy semester assignment
            semester_plans = []
            scheduled_courses = set(completed_courses)
            unscheduled_courses = list(courses_to_schedule)
            
            for semester_num in range(1, semesters_available + 1):
                semester_courses = []
                semester_titles = []
                semester_credits = 0
                courses_added_this_iteration = []
                
                # Try to add courses that have all prerequisites satisfied
                for course_code in topo_order:
                    if course_code in scheduled_courses or course_code in courses_added_this_iteration:
                        continue
                    
                    # Check if all prerequisites are satisfied
                    prerequisites_satisfied = True
                    course_prereqs = predecessors.get(course_code, set())
                    
                    for prereq in course_prereqs:
                        if prereq not in scheduled_courses:
                            prerequisites_satisfied = False
                            break
                    
                    if prerequisites_satisfied:
                        course_info = courses.get(course_code, {})
                        course_credits = course_info.get('credits', 3)
                        
                        # Check credit limit
                        if semester_credits + course_credits <= max_credits_per_semester:
                            semester_courses.append(course_code)
                            semester_titles.append(course_info.get('title', ''))
                            semester_credits += course_credits
                            courses_added_this_iteration.append(course_code)
                            
                            if course_code in unscheduled_courses:
                                unscheduled_courses.remove(course_code)
                
                # Update scheduled courses
                scheduled_courses.update(courses_added_this_iteration)
                
                # Create semester plan
                if semester_courses:
                    semester_plans.append(SemesterPlan(
                        semester_number=semester_num,
                        courses=semester_courses,
                        course_titles=semester_titles,
                        total_credits=semester_credits,
                        prerequisite_violations=[]  # Would need more complex validation
                    ))
                
                # Stop if all courses are scheduled
                if not unscheduled_courses:
                    break
            
            optimization_time = time.time() - start_time
            
            metadata = {
                "target_courses": target_courses,
                "total_courses_needed": len(all_needed_courses),
                "courses_to_schedule": len(courses_to_schedule),
                "optimization_time_seconds": optimization_time,
                "semesters_used": len(semester_plans),
                "max_credits_per_semester": max_credits_per_semester,
                "scheduling_efficiency": 1.0 - (len(unscheduled_courses) / len(courses_to_schedule)) if courses_to_schedule else 1.0
            }
            
            logger.info(f"Semester optimization completed in {optimization_time:.2f}s: "
                       f"{len(semester_plans)} semesters, {len(unscheduled_courses)} unscheduled courses")
            
            return OptimizedSchedule(
                semester_plans=semester_plans,
                total_semesters=len(semester_plans),
                total_courses=sum(len(plan.courses) for plan in semester_plans),
                unscheduled_courses=unscheduled_courses,
                optimization_metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Semester optimization failed: {e}")
            raise
    
    def clear_cache(self):
        """Clear cached graph and course data"""
        # Clear memoized graph existence cache
        self._graph_exists_cache.clear()
        self._cache_timestamp = None
        
        # Clear graph data caches
        self._graph_cache = None
        self._course_info_cache = None
        logger.info("Pathfinding cache cleared")