"""
Production prerequisite parser using regex-only approach.
Focuses on extracting specific course-to-course dependencies for graph database.
Ignores vague background requirements that don't contain specific course codes.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Configure logging to prevent log volume explosion during mass parsing
logging.basicConfig(level=logging.WARNING)  # Set root logger to WARNING to reduce noise

# Set up module-specific logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Allow INFO messages for this module

@dataclass
class ParsedPrereq:
    """Result of prerequisite parsing with AST, confidence, and error handling"""
    ast: Optional[Dict[str, Any]]
    confidence: float  # 0-1 confidence score
    error: Optional[str]
    tokens: List[str]  # Course codes found

def safe_parse_prerequisites(text: str) -> ParsedPrereq:
    """
    Parse prerequisites using regex-only approach.
    Never crashes - always returns a ParsedPrereq.
    """
    if not text or not text.strip():
        return ParsedPrereq(
            ast=None,
            confidence=0.0,
            error=None,
            tokens=[]
        )
    
    try:
        return regex_parse_prerequisites(text)
        
    except Exception as e:
        logger.error(f"Parse failed for: {text[:50]}..., error: {e}")
        return ParsedPrereq(
            ast=None,
            confidence=0.0,
            error=str(e),
            tokens=[]
        )

def regex_parse_prerequisites(text: str) -> ParsedPrereq:
    """
    Extract course codes and build simple AST using regex patterns.
    Only creates AST if specific course codes are found.
    """
    if not text or not text.strip():
        return ParsedPrereq(ast=None, confidence=0.0, error=None, tokens=[])
    
    # Extract specific course codes
    course_codes = extract_course_codes(text)
    
    # If no course codes found, treat as background requirement (not a graph prerequisite)
    if not course_codes:
        return ParsedPrereq(
            ast=None,  # No AST for vague requirements
            confidence=0.0,
            error=None,
            tokens=[]
        )
    
    # Build AST for specific course dependencies
    ast = build_prerequisite_ast(text, course_codes)
    confidence = calculate_confidence(text, course_codes)
    
    return ParsedPrereq(
        ast=ast,
        confidence=confidence,
        error=None,
        tokens=course_codes
    )

def extract_course_codes(text: str) -> List[str]:
    """Extract specific course codes using multiple regex patterns"""
    course_codes = []
    
    # Pattern 1: Standard course codes (CS 2110, MATH 1920, ENGRD 2110)
    standard_pattern = r'\b([A-Z]{2,5})\s+(\d{3,4})\b'
    matches = re.findall(standard_pattern, text)
    for subject, number in matches:
        course_codes.append(f"{subject} {number}")
    
    # Pattern 2: Course codes with letters (CS 2110A, PHYS 2214)
    letter_pattern = r'\b([A-Z]{2,5})\s+(\d{3,4}[A-Z])\b'
    letter_matches = re.findall(letter_pattern, text)
    for subject, number in letter_matches:
        course_codes.append(f"{subject} {number}")
    
    # Pattern 3: Range pattern (CS 2110-2800) - expand to individual courses
    range_pattern = r'\b([A-Z]{2,5})\s+(\d{3,4})-(\d{3,4})\b'
    range_matches = re.findall(range_pattern, text)
    for subject, start, end in range_matches:
        start_num = int(start)
        end_num = int(end)
        # Expand range to individual course numbers
        for num in range(start_num, end_num + 1):
            course_codes.append(f"{subject} {num}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_codes = []
    for code in course_codes:
        if code not in seen:
            seen.add(code)
            unique_codes.append(code)
    
    return unique_codes

def build_prerequisite_ast(text: str, course_codes: List[str]) -> Dict[str, Any]:
    """
    Build AST structure for course-to-course dependencies.
    Creates logical structure based on AND/OR keywords.
    """
    text_lower = text.lower()
    
    # Check for permission clauses which make prerequisites optional
    has_permission = 'permission' in text_lower
    
    # Determine relationship type with explicit prerequisite vs corequisite distinction
    if any(word in text_lower for word in ['corequisite', 'concurrent', 'may be taken concurrently']):
        base_type = 'COREQUISITE'  # Must be taken at same time or before
    elif 'prerequisite' in text_lower:
        # Explicit prerequisite - must be completed before
        if 'or' in text_lower and len(course_codes) > 1:
            base_type = 'PREREQUISITE_OR'  # One of several prerequisites required
        elif 'and' in text_lower and len(course_codes) > 1:
            base_type = 'PREREQUISITE_AND'  # All prerequisites required
        else:
            base_type = 'PREREQUISITE'  # Single prerequisite
    elif 'recommended' in text_lower:
        # Recommended courses - suggested but not required
        if 'or' in text_lower and len(course_codes) > 1:
            base_type = 'RECOMMENDED_OR'  # One of several recommendations
        elif 'and' in text_lower and len(course_codes) > 1:
            base_type = 'RECOMMENDED_AND'  # All recommendations
        else:
            base_type = 'RECOMMENDED'  # Single recommendation
    elif 'or' in text_lower and len(course_codes) > 1:
        base_type = 'OR_GROUP'  # General alternative requirement
    elif 'and' in text_lower and len(course_codes) > 1:
        base_type = 'AND_GROUP'  # General multiple requirements
    else:
        base_type = 'MANDATORY'  # Single course or unclear logic
    
    # Add permission suffix if permission clause is present
    if has_permission:
        relationship_type = f"{base_type}_OR_PERMISSION"
    else:
        relationship_type = base_type
    
    # Build AST with course dependencies
    ast = {
        'type': relationship_type,
        'courses': course_codes,
        'raw_text': text.strip(),
        'metadata': {
            'has_permission_clause': 'permission' in text_lower,
            'has_equivalent_clause': 'equivalent' in text_lower,
            'is_recommended': 'recommended' in text_lower
        }
    }
    
    return ast

def calculate_confidence(text: str, course_codes: List[str]) -> float:
    """
    Calculate confidence for prerequisites with specific course codes.
    Higher confidence = clearer logical structure.
    """
    if not course_codes:
        return 0.0
    
    text_lower = text.lower()
    confidence = 0.9  # Start high since we have specific course codes
    
    # Reduce confidence for complex nested logic
    if '(' in text and ')' in text:
        confidence -= 0.2
    
    # Reduce confidence for ambiguous permission/equivalent clauses
    if 'permission' in text_lower or 'equivalent' in text_lower:
        confidence -= 0.3
    
    # Reduce confidence for very long/complex text
    if len(text) > 150:
        confidence -= 0.1
    
    # Increase confidence for simple, clear patterns
    simple_patterns = [
        r'prerequisite:\s*[A-Z]+\s+\d+',  # "Prerequisite: CS 2110"
        r'corequisite:\s*[A-Z]+\s+\d+',   # "Corequisite: MATH 1920"
        r'^[A-Z]+\s+\d+$'                 # Just "CS 2110"
    ]
    
    for pattern in simple_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            confidence += 0.1
            break
    
    return max(0.0, min(1.0, confidence))

def update_course_with_prerequisites(course_data: dict) -> dict:
    """
    Add parsed prerequisite data to a course dictionary.
    Updates course_data in place and returns it.
    """
    prereq_text = course_data.get('prerequisite_text')
    if not prereq_text:
        course_data.update({
            'prereq_ast': None,
            'prereq_confidence': None
        })
        return course_data
    
    # Parse prerequisites
    parsed = safe_parse_prerequisites(prereq_text)
    
    # Add parsed data to course
    course_data.update({
        'prereq_ast': parsed.ast,
        'prereq_confidence': parsed.confidence
    })
    
    return course_data

# Test and validation functions
def test_parser_on_real_data():
    """Test parser on sample real Cornell prerequisites"""
    test_cases = [
        # Should succeed (specific course codes)
        "CS 2110",
        "Prerequisite: CS 2110 or CS 2112", 
        "CS 2110 and MATH 1920",
        "Corequisite: MATH 1110, MATH 1910, or equivalent",
        "Prerequisite: CS 3410 or CS 3420",
        "CS 2110-2112",  # Range pattern test - should expand to CS 2110, CS 2111, CS 2112
        "Recommended: CS 2110 or CS 2112",  # Recommended type test
        "Prerequisite: CS 3110 or permission of instructor",  # Permission clause test
        
        # Should ignore (vague background requirements)
        "Assumes basic high school mathematics (no calculus) but no programming experience",
        "Prerequisite: one course in programming", 
        "Some familiarity with linear algebra and statistics",
        "Recommended prerequisite: good comfort level with computers"
    ]
    
    print("Testing prerequisite parser on real Cornell data:\n")
    
    for text in test_cases:
        result = safe_parse_prerequisites(text)
        
        if result.ast:
            print(f"✅ PARSED: {text}")
            print(f"   Courses: {result.tokens}")
            print(f"   Type: {result.ast['type']}")
            print(f"   Confidence: {result.confidence:.2f}")
        else:
            print(f"⭕ IGNORED: {text}")
            print(f"   Reason: No specific course codes (background requirement)")
        
        print()

if __name__ == "__main__":
    test_parser_on_real_data()