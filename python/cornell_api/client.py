"""
Cornell Course Roster API Client
Integrates with Cornell's live Course Roster API 2.0 to fetch current course data
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import httpx
import json

logger = logging.getLogger(__name__)

# Cornell API Configuration
CORNELL_API_BASE = "https://classes.cornell.edu/api/2.0"
RATE_LIMIT_DELAY = 1.1  # Slightly over 1 second per request as required

@dataclass
class CourseInfo:
    """Structured course information from Cornell API"""
    subject: str
    catalog_nbr: str
    title_short: str
    title_long: str
    description: str
    prerequisite_text: Optional[str]
    corequisite_text: Optional[str]
    outcomes: List[str]
    units_min: Optional[int]
    units_max: Optional[int]
    roster: str
    instructors: List[str]
    
    @property
    def course_code(self) -> str:
        """Generate course code in standard format"""
        return f"{self.subject} {self.catalog_nbr}"
    
    @property
    def course_id(self) -> str:
        """Generate unique course ID including roster"""
        return f"{self.roster}-{self.subject}-{self.catalog_nbr}"

@dataclass
class APIStats:
    """Track API usage statistics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    subjects_fetched: int = 0
    courses_fetched: int = 0
    last_request_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

class CornellAPIClient:
    """
    Cornell Course Roster API 2.0 Client
    
    Handles rate limiting, error recovery, and data transformation
    for Cornell's live course data.
    """
    
    def __init__(self, roster: str = "SP25"):
        self.roster = roster
        self.base_url = CORNELL_API_BASE
        self.stats = APIStats()
        self.last_request_time = 0.0
        
        # HTTP client with reasonable timeouts
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def _rate_limited_request(self, url: str) -> Dict[str, Any]:
        """Make rate-limited request to Cornell API"""
        # Enforce 1+ second delay between requests
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < RATE_LIMIT_DELAY:
            await asyncio.sleep(RATE_LIMIT_DELAY - time_since_last)
        
        self.stats.total_requests += 1
        self.last_request_time = time.time()
        
        try:
            logger.info(f"Fetching: {url}")
            response = await self.client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") != "success":
                raise Exception(f"API returned error status: {data}")
            
            self.stats.successful_requests += 1
            self.stats.last_request_time = datetime.utcnow()
            
            return data.get("data", {})
            
        except Exception as e:
            self.stats.failed_requests += 1
            logger.error(f"Cornell API request failed for {url}: {e}")
            raise
    
    async def get_subjects(self) -> List[Dict[str, str]]:
        """Get all available subjects for the roster"""
        url = f"{self.base_url}/config/subjects.json?roster={self.roster}"
        data = await self._rate_limited_request(url)
        
        subjects = data.get("subjects", [])
        self.stats.subjects_fetched = len(subjects)
        
        logger.info(f"Fetched {len(subjects)} subjects for {self.roster}")
        return subjects
    
    async def get_courses_for_subject(self, subject: str) -> List[CourseInfo]:
        """Get all courses for a specific subject"""
        url = f"{self.base_url}/search/classes.json?roster={self.roster}&subject={subject}"
        data = await self._rate_limited_request(url)
        
        classes = data.get("classes", [])
        courses = []
        
        for class_data in classes:
            try:
                # Extract course information
                course = CourseInfo(
                    subject=class_data.get("subject", ""),
                    catalog_nbr=class_data.get("catalogNbr", ""),
                    title_short=class_data.get("titleShort", ""),
                    title_long=class_data.get("titleLong", ""),
                    description=class_data.get("description", ""),
                    prerequisite_text=class_data.get("catalogPrereqCoreq"),
                    corequisite_text=class_data.get("catalogCoreq"),
                    outcomes=class_data.get("catalogOutcomes", []),
                    units_min=None,  # Would need to parse from enrollGroups
                    units_max=None,  # Would need to parse from enrollGroups
                    roster=self.roster,
                    instructors=self._extract_instructors(class_data)
                )
                courses.append(course)
                
            except Exception as e:
                logger.warning(f"Failed to parse course data: {e}")
                continue
        
        self.stats.courses_fetched += len(courses)
        logger.info(f"Fetched {len(courses)} courses for subject {subject}")
        
        return courses
    
    def _extract_instructors(self, class_data: Dict[str, Any]) -> List[str]:
        """Extract instructor names from complex enrollGroups structure"""
        instructors = set()
        
        enroll_groups = class_data.get("enrollGroups", [])
        for group in enroll_groups:
            class_sections = group.get("classSections", [])
            for section in class_sections:
                meetings = section.get("meetings", [])
                for meeting in meetings:
                    meeting_instructors = meeting.get("instructors", [])
                    for instructor in meeting_instructors:
                        first_name = instructor.get("firstName", "")
                        last_name = instructor.get("lastName", "")
                        if first_name and last_name:
                            instructors.add(f"{first_name} {last_name}")
        
        return list(instructors)
    
    async def get_all_courses(self, subject_filter: Optional[List[str]] = None) -> List[CourseInfo]:
        """
        Fetch all courses from Cornell API
        
        Args:
            subject_filter: Optional list of subject codes to fetch (e.g., ['CS', 'MATH'])
                           If None, fetches all subjects
        """
        logger.info(f"Starting comprehensive course fetch for {self.roster}")
        
        # Get available subjects
        subjects = await self.get_subjects()
        subject_codes = [s["value"] for s in subjects]
        
        # Apply filter if provided
        if subject_filter:
            subject_codes = [s for s in subject_codes if s in subject_filter]
            logger.info(f"Filtering to {len(subject_codes)} subjects: {subject_filter}")
        
        all_courses = []
        
        # Fetch courses for each subject with progress logging
        for i, subject_code in enumerate(subject_codes, 1):
            try:
                courses = await self.get_courses_for_subject(subject_code)
                all_courses.extend(courses)
                
                if i % 10 == 0:  # Progress update every 10 subjects
                    logger.info(f"Progress: {i}/{len(subject_codes)} subjects, {len(all_courses)} courses total")
                    
            except Exception as e:
                logger.error(f"Failed to fetch courses for {subject_code}: {e}")
                continue
        
        logger.info(f"Completed course fetch: {len(all_courses)} courses from {len(subject_codes)} subjects")
        return all_courses
    
    def get_stats(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        return {
            "roster": self.roster,
            "total_requests": self.stats.total_requests,
            "successful_requests": self.stats.successful_requests,
            "failed_requests": self.stats.failed_requests,
            "success_rate": f"{self.stats.success_rate:.2%}",
            "subjects_fetched": self.stats.subjects_fetched,
            "courses_fetched": self.stats.courses_fetched,
            "last_request": self.stats.last_request_time.isoformat() if self.stats.last_request_time else None
        }