from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# validates the structure from the API
# This model should be very loose to avoid breaking on minor API changes.
class RawEnrollGroup(BaseModel):
    classSections: List[Dict[str, Any]]
    unitsMinimum: float  # Cornell has fractional credits (0.25, 0.5, 1.5)
    unitsMaximum: float  # Changed from int to float for data integrity
    
    class Config:
        extra = "allow"

class RawCourse(BaseModel):
    crseId: int
    crseOfferNbr: int  # need this for unique IDs
    subject: str
    catalogNbr: str
    titleLong: str
    description: Optional[str] = None
    catalogPrereqCoreq: Optional[str] = None
    catalogPrereq: Optional[str] = None  # Alternative prerequisite field
    enrollGroups: List[RawEnrollGroup]
    # Allow additional fields that we might not care about
    class Config:
        extra = "allow"

# clean model: our application's internal representation
# This model is strict and represents the ideal data structure we want to work with.
class CleanMeeting(BaseModel):
    """Represents a class meeting time (lecture, discussion, lab, etc.)"""
    type: str  # e.g., "LEC", "DIS", "LAB"
    days: List[str]  # e.g., ["M", "W", "F"]
    time_start: Optional[str] = None  # e.g., "10:10"
    time_end: Optional[str] = None    # e.g., "11:00"
    location: Optional[str] = None    # e.g., "Olin Hall 155"
    instructor: Optional[str] = None

def _extract_instructor(meeting: dict) -> Optional[str]:
    """Extract instructor information from meeting data."""
    instructors = meeting.get("instructors", [])
    if instructors and len(instructors) > 0:
        # Try netid first (most reliable), then displayName, then build from firstName/lastName
        instructor = instructors[0]
        if instructor.get("netid"):
            return instructor["netid"]
        elif instructor.get("displayName"):
            return instructor["displayName"]
        elif instructor.get("firstName") or instructor.get("lastName"):
            first = instructor.get("firstName", "")
            last = instructor.get("lastName", "")
            return f"{first} {last}".strip()
    return None

def parse_meetings(raw_course: "RawCourse") -> List[CleanMeeting]:
    """Parse meeting information from raw course data."""
    meetings = []
    seen_meetings = set()  # Track duplicate meetings
    
    for enroll_group in raw_course.enrollGroups:
        for class_section in enroll_group.classSections:
            # Get meeting data from the class section
            section_meetings = class_section.get("meetings", [])
            
            if not section_meetings:
                # Fallback: create a meeting with just the component type
                meeting_key = (
                    class_section.get("ssrComponent", "UNKNOWN"),
                    tuple([]),  # empty days
                    None,       # no start time
                    None,       # no end time
                    None,       # no location
                    None        # no instructor data available
                )
                if meeting_key not in seen_meetings:
                    meetings.append(CleanMeeting(
                        type=class_section.get("ssrComponent", "UNKNOWN"),
                        days=[],
                        instructor=None  # No meeting data available
                    ))
                    seen_meetings.add(meeting_key)
                continue
            
            # Parse each meeting in the class section
            for meeting in section_meetings:
                # Parse day pattern (e.g., "MWF" or "M W F")
                pattern = meeting.get("pattern", "")
                if pattern.strip() == "ARR":
                    # "ARR" means arranged/flexible - no specific days
                    days = []
                else:
                    days = [char for char in pattern.replace(" ", "") if char.isalpha()]
                
                # Create unique key for deduplication
                meeting_key = (
                    class_section.get("ssrComponent", "UNKNOWN"),
                    tuple(sorted(days)),
                    meeting.get("timeStart"),
                    meeting.get("timeEnd"),
                    meeting.get("facilityDescr"),
                    _extract_instructor(meeting)
                )
                
                if meeting_key not in seen_meetings:
                    meetings.append(CleanMeeting(
                        type=class_section.get("ssrComponent", "UNKNOWN"),
                        days=days,
                        time_start=meeting.get("timeStart"),
                        time_end=meeting.get("timeEnd"),
                        location=meeting.get("facilityDescr"),
                        instructor=_extract_instructor(meeting)
                    ))
                    seen_meetings.add(meeting_key)
    
    return meetings

def _parse_cross_listings(raw_course: "RawCourse") -> List[str]:
    """
    Extract cross-listing information from raw course data.
    
    Simplified approach based on analysis of real Cornell data:
    - Only simpleCombinations field is used (32.8% of courses)
    - 4 other strategies were unused (0% usage each)
    - Reduces complexity from 80+ lines to ~15 lines
    """
    cross_listings = []
    
    # Single strategy: simpleCombinations field (proven to work for all Cornell cross-listings)
    for enroll_group in raw_course.enrollGroups:
        # Get simpleCombinations with fallback for different Pydantic versions
        simple_combinations = []
        
        if hasattr(enroll_group, '__pydantic_extra__'):
            simple_combinations = enroll_group.__pydantic_extra__.get("simpleCombinations", [])
        elif hasattr(enroll_group, 'model_extra'):
            simple_combinations = enroll_group.model_extra.get("simpleCombinations", [])
        elif hasattr(enroll_group, 'simpleCombinations'):
            simple_combinations = enroll_group.simpleCombinations
        else:
            # Final fallback: model_dump()
            enroll_group_dict = enroll_group.model_dump()
            simple_combinations = enroll_group_dict.get("simpleCombinations", [])
        
        for combo in simple_combinations:
            if isinstance(combo, dict):
                subject = combo.get("subject", "")
                catalog_nbr = combo.get("catalogNbr", "")
                if subject and catalog_nbr:
                    # Don't include the course as a cross-listing of itself
                    if not (subject == raw_course.subject and catalog_nbr == raw_course.catalogNbr):
                        cross_listings.append(f"{subject} {catalog_nbr}")
    
    # Remove duplicates and sort for consistency
    return sorted(list(set(cross_listings)))

class CleanCourse(BaseModel):
    """Our application's internal representation of a course"""
    id: str                              # e.g., "FA25-CS-2110-1"
    crse_id: int                        # Cornell's internal course ID
    crse_offer_nbr: int                 # Course offer number for uniqueness
    title: str                          # Course title
    subject: str                        # e.g., "CS"
    catalog_nbr: str                    # e.g., "2110"
    description_text: Optional[str] = None
    prerequisite_text: Optional[str] = None
    prereq_ast: Optional[Dict] = None   # Parsed prerequisite structure
    prereq_confidence: Optional[float] = None  # Parser confidence (0-1)
    units_min: float  # Cornell has fractional credits 
    units_max: float  # Changed from int to float for data integrity
    roster: str                         # e.g., "FA25"
    meetings: List[CleanMeeting] = Field(default_factory=list)
    cross_listings: List[str] = Field(default_factory=list)  # e.g., ["ENGRD 2110"]
    
    class Config:
        validate_assignment = True
    
    @classmethod
    def from_raw(cls, raw_course: RawCourse, roster: str, strict_mode: bool = True) -> "CleanCourse":
        """
        Transform a RawCourse into a CleanCourse with strict validation.
        
        Best Practices Implemented:
        - Fail-fast validation: Expose data quality issues rather than hiding them
        - Business rule enforcement: Validate against Cornell course standards  
        - Comprehensive error reporting: Track all validation issues for monitoring
        - Data integrity: Preserve valid data, reject invalid data with clear reasoning
        
        Args:
            raw_course: Raw course data from Cornell API
            roster: Academic term (e.g., "FA25")
            strict_mode: If True, validation failures raise exceptions
            
        Raises:
            ValueError: If strict_mode=True and validation fails
        """
        from python.data_ingestion.validation import BusinessRuleValidator, DataQualityTracker
        
        course_code = f"{raw_course.subject} {raw_course.catalogNbr}"
        
        # Step 1: Strict validation with business rules
        validator = BusinessRuleValidator(strict_mode=strict_mode)
        validation_result = validator.validate_course(raw_course, roster)
        
        # Log all validation issues
        validation_result.log_issues()
        
        # Fail fast if critical issues found in strict mode
        if not validation_result.is_valid and strict_mode:
            critical_messages = [issue.message for issue in validation_result.critical_issues]
            raise ValueError(f"Course {course_code} failed validation: {'; '.join(critical_messages)}")
        
        # Step 2: Parse validated data with controlled error handling
        course_id = f"{roster}-{raw_course.subject}-{raw_course.catalogNbr}-{raw_course.crseOfferNbr}"
        
        # Parse meetings - fail fast if parsing fails
        meetings = parse_meetings(raw_course)
        
        # Calculate units from enrollment groups (preserve fractional credits)
        all_mins = [float(g.unitsMinimum) for g in raw_course.enrollGroups if g.unitsMinimum is not None]
        all_maxs = [float(g.unitsMaximum) for g in raw_course.enrollGroups if g.unitsMaximum is not None]
        units_min = min(all_mins) if all_mins else 0.0
        units_max = max(all_maxs) if all_maxs else 0.0
        
        # Log fractional credits for monitoring 
        if units_min != int(units_min) or units_max != int(units_max):
            logger.info(f"Fractional credits preserved for {course_code}: {units_min}-{units_max}")
        
        # Parse cross-listings using simplified approach (will be simplified in Priority 2)
        cross_listings = _parse_cross_listings(raw_course)
        
        # Parse prerequisites using the prerequisite parser
        prereq_text = raw_course.catalogPrereqCoreq or getattr(raw_course, 'catalogPrereq', '') or ''
        prereq_ast = None
        prereq_confidence = None
        if prereq_text and prereq_text.strip():
            try:
                from python.graph_analysis.prereq_parser import safe_parse_prerequisites
                parsed_prereq = safe_parse_prerequisites(prereq_text)
                prereq_ast = parsed_prereq.ast
                prereq_confidence = parsed_prereq.confidence
            except ImportError:
                # Parser not available during some import cycles - acceptable
                logger.debug(f"Prerequisite parser not available for {course_code}")
                prereq_ast = None
                prereq_confidence = None
            except Exception as e:
                # Prerequisite parsing failure - log but don't fail course creation
                logger.warning(f"Failed to parse prerequisites for {course_code}: {e}")
                prereq_ast = None
                prereq_confidence = None
        
        return cls(
            id=course_id,
            crse_id=raw_course.crseId,
            crse_offer_nbr=raw_course.crseOfferNbr,
            title=raw_course.titleLong,
            subject=raw_course.subject,
            catalog_nbr=raw_course.catalogNbr,
            description_text=raw_course.description,
            prerequisite_text=prereq_text,
            prereq_ast=prereq_ast,
            prereq_confidence=prereq_confidence,
            units_min=units_min,
            units_max=units_max,
            roster=roster,
            meetings=meetings,
            cross_listings=cross_listings
        )

# API Response Models
class RawClassesResponse(BaseModel):
    """Response from the Cornell API for class searches"""
    status: str
    data: Dict[str, Any]
    
    def get_courses(self) -> List[RawCourse]:
        """Extract courses from the API response"""
        courses = []
        classes = self.data.get("classes", [])
        
        for class_data in classes:
            try:
                course = RawCourse(**class_data)
                courses.append(course)
            except Exception as e:
                print(f"Warning: Could not parse course {class_data.get('crseId')}: {e}")
                continue
                
        return courses