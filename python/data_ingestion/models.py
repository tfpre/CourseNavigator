from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# validates the structure from the API
# This model should be very loose to avoid breaking on minor API changes.
class RawEnrollGroup(BaseModel):
    classSections: List[Dict[str, Any]]
    unitsMinimum: int
    unitsMaximum: int
    
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
    """Extract cross-listing information from raw course data."""
    cross_listings = []
    
    # Access raw course data as dict to check for additional fields
    raw_data = raw_course.__dict__
    
    # Strategy 1: Look for catalogGroup field (common in Cornell API)
    catalog_group = raw_data.get("catalogGroup")
    if catalog_group and isinstance(catalog_group, list):
        for group_item in catalog_group:
            if isinstance(group_item, dict):
                subject = group_item.get("subject", "")
                catalog_nbr = group_item.get("catalogNbr", "")
                if subject and catalog_nbr:
                    # Don't include the current course as a cross-listing of itself
                    if not (subject == raw_course.subject and catalog_nbr == raw_course.catalogNbr):
                        cross_listings.append(f"{subject} {catalog_nbr}")
    
    # Strategy 2: Look for crossListGroup field
    cross_list_group = raw_data.get("crossListGroup")
    if cross_list_group and isinstance(cross_list_group, list):
        for cross_item in cross_list_group:
            if isinstance(cross_item, dict):
                subject = cross_item.get("subject", "")
                catalog_nbr = cross_item.get("catalogNbr", "")
                if subject and catalog_nbr:
                    if not (subject == raw_course.subject and catalog_nbr == raw_course.catalogNbr):
                        cross_listings.append(f"{subject} {catalog_nbr}")
    
    # Strategy 3: Look for simpleCombinations field (found in CS 2110/ENGRD 2110 case)
    for enroll_group in raw_course.enrollGroups:
        # Pydantic v2 stores extra attributes in __pydantic_extra__
        simple_combinations = []
        
        # Try Pydantic v2 extra attributes first
        if hasattr(enroll_group, '__pydantic_extra__'):
            simple_combinations = enroll_group.__pydantic_extra__.get("simpleCombinations", [])
        # Try model_extra for newer Pydantic versions (>=2.6)
        elif hasattr(enroll_group, 'model_extra'):
            simple_combinations = enroll_group.model_extra.get("simpleCombinations", [])
        # Fallback to direct attribute access for compatibility
        elif hasattr(enroll_group, 'simpleCombinations'):
            simple_combinations = enroll_group.simpleCombinations
        # Final fallback: try accessing as dict (from model_dump)
        else:
            enroll_group_dict = enroll_group.model_dump()
            simple_combinations = enroll_group_dict.get("simpleCombinations", [])
        
        for combo in simple_combinations:
            if isinstance(combo, dict):
                subject = combo.get("subject", "")
                catalog_nbr = combo.get("catalogNbr", "")
                if subject and catalog_nbr:
                    if not (subject == raw_course.subject and catalog_nbr == raw_course.catalogNbr):
                        cross_listings.append(f"{subject} {catalog_nbr}")
    
    # Strategy 4: Defensive check for subjects listed inside enrollGroups class sections.
    # This is rare in the Cornell API but kept for robustness against future schema changes.
    # Some edge cases may have cross-listing info nested in class sections.
    for enroll_group in raw_course.enrollGroups:
        for class_section in enroll_group.classSections:
            section_subject = class_section.get("subject")
            section_catalog = class_section.get("catalogNbr")
            if (section_subject and section_catalog and 
                section_subject != raw_course.subject):
                cross_listing = f"{section_subject} {section_catalog}"
                if cross_listing not in cross_listings:
                    cross_listings.append(cross_listing)
    
    # Strategy 5: Parse from course title if it contains cross-listing info
    title = raw_course.titleLong or ""
    if "also listed as" in title.lower() or "cross-listed" in title.lower():
        # Extract patterns like "CS 2110 (also listed as ENGRD 2110)"
        import re
        pattern = r'\b([A-Z]{2,5})\s+(\d{4})\b'
        matches = re.findall(pattern, title)
        for subject, catalog_nbr in matches:
            if not (subject == raw_course.subject and catalog_nbr == raw_course.catalogNbr):
                cross_listing = f"{subject} {catalog_nbr}"
                if cross_listing not in cross_listings:
                    cross_listings.append(cross_listing)
    
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
    units_min: int
    units_max: int
    roster: str                         # e.g., "FA25"
    meetings: List[CleanMeeting] = Field(default_factory=list)
    cross_listings: List[str] = Field(default_factory=list)  # e.g., ["ENGRD 2110"]
    
    class Config:
        validate_assignment = True
    
    @classmethod
    def from_raw(cls, raw_course: RawCourse, roster: str) -> "CleanCourse":
        """Transform a RawCourse into a CleanCourse"""
        # Generate our internal ID with offer number for uniqueness
        course_id = f"{roster}-{raw_course.subject}-{raw_course.catalogNbr}-{raw_course.crseOfferNbr}"
        
        # Parse meetings using dedicated function
        meetings = parse_meetings(raw_course)
        
        # Fix units calculation - check all enrollment groups and cast to int
        all_mins = [int(g.unitsMinimum) for g in raw_course.enrollGroups]
        all_maxs = [int(g.unitsMaximum) for g in raw_course.enrollGroups]
        units_min = min(all_mins) if all_mins else 0
        units_max = max(all_maxs) if all_maxs else 0
        
        # Parse cross-listings from available fields
        cross_listings = _parse_cross_listings(raw_course)
        
        # Parse prerequisites using the prerequisite parser
        prereq_ast = None
        prereq_confidence = None
        if raw_course.catalogPrereqCoreq:
            try:
                from python.graph_analysis.prereq_parser import safe_parse_prerequisites
                parsed_prereq = safe_parse_prerequisites(raw_course.catalogPrereqCoreq)
                prereq_ast = parsed_prereq.ast
                prereq_confidence = parsed_prereq.confidence
            except ImportError as e:
                # Handle circular import gracefully - parser not available during some import cycles
                print(f"Warning: Could not import prerequisite parser due to circular import: {e}")
                print("Prerequisites will be parsed in a later processing step.")
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
            prerequisite_text=raw_course.catalogPrereqCoreq,
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