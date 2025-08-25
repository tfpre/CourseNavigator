"""
Conflict Detection Service - Registration Intelligence Lite
 
Implements Ground Truth: Actionable Prioritization
- Detect time conflicts between desired courses
- Suggest backup plans with clear rationale
- Demo-bounded implementation with curated data
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum

logger = logging.getLogger(__name__)

class ConflictType(Enum):
    TIME_OVERLAP = "time_overlap"
    PREREQUISITE_MISSING = "prerequisite_missing" 
    CAPACITY_FULL = "capacity_full"

@dataclass
class CourseSection:
    """Course section with scheduling information"""
    course_code: str
    section_id: str = "001"
    title: str = ""
    instructor: str = ""
    time_slot: str = ""  # e.g., "MWF 14:25-15:15"
    location: str = ""
    capacity: int = 0
    enrolled: int = 0
    waitlist: int = 0
    
    def get_days_and_times(self) -> Tuple[Set[str], Tuple[time, time]]:
        """Parse time_slot into days and start/end times
        
        Returns:
            (days_set, (start_time, end_time))
            e.g., ({'M', 'W', 'F'}, (time(14,25), time(15,15)))
        """
        if not self.time_slot:
            return set(), (time(0,0), time(0,0))
            
        try:
            # Parse "MWF 14:25-15:15" format
            parts = self.time_slot.split(' ')
            if len(parts) != 2:
                return set(), (time(0,0), time(0,0))
                
            days_str, time_range = parts
            days = set(days_str)  # {'M', 'W', 'F'}
            
            start_str, end_str = time_range.split('-')
            start_hour, start_min = map(int, start_str.split(':'))
            end_hour, end_min = map(int, end_str.split(':'))
            
            return days, (time(start_hour, start_min), time(end_hour, end_min))
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse time_slot '{self.time_slot}': {e}")
            return set(), (time(0,0), time(0,0))

@dataclass
class ScheduleConflict:
    """Detected schedule conflict between courses"""
    course_a: str
    course_b: str
    conflict_type: ConflictType
    description: str
    severity: str  # "high", "medium", "low"
    
    # Time overlap details
    overlapping_days: Set[str] = None
    time_overlap: Tuple[time, time] = None

@dataclass 
class BackupPlan:
    """Alternative course recommendation to resolve conflict"""
    original_course: str
    backup_course: str
    rationale: str
    difficulty_delta: str  # "+1 easier", "same", "+1 harder"
    professor_rating: float = 0.0
    fulfills_same_requirements: bool = True

class ConflictDetectionService:
    """Demo-bounded conflict detection for Registration Intelligence"""
    
    def __init__(self):
        # Demo dataset - curated course sections with known conflicts
        self._demo_sections = self._load_demo_sections()
        self._backup_plans = self._load_backup_plans()
        
    def _load_demo_sections(self) -> Dict[str, CourseSection]:
        """Load curated course sections for demo scenarios"""
        
        sections = {
            # Primary conflict: CS 4780 vs CS 4820 (same time slot)
            "CS 4780": CourseSection(
                course_code="CS 4780",
                title="Machine Learning for Intelligent Systems",
                instructor="Prof. Johnson", 
                time_slot="MWF 14:25-15:15",
                location="Olin 155",
                capacity=180,
                enrolled=175,
                waitlist=45
            ),
            "CS 4820": CourseSection(
                course_code="CS 4820", 
                title="Introduction to Algorithms",
                instructor="Prof. Williams",
                time_slot="MWF 14:25-15:15",
                location="Statler Aud",
                capacity=200,
                enrolled=198,
                waitlist=67
            ),
            
            # Backup options with no conflicts
            "CS 4701": CourseSection(
                course_code="CS 4701",
                title="Practicum in Artificial Intelligence", 
                instructor="Prof. Anderson",
                time_slot="TR 11:40-12:55",
                location="Gates 122",
                capacity=60,
                enrolled=45,
                waitlist=8
            ),
            "CS 4740": CourseSection(
                course_code="CS 4740",
                title="Natural Language Processing",
                instructor="Prof. Chen", 
                time_slot="TR 09:05-09:55",
                location="Phillips 101",
                capacity=80,
                enrolled=65,
                waitlist=12
            ),
            "CS 4810": CourseSection(
                course_code="CS 4810",
                title="Computer System Organization and Programming",
                instructor="Prof. Martinez",
                time_slot="MWF 10:10-11:00",
                location="Olin 255",
                capacity=120,
                enrolled=100,
                waitlist=15
            ),
            
            # ECE courses for cross-major conflicts
            "ECE 5760": CourseSection(
                course_code="ECE 5760", 
                title="Advanced Microcontroller Design",
                instructor="Prof. Martinez",
                time_slot="TR 11:40-12:55",
                location="Phillips 203",
                capacity=40,
                enrolled=32,
                waitlist=5
            ),
            "CS 4420": CourseSection(
                course_code="CS 4420",
                title="Computer Networks",
                instructor="Prof. Davis", 
                time_slot="TR 11:40-12:55",
                location="Gates 114", 
                capacity=90,
                enrolled=85,
                waitlist=25
            ),
            
            # Math courses
            "MATH 4710": CourseSection(
                course_code="MATH 4710",
                title="Basic Probability Theory",
                instructor="Prof. Anderson",
                time_slot="MWF 10:10-11:00", 
                location="Malott 253",
                capacity=50,
                enrolled=35,
                waitlist=3
            )
        }
        
        return sections
    
    def _load_backup_plans(self) -> Dict[str, List[BackupPlan]]:
        """Load curated backup plans for known conflicts"""
        
        return {
            "CS 4780": [
                BackupPlan(
                    original_course="CS 4780",
                    backup_course="CS 4701", 
                    rationale="AI practicum covers ML applications, no time conflict, easier enrollment",
                    difficulty_delta="same difficulty",
                    professor_rating=4.1,
                    fulfills_same_requirements=True
                ),
                BackupPlan(
                    original_course="CS 4780",
                    backup_course="CS 4740",
                    rationale="NLP has strong ML foundations, morning slot available, good professor",
                    difficulty_delta="+1 easier", 
                    professor_rating=4.3,
                    fulfills_same_requirements=True
                )
            ],
            "CS 4820": [
                BackupPlan(
                    original_course="CS 4820",
                    backup_course="CS 4810",
                    rationale="Systems programming covers algorithmic thinking, morning slot, reasonable waitlist",
                    difficulty_delta="+1 easier",
                    professor_rating=4.0,
                    fulfills_same_requirements=False
                )
            ],
            "ECE 5760": [
                BackupPlan(
                    original_course="ECE 5760", 
                    backup_course="ECE 4760",
                    rationale="Undergraduate version covers core concepts, likely available",
                    difficulty_delta="+1 easier",
                    professor_rating=3.8,
                    fulfills_same_requirements=True
                )
            ]
        }
    
    def detect_conflicts(self, course_codes: List[str]) -> List[ScheduleConflict]:
        """Detect time conflicts between requested courses
        
        Args:
            course_codes: List of courses student wants to take
            
        Returns:
            List of detected conflicts
        """
        conflicts = []
        
        # Get sections for requested courses
        sections = []
        for code in course_codes:
            if code in self._demo_sections:
                sections.append(self._demo_sections[code])
            else:
                logger.warning(f"Course {code} not in demo dataset")
        
        # Check pairwise time conflicts
        for i, section_a in enumerate(sections):
            for section_b in sections[i+1:]:
                conflict = self._check_time_conflict(section_a, section_b)
                if conflict:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _check_time_conflict(self, section_a: CourseSection, section_b: CourseSection) -> Optional[ScheduleConflict]:
        """Check if two sections have time conflicts"""
        
        days_a, (start_a, end_a) = section_a.get_days_and_times()
        days_b, (start_b, end_b) = section_b.get_days_and_times()
        
        # Check for overlapping days
        overlapping_days = days_a & days_b
        if not overlapping_days:
            return None
            
        # Check for time overlap
        overlap_start = max(start_a, start_b)
        overlap_end = min(end_a, end_b)
        
        if overlap_start >= overlap_end:
            return None  # No actual time overlap
            
        # Calculate severity based on overlap duration
        overlap_minutes = (overlap_end.hour * 60 + overlap_end.minute) - (overlap_start.hour * 60 + overlap_start.minute)
        if overlap_minutes >= 30:
            severity = "high"
        elif overlap_minutes >= 15:
            severity = "medium" 
        else:
            severity = "low"
            
        return ScheduleConflict(
            course_a=section_a.course_code,
            course_b=section_b.course_code,
            conflict_type=ConflictType.TIME_OVERLAP,
            description=f"{section_a.course_code} and {section_b.course_code} both meet {', '.join(sorted(overlapping_days))} {overlap_start.strftime('%H:%M')}-{overlap_end.strftime('%H:%M')}",
            severity=severity,
            overlapping_days=overlapping_days,
            time_overlap=(overlap_start, overlap_end)
        )
    
    def suggest_backup_plans(self, conflicts: List[ScheduleConflict]) -> Dict[str, List[BackupPlan]]:
        """Get curated backup plans for conflicted courses
        
        Args:
            conflicts: List of detected schedule conflicts
            
        Returns:
            Dict mapping course_code -> list of backup plans
        """
        suggestions = {}
        
        for conflict in conflicts:
            # Get backup plans for both courses in conflict
            for course in [conflict.course_a, conflict.course_b]:
                if course in self._backup_plans:
                    suggestions[course] = self._backup_plans[course]
                    
        return suggestions
    
    def get_section_info(self, course_code: str) -> Optional[CourseSection]:
        """Get section information for a course"""
        return self._demo_sections.get(course_code)
    
    def format_conflict_summary(self, conflicts: List[ScheduleConflict]) -> str:
        """Format conflicts for display in chat response"""
        if not conflicts:
            return "✅ No time conflicts detected in your course selection."
            
        summary = f"⚠️  **{len(conflicts)} schedule conflict(s) detected:**\n\n"
        
        for i, conflict in enumerate(conflicts, 1):
            summary += f"{i}. **{conflict.course_a}** vs **{conflict.course_b}**\n"
            summary += f"   - {conflict.description}\n"
            summary += f"   - Severity: {conflict.severity}\n\n"
            
        return summary
    
    def format_backup_suggestions(self, backup_plans: Dict[str, List[BackupPlan]]) -> str:
        """Format backup plan suggestions for display"""
        if not backup_plans:
            return ""
            
        summary = "💡 **Backup course suggestions:**\n\n"
        
        for original_course, plans in backup_plans.items():
            summary += f"**Instead of {original_course}:**\n"
            
            for i, plan in enumerate(plans, 1):
                summary += f"{i}. **{plan.backup_course}** - {plan.rationale}\n"
                summary += f"   - Difficulty: {plan.difficulty_delta}\n"
                if plan.professor_rating > 0:
                    summary += f"   - Professor rating: {plan.professor_rating}/5.0\n"
                summary += "\n"
                
        return summary