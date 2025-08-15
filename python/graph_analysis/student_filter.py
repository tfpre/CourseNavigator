# Student-Centric Graph Filtering for Cornell Course Navigator
# Transforms global course graph into personalized academic pathways
# PRIORITY 1: "Cool toy" → "This will help ME graduate"

import logging
from typing import Dict, List, Set, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class StudentProfile:
    """Simplified student profile for graph filtering"""
    student_id: str
    major: str
    minor: Optional[str] = None
    completed_courses: List[str] = None
    current_courses: List[str] = None
    target_graduation: str = "Spring 2027"
    career_interests: List[str] = None
    
    def __post_init__(self):
        if self.completed_courses is None:
            self.completed_courses = []
        if self.current_courses is None:
            self.current_courses = []
        if self.career_interests is None:
            self.career_interests = []

@dataclass 
class StudentGraphMetrics:
    """Metrics for personalized graph analysis"""
    total_relevant_courses: int
    courses_completed: int
    courses_available_now: int
    courses_blocked_by_prereqs: int
    estimated_semesters_remaining: int
    
class StudentGraphFilter:
    """
    Filters global course graph to student-relevant subgraphs
    Implementation Strategy: Start with filter approach (~150 lines, fast)
    Future: Graduate to PersonalizedGraphService with materialized views
    """
    
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service
        
        # Major-specific course requirements (expandable)
        self.major_requirements = {
            "Computer Science": {
                "core_subjects": ["CS", "ENGRD"],
                "required_subjects": ["MATH", "PHYS"],
                "elective_subjects": ["ECE", "ORIE", "ENGRI"],
                "min_level": 1000,
                "focus_areas": ["programming", "algorithms", "systems", "theory"]
            },
            "Mathematics": {
                "core_subjects": ["MATH"],
                "required_subjects": ["PHYS", "CS"], 
                "elective_subjects": ["ENGRD", "ORIE"],
                "min_level": 1000,
                "focus_areas": ["analysis", "algebra", "statistics", "applied_math"]
            },
            "Electrical Engineering": {
                "core_subjects": ["ECE", "ENGRD"],
                "required_subjects": ["MATH", "PHYS", "CS"],
                "elective_subjects": ["ORIE", "ENGRI"],
                "min_level": 1000,
                "focus_areas": ["circuits", "signals", "systems", "embedded"]
            }
        }
        
    def filter_for_student(
        self, 
        student: StudentProfile,
        include_exploration: bool = True,
        max_courses: int = 150
    ) -> Dict[str, any]:
        """
        Filter global graph to student-relevant courses
        
        Args:
            student: Student profile with major, completed courses
            include_exploration: Include courses outside major for breadth
            max_courses: Limit on returned courses (performance)
            
        Returns:
            Dict with filtered courses, prerequisites, and personalization metadata
        """
        logger.info(f"Filtering graph for student {student.student_id} (major: {student.major})")
        
        # Get major requirements
        major_req = self.major_requirements.get(
            student.major, 
            self.major_requirements["Computer Science"]  # Default fallback
        )
        
        # Build relevance criteria
        relevant_subjects = (
            major_req["core_subjects"] + 
            major_req["required_subjects"] + 
            (major_req["elective_subjects"] if include_exploration else [])
        )
        
        completed_set = set(student.completed_courses)
        in_progress_set = set(student.current_courses)
        
        # Get filtered course set
        filtered_courses = self._get_relevant_courses(
            relevant_subjects, 
            major_req["min_level"],
            completed_set,
            in_progress_set,
            max_courses
        )
        
        # Calculate personalized metrics
        metrics = self._calculate_student_metrics(
            filtered_courses, 
            completed_set, 
            in_progress_set,
            student.major
        )
        
        # Get prerequisite relationships within filtered set
        filtered_prerequisites = self._get_filtered_prerequisites(
            [c["course_code"] for c in filtered_courses]
        )
        
        return {
            "courses": filtered_courses,
            "prerequisites": filtered_prerequisites,
            "student_metrics": metrics,
            "personalization": {
                "student_id": student.student_id,
                "major": student.major,
                "minor": student.minor,
                "filtering_criteria": {
                    "relevant_subjects": relevant_subjects,
                    "min_level": major_req["min_level"],
                    "include_exploration": include_exploration
                },
                "academic_progress": {
                    "completed_count": len(completed_set),
                    "in_progress_count": len(in_progress_set),
                    "available_count": metrics.courses_available_now,
                    "completion_percentage": metrics.courses_completed / max(metrics.total_relevant_courses, 1)
                }
            }
        }
    
    def _get_relevant_courses(
        self, 
        subjects: List[str], 
        min_level: int,
        completed: Set[str],
        in_progress: Set[str],
        max_courses: int
    ) -> List[Dict]:
        """Get courses relevant to student's major and academic progress"""
        
        # Build subject filter for Cypher
        subject_filter = " OR ".join([f"c.subject = '{subj}'" for subj in subjects])
        
        query = f"""
        MATCH (c:Course)
        WHERE ({subject_filter})
        AND c.catalog_nbr >= $min_level
        
        // Calculate course status relative to student  
        WITH c,
             CASE 
                WHEN c.code IN $completed THEN 'completed'
                WHEN c.code IN $in_progress THEN 'in_progress'
                ELSE 'available'
             END AS status,
             
             // Calculate prerequisite satisfaction
             [p IN [(c)<-[:REQUIRES]-(prereq) | prereq.code] WHERE p IN $completed] AS satisfied_prereqs,
             [(c)<-[:REQUIRES]-(prereq) | prereq.code] AS all_prereqs
        
        WITH c, status, satisfied_prereqs, all_prereqs,
             CASE 
                WHEN size(all_prereqs) = 0 THEN true
                WHEN size(satisfied_prereqs) = size(all_prereqs) THEN true
                ELSE false
             END AS prereqs_satisfied
        
        // Priority scoring: available and prereq-satisfied courses ranked highest
        WITH c, status, prereqs_satisfied, satisfied_prereqs, all_prereqs,
             CASE
                WHEN status = 'completed' THEN 0
                WHEN status = 'in_progress' THEN 1  
                WHEN prereqs_satisfied THEN 3
                ELSE 2
             END AS priority_score
        
        RETURN 
            c.code AS course_code,
            c.title AS course_title, 
            c.subject AS subject,
            c.catalog_nbr AS level,
            status,
            prereqs_satisfied,
            satisfied_prereqs,
            all_prereqs,
            priority_score
        
        ORDER BY priority_score DESC, c.catalog_nbr ASC
        LIMIT $max_courses
        """
        
        try:
            result = self.neo4j.execute_query(
                query,
                min_level=min_level,
                completed=list(completed),
                in_progress=list(in_progress),
                max_courses=max_courses
            )
            
            courses = []
            for record in result:
                courses.append({
                    "course_code": record["course_code"],
                    "course_title": record["course_title"] or "",
                    "subject": record["subject"],
                    "level": int(record["level"]),
                    "status": record["status"],
                    "prereqs_satisfied": record["prereqs_satisfied"],
                    "satisfied_prereqs": record["satisfied_prereqs"] or [],
                    "all_prereqs": record["all_prereqs"] or [],
                    "priority_score": record["priority_score"]
                })
            
            logger.info(f"Found {len(courses)} relevant courses for student")
            return courses
            
        except Exception as e:
            logger.error(f"Failed to get relevant courses: {e}")
            return []
    
    def _get_filtered_prerequisites(self, course_codes: List[str]) -> List[Dict]:
        """Get prerequisite relationships within the filtered course set"""
        
        if not course_codes:
            return []
            
        query = """
        MATCH (from:Course)-[r:REQUIRES]->(to:Course)
        WHERE from.code IN $course_codes AND to.code IN $course_codes
        RETURN 
            from.code AS from_course,
            to.code AS to_course,
            type(r) AS relationship_type
        ORDER BY from_course, to_course
        """
        
        try:
            result = self.neo4j.execute_query(query, course_codes=course_codes)
            
            prerequisites = []
            for record in result:
                prerequisites.append({
                    "from_course": record["from_course"], 
                    "to_course": record["to_course"],
                    "relationship_type": record["relationship_type"]
                })
            
            logger.info(f"Found {len(prerequisites)} prerequisite relationships in filtered graph")
            return prerequisites
            
        except Exception as e:
            logger.error(f"Failed to get filtered prerequisites: {e}")
            return []
    
    def _calculate_student_metrics(
        self, 
        courses: List[Dict], 
        completed: Set[str],
        in_progress: Set[str],
        major: str
    ) -> StudentGraphMetrics:
        """Calculate personalized metrics for student progress"""
        
        total_relevant = len(courses)
        courses_completed = len([c for c in courses if c["status"] == "completed"])
        courses_in_progress = len([c for c in courses if c["status"] == "in_progress"])
        courses_available = len([c for c in courses if c["status"] == "available" and c["prereqs_satisfied"]])
        courses_blocked = len([c for c in courses if c["status"] == "available" and not c["prereqs_satisfied"]])
        
        # Estimate remaining semesters (rough heuristic)
        remaining_courses = total_relevant - courses_completed - courses_in_progress
        typical_load = 4  # courses per semester
        estimated_semesters = max(1, (remaining_courses + typical_load - 1) // typical_load)
        
        return StudentGraphMetrics(
            total_relevant_courses=total_relevant,
            courses_completed=courses_completed, 
            courses_available_now=courses_available,
            courses_blocked_by_prereqs=courses_blocked,
            estimated_semesters_remaining=estimated_semesters
        )
    
    def get_next_semester_recommendations(
        self, 
        student: StudentProfile, 
        semester_credit_limit: int = 16
    ) -> List[Dict]:
        """
        Get personalized course recommendations for next semester
        Prioritizes: 1) Available prereq-satisfied courses, 2) Core major requirements
        """
        
        filtered_data = self.filter_for_student(student, max_courses=100)
        courses = filtered_data["courses"]
        
        # Filter to available courses with satisfied prerequisites
        available_courses = [
            c for c in courses 
            if c["status"] == "available" and c["prereqs_satisfied"]
        ]
        
        # Sort by priority (core subjects first, then by level)
        major_req = self.major_requirements.get(student.major, {})
        core_subjects = set(major_req.get("core_subjects", ["CS"]))
        
        def recommendation_priority(course):
            score = 0
            # Core subjects get highest priority
            if course["subject"] in core_subjects:
                score += 100
            # Lower-level courses preferred (build foundation first)  
            score += (5000 - course["level"]) / 100
            # Courses with fewer unsatisfied prereqs preferred
            score += (10 - len(course["all_prereqs"])) * 5
            return score
        
        available_courses.sort(key=recommendation_priority, reverse=True)
        
        # Select courses within credit limit (assuming 4 credits each)
        recommended_courses = []
        total_credits = 0
        avg_credits_per_course = 4
        
        for course in available_courses:
            if total_credits + avg_credits_per_course <= semester_credit_limit:
                recommended_courses.append({
                    **course,
                    "recommendation_reason": self._get_recommendation_reason(course, student.major),
                    "estimated_credits": avg_credits_per_course
                })
                total_credits += avg_credits_per_course
            
            if len(recommended_courses) >= 6:  # Reasonable maximum
                break
        
        logger.info(f"Generated {len(recommended_courses)} personalized recommendations for {student.student_id}")
        return recommended_courses
    
    def _get_recommendation_reason(self, course: Dict, major: str) -> str:
        """Generate human-readable recommendation reasoning"""
        
        major_req = self.major_requirements.get(major, {})
        core_subjects = major_req.get("core_subjects", [])
        
        if course["subject"] in core_subjects:
            return f"Core {major} requirement - builds foundation for advanced courses"
        elif course["level"] < 2000:
            return "Introductory course - good preparation for upper-level classes"
        elif len(course["all_prereqs"]) == 0:
            return "No prerequisites required - can take immediately"
        else:
            return f"Next logical step - builds on {', '.join(course['satisfied_prereqs'][:2])}"

# Mock student profiles for demo/testing
DEMO_STUDENTS = {
    "alice_cs": StudentProfile(
        student_id="alice_cs",
        major="Computer Science",
        completed_courses=["CS 1110", "MATH 1910", "PHYS 2213"],
        current_courses=["CS 2110", "MATH 2930"],
        career_interests=["software_engineering", "machine_learning"]
    ),
    "bob_math": StudentProfile(
        student_id="bob_math", 
        major="Mathematics",
        completed_courses=["MATH 1910", "MATH 1920", "CS 1110"],
        current_courses=["MATH 2940", "CS 2110"],
        career_interests=["data_science", "research"]
    ),
    "charlie_ece": StudentProfile(
        student_id="charlie_ece",
        major="Electrical Engineering", 
        completed_courses=["MATH 1910", "PHYS 2213", "ENGRD 2100"],
        current_courses=["ECE 3140", "MATH 2930"],
        career_interests=["embedded_systems", "robotics"]
    )
}