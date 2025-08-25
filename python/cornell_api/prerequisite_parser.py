"""
Cornell Prerequisite Parser
Extracts structured prerequisite relationships from text-based Cornell course descriptions
"""

import re
import logging
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class PrereqType(Enum):
    REQUIRED = "required"
    COREQUISITE = "corequisite"
    RECOMMENDED = "recommended"

@dataclass
class ParsedPrerequisite:
    """Structured prerequisite information"""
    course_codes: List[str]  # e.g., ["CS 1110", "CS 1112"]
    relation: str  # "AND", "OR"
    type: PrereqType
    confidence: float  # 0-1 confidence in parsing accuracy
    raw_text: str

@dataclass
class PrerequisiteParseResult:
    """Complete prerequisite parsing result"""
    prerequisites: List[ParsedPrerequisite]
    total_courses_mentioned: int
    parsing_confidence: float
    has_complex_logic: bool
    raw_text: str

class CornellPrerequisiteParser:
    """
    Parses Cornell's text-based prerequisite descriptions into structured data
    
    Handles patterns like:
    - "Prerequisite: CS 1110 or CS 1112"
    - "Prerequisites: CS 2110 and MATH 1920"
    - "Corequisite: MATH 1110, MATH 1910, or equivalent"
    """
    
    def __init__(self):
        # Course code patterns - matches "CS 1110", "MATH 1920", etc.
        self.course_pattern = re.compile(r'\b([A-Z]{2,6})\s+(\d{4})\b')
        
        # Prerequisite type patterns
        self.prereq_patterns = {
            PrereqType.REQUIRED: re.compile(r'\b(?:prerequisite|prereq)s?:?\s*', re.IGNORECASE),
            PrereqType.COREQUISITE: re.compile(r'\b(?:corequisite|coreq)s?:?\s*', re.IGNORECASE),
            PrereqType.RECOMMENDED: re.compile(r'\b(?:recommended|suggestion|advised):?\s*', re.IGNORECASE)
        }
        
        # Logic connectors
        self.and_pattern = re.compile(r'\b(?:and|&|,)\b', re.IGNORECASE)
        self.or_pattern = re.compile(r'\b(?:or|\|)\b', re.IGNORECASE)
        
        # Complex patterns that reduce parsing confidence
        self.complex_patterns = [
            re.compile(r'\b(?:equivalent|permission|instructor|consent)\b', re.IGNORECASE),
            re.compile(r'\b(?:one\s+of|at\s+least|minimum)\b', re.IGNORECASE),
            re.compile(r'\([^)]*\)', re.IGNORECASE),  # Parenthetical expressions
        ]
    
    def parse_prerequisites(self, text: str) -> PrerequisiteParseResult:
        """
        Parse prerequisite text into structured format
        
        Args:
            text: Raw prerequisite text from Cornell API
            
        Returns:
            PrerequisiteParseResult with structured prerequisite data
        """
        if not text or not text.strip():
            return PrerequisiteParseResult(
                prerequisites=[],
                total_courses_mentioned=0,
                parsing_confidence=1.0,
                has_complex_logic=False,
                raw_text=""
            )
        
        logger.debug(f"Parsing prerequisites: {text}")
        
        # Extract all course codes mentioned
        course_matches = self.course_pattern.findall(text)
        all_courses = [f"{subject} {number}" for subject, number in course_matches]
        
        # Check for complex patterns that reduce confidence
        has_complex = any(pattern.search(text) for pattern in self.complex_patterns)
        
        # Split text by prerequisite types
        prerequisites = []
        
        for prereq_type, pattern in self.prereq_patterns.items():
            matches = pattern.finditer(text)
            for match in matches:
                # Extract text after the prerequisite keyword
                start_pos = match.end()
                # Find end of this prerequisite section (next keyword or sentence end)
                end_pos = len(text)
                
                for other_pattern in self.prereq_patterns.values():
                    other_match = other_pattern.search(text, start_pos)
                    if other_match and other_match.start() < end_pos:
                        end_pos = other_match.start()
                
                prereq_text = text[start_pos:end_pos].strip()
                if not prereq_text:
                    continue
                
                # Parse this prerequisite section
                parsed = self._parse_prerequisite_section(prereq_text, prereq_type, all_courses)
                if parsed:
                    prerequisites.append(parsed)
        
        # If no explicit prerequisite keywords found, try to parse the whole text
        if not prerequisites and all_courses:
            parsed = self._parse_prerequisite_section(text, PrereqType.REQUIRED, all_courses)
            if parsed:
                prerequisites.append(parsed)
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(prerequisites, has_complex, len(all_courses))
        
        return PrerequisiteParseResult(
            prerequisites=prerequisites,
            total_courses_mentioned=len(all_courses),
            parsing_confidence=confidence,
            has_complex_logic=has_complex,
            raw_text=text
        )
    
    def _parse_prerequisite_section(self, text: str, prereq_type: PrereqType, all_courses: List[str]) -> Optional[ParsedPrerequisite]:
        """Parse a single prerequisite section"""
        # Find course codes in this section
        section_matches = self.course_pattern.findall(text)
        section_courses = [f"{subject} {number}" for subject, number in section_matches]
        
        if not section_courses:
            return None
        
        # Determine relationship between courses
        has_and = self.and_pattern.search(text)
        has_or = self.or_pattern.search(text)
        
        if has_or and not has_and:
            relation = "OR"
            confidence = 0.9
        elif has_and and not has_or:
            relation = "AND"
            confidence = 0.9
        elif len(section_courses) == 1:
            relation = "SINGLE"
            confidence = 0.95
        else:
            # Mixed or unclear logic
            relation = "COMPLEX"
            confidence = 0.6
        
        return ParsedPrerequisite(
            course_codes=section_courses,
            relation=relation,
            type=prereq_type,
            confidence=confidence,
            raw_text=text
        )
    
    def _calculate_confidence(self, prerequisites: List[ParsedPrerequisite], has_complex: bool, total_courses: int) -> float:
        """Calculate overall parsing confidence"""
        if not prerequisites:
            return 1.0 if total_courses == 0 else 0.3
        
        # Average individual prerequisite confidences
        individual_confidence = sum(p.confidence for p in prerequisites) / len(prerequisites)
        
        # Penalty for complex patterns
        complexity_penalty = 0.3 if has_complex else 0.0
        
        # Penalty for many courses (likely complex logic)
        course_penalty = min(0.2, total_courses * 0.05) if total_courses > 3 else 0.0
        
        final_confidence = max(0.1, individual_confidence - complexity_penalty - course_penalty)
        
        return final_confidence
    
    def extract_prerequisite_edges(self, course_code: str, parsed_result: PrerequisiteParseResult) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        Convert parsed prerequisites to graph edges
        
        Returns:
            List of (prerequisite_course, target_course, metadata) tuples
        """
        edges = []
        
        for prereq in parsed_result.prerequisites:
            if prereq.type != PrereqType.REQUIRED:
                continue  # Only include hard prerequisites in graph
            
            for prereq_course in prereq.course_codes:
                metadata = {
                    "type": prereq.relation.lower(),
                    "confidence": prereq.confidence,
                    "raw_text": prereq.raw_text
                }
                edges.append((prereq_course, course_code, metadata))
        
        return edges

# Convenience function for easy usage
def parse_cornell_prerequisites(text: str) -> PrerequisiteParseResult:
    """Parse Cornell prerequisite text - convenience function"""
    parser = CornellPrerequisiteParser()
    return parser.parse_prerequisites(text)