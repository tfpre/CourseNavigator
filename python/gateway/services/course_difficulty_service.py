# Course Difficulty Service - Cornell Grade Distribution Analysis
# REAL DATA IMPLEMENTATION - Serves Information Consolidation ground truth

import asyncio
import logging
import json
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

class CourseDifficultyService:
    """
    Course Difficulty Service with REAL Cornell grade data.
    
    Serves Information Consolidation ground truth with actual Cornell grade distributions.
    Provides structured difficulty analysis optimized for LLM context.
    
    Architecture: CSV → Redis cache → structured response format
    """
    
    def __init__(self, redis_client=None, data_file: str = None):
        self.redis_client = redis_client
        
        # Default to Cornell grades CSV in data directory
        if data_file is None:
            project_root = Path(__file__).parent.parent.parent.parent
            data_file = project_root / "data" / "cornell_grades.csv"
        
        self.data_file = Path(data_file)
        self.grades_data = None
        self.CACHE_TTL_SECONDS = 24 * 3600  # 24 hours
        
        self._load_grades_data()
        
    def _load_grades_data(self):
        """Load real Cornell grades data from CSV file"""
        try:
            if self.data_file.exists():
                self.grades_data = pd.read_csv(self.data_file)
                logger.info(f"Loaded {len(self.grades_data)} course grade records from {self.data_file}")
            else:
                logger.warning(f"Grades data file not found: {self.data_file}")
                self.grades_data = pd.DataFrame()  # Empty dataframe for graceful degradation
        except Exception as e:
            logger.error(f"Failed to load grades data: {e}")
            self.grades_data = pd.DataFrame()
    
    async def get_course_difficulty(self, course_code: str) -> Dict[str, Any]:
        """
        Get comprehensive course difficulty analysis using REAL Cornell grade data.
        
        Serves Information Consolidation ground truth by providing actual difficulty metrics.
        
        Args:
            course_code: Course code (e.g., "CS 3110", "MATH 1920")
            
        Returns:
            Dict with difficulty metrics, grade distribution, and prompt-ready summary
        """
        # Normalize course code (handle different formats)
        course_code = course_code.replace("-", " ").strip().upper()
        
        # PERFORMANCE CRITICAL: Cache grade analysis since calculations are expensive
        cache_key = f"grades:v1:{hashlib.sha1(course_code.encode()).hexdigest()[:12]}"
        
        # Try cache first
        if self.redis_client:
            try:
                cached = await self.redis_client.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    logger.debug(f"Cache hit for course difficulty: {course_code}")
                    return data
            except Exception as e:
                logger.warning(f"Redis cache read failed for grades: {e}")
        
        # Query the grades data
        difficulty_data = self._calculate_difficulty_metrics(course_code)
        
        if not difficulty_data:
            logger.debug(f"No grade data found for course: {course_code}")
            # Return structured fallback data
            return self._generate_fallback_data(course_code)
        
        # Cache successful result for 24 hours (grades change seasonally, not daily)
        if self.redis_client and difficulty_data:
            try:
                await self.redis_client.setex(
                    cache_key,
                    self.CACHE_TTL_SECONDS,
                    json.dumps(difficulty_data)
                )
                logger.debug(f"Cached difficulty data for {course_code}")
            except Exception as e:
                logger.warning(f"Redis cache write failed for grades: {e}")
        
        return difficulty_data
    
    def _calculate_difficulty_metrics(self, course_code: str) -> Optional[Dict[str, Any]]:
        """Calculate comprehensive difficulty metrics from real Cornell grade data"""
        if self.grades_data.empty:
            return None
            
        # Find matching course (case-insensitive)
        course_rows = self.grades_data[
            self.grades_data['course_id'].str.upper() == course_code.upper()
        ]
        
        if course_rows.empty:
            return None
        
        # Use most recent term data (assuming sorted by term)
        course_data = course_rows.iloc[-1]
        
        # Calculate derived metrics
        mean_gpa = float(course_data['mean_gpa'])
        a_rate = float(course_data['grade_a_pct'])
        b_rate = float(course_data['grade_b_pct'])
        c_rate = float(course_data['grade_c_pct'])
        failure_rate = float(course_data['grade_d_pct'] + course_data['grade_f_pct'])
        enrollment = int(course_data['enrollment_count'])
        difficulty_percentile = int(course_data['difficulty_percentile'])
        
        # Classify difficulty level
        if difficulty_percentile >= 80:
            difficulty_level = "Very Hard"
        elif difficulty_percentile >= 65:
            difficulty_level = "Hard" 
        elif difficulty_percentile >= 35:
            difficulty_level = "Moderate"
        else:
            difficulty_level = "Easy"
        
        # Create workload estimate based on difficulty and course type
        if course_code.startswith('CS') and difficulty_percentile > 70:
            workload_estimate = "Heavy programming workload"
        elif course_code.startswith('MATH') and difficulty_percentile > 75:
            workload_estimate = "Intensive problem sets"
        elif difficulty_percentile > 80:
            workload_estimate = "High time commitment"
        elif difficulty_percentile < 50:
            workload_estimate = "Manageable workload"
        else:
            workload_estimate = "Standard workload"
        
        # Create structured response matching expected format
        difficulty_analysis = {
            "course_code": course_code,
            "mean_gpa": mean_gpa,
            "std_dev": 0.8,  # Simplified for now
            "relative_rank": difficulty_percentile / 100.0,
            "difficulty_category": difficulty_level.lower().replace(" ", "_"),
            "data_source": "cornell_grade_distributions",
            "last_updated": course_data['updated_at'],
            
            # Extended metrics for comprehensive analysis
            "difficulty_metrics": {
                "mean_gpa": mean_gpa,
                "grade_a_percentage": a_rate,
                "grade_b_percentage": b_rate,
                "grade_c_percentage": c_rate,
                "failure_rate": failure_rate,
                "difficulty_percentile": difficulty_percentile,
                "difficulty_level": difficulty_level,
                "enrollment_size": enrollment
            },
            
            # Analysis summaries
            "analysis": {
                "gpa_context": self._gpa_context(mean_gpa),
                "grade_distribution": f"Grade-friendly: {a_rate:.0f}% A's, {b_rate:.0f}% B's" if a_rate >= 50 else f"Tough grading: only {a_rate:.0f}% A's, {b_rate:.0f}% B's",
                "workload_estimate": workload_estimate,
                "relative_difficulty": self._relative_difficulty_description(difficulty_percentile)
            },
            
            # Optimized for LLM prompt context
            "prompt_summary": self._generate_prompt_summary(course_code, mean_gpa, a_rate, difficulty_level, workload_estimate),
            "cache_hit": False  # Always False for fresh calculations
        }
        
        return difficulty_analysis
    
    def _gpa_context(self, mean_gpa: float) -> str:
        """Provide context for GPA relative to Cornell averages"""
        if mean_gpa >= 3.5:
            return "Above average GPA for Cornell courses"
        elif mean_gpa >= 3.2:
            return "Average GPA for Cornell courses"
        elif mean_gpa >= 2.8:
            return "Below average GPA - challenging course"
        else:
            return "Significantly challenging course with low average GPA"
    
    def _relative_difficulty_description(self, difficulty_percentile: int) -> str:
        """Describe difficulty relative to other Cornell courses"""
        if difficulty_percentile >= 90:
            return "Among the most challenging Cornell courses"
        elif difficulty_percentile >= 80:
            return "Significantly more difficult than typical Cornell courses"
        elif difficulty_percentile >= 65:
            return "More challenging than average Cornell courses"
        elif difficulty_percentile >= 35:
            return "Average difficulty for Cornell courses"
        else:
            return "Less challenging than typical Cornell courses"
    
    def _generate_prompt_summary(self, course_code: str, mean_gpa: float, a_rate: float, difficulty_level: str, workload: str) -> str:
        """
        Generate concise summary optimized for LLM prompts.
        
        Following ground truth: Actionable Prioritization - provide clear guidance.
        """
        return f"{course_code}: {difficulty_level.lower()} course (avg GPA {mean_gpa:.2f}, {a_rate:.0f}% A's). {workload}. Plan accordingly for time management."
    
    def _generate_fallback_data(self, course_code: str) -> Dict[str, Any]:
        """Generate fallback data for courses not in our dataset"""
        # Use heuristics based on course code patterns
        course_upper = course_code.upper()
        
        # Extract course level (1000, 2000, etc.)
        import re
        level_match = re.search(r'(\d)(\d{3})', course_code)
        level = int(level_match.group(1)) if level_match else 3
        
        # Subject-based difficulty patterns
        if any(subj in course_upper for subj in ["CS", "ECE", "ENGRD"]):
            base_gpa = 3.0 if level >= 3 else 3.2
            base_rank = 0.75 + (level - 1) * 0.05
            category = "very_hard" if level >= 4 else "hard"
        elif any(subj in course_upper for subj in ["MATH", "PHYS", "CHEM"]):
            base_gpa = 2.9 if level >= 3 else 3.1
            base_rank = 0.70 + (level - 1) * 0.08
            category = "very_hard" if level >= 3 else "hard"
        else:
            base_gpa = 3.4
            base_rank = 0.45 + (level - 1) * 0.05
            category = "moderate" if level >= 3 else "easy"
        
        return {
            "course_code": course_code,
            "mean_gpa": round(base_gpa, 2),
            "std_dev": 0.8,
            "relative_rank": min(0.95, base_rank),
            "difficulty_category": category,
            "data_source": "heuristic_fallback",
            "last_updated": datetime.utcnow().isoformat(),
            "prompt_summary": f"{course_code}: Estimated {category} course (avg GPA ~{base_gpa:.2f}). Limited data available - verify with instructor or peers.",
            "cache_hit": False
        }
    
    async def health_check(self) -> bool:
        """Check if course difficulty service is functioning properly"""
        try:
            if self.grades_data.empty:
                logger.warning("Course difficulty service has no data loaded")
                return False
            
            # Test a sample query
            sample_course = self.grades_data['course_id'].iloc[0]
            test_result = await self.get_course_difficulty(sample_course)
            
            return test_result is not None
            
        except Exception as e:
            logger.error(f"Course difficulty health check failed: {e}")
            return False