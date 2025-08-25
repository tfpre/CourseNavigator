#!/usr/bin/env python3
"""
Test strict validation on existing FA25 course data.

This will expose quality issues that were previously hidden by graceful degradation.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from pathlib import Path
from python.data_ingestion.models import RawCourse, CleanCourse
from python.data_ingestion.validation import BusinessRuleValidator, DataQualityTracker, ValidationSeverity

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def load_fa25_data():
    """Load existing FA25 course data for validation testing"""
    # Load raw FA25 data from compressed JSON files
    raw_data_dir = Path("/mnt/c/dev/CourseNavigator/data/raw")
    fa25_files = list(raw_data_dir.glob("FA25_*.json.gz"))
    
    if not fa25_files:
        logger.error("No FA25 raw data files found")
        return []
    
    courses = []
    for file_path in fa25_files[:2]:  # Test with first 2 files (CS and one other)
        logger.info(f"Loading raw data from {file_path}")
        
        try:
            import gzip
            with gzip.open(file_path, 'rt') as f:
                data = json.load(f)
                
            # Extract courses from Cornell API response
            classes_data = data.get('data', {}).get('classes', [])
            logger.info(f"Found {len(classes_data)} courses in {file_path.name}")
            
            for class_data in classes_data:
                try:
                    raw_course = RawCourse(**class_data)
                    courses.append(raw_course)
                except Exception as e:
                    logger.warning(f"Could not parse course {class_data.get('crseId')}: {e}")
                    
        except Exception as e:
            logger.error(f"Could not load {file_path}: {e}")
    
    logger.info(f"Loaded {len(courses)} total courses for validation testing")
    return courses


def test_validation_modes():
    """Test both strict and non-strict validation modes"""
    
    courses = load_fa25_data()
    if not courses:
        logger.error("No courses loaded - cannot run validation test")
        return
    
    logger.info(f"Testing validation on {len(courses)} FA25 courses")
    
    # Test strict validation mode
    logger.info("\n=== STRICT VALIDATION MODE ===")
    strict_tracker = DataQualityTracker()
    strict_failures = []
    
    for i, raw_course in enumerate(courses[:20]):  # Test first 20 courses
        course_code = f"{raw_course.subject} {raw_course.catalogNbr}"
        
        try:
            # Try strict validation
            clean_course = CleanCourse.from_raw(raw_course, "FA25", strict_mode=True)
            logger.info(f"✓ PASS: {course_code}")
            
        except ValueError as e:
            logger.error(f"✗ FAIL: {course_code} - {e}")
            strict_failures.append((course_code, str(e)))
            
            # Also run validation to collect metrics
            validator = BusinessRuleValidator(strict_mode=False)
            result = validator.validate_course(raw_course, "FA25")
            strict_tracker.record_validation(result)
        except Exception as e:
            logger.error(f"✗ ERROR: {course_code} - Unexpected error: {e}")
            strict_failures.append((course_code, f"Unexpected error: {e}"))
    
    # Test non-strict validation mode  
    logger.info("\n=== NON-STRICT VALIDATION MODE ===")
    nonstrict_tracker = DataQualityTracker()
    
    for raw_course in courses[:20]:  # Test first 20 courses
        course_code = f"{raw_course.subject} {raw_course.catalogNbr}"
        
        try:
            # Non-strict mode - should always succeed but track issues
            validator = BusinessRuleValidator(strict_mode=False)
            result = validator.validate_course(raw_course, "FA25")
            nonstrict_tracker.record_validation(result)
            
            clean_course = CleanCourse.from_raw(raw_course, "FA25", strict_mode=False)
            
            if result.issues:
                issue_summary = f"{len(result.critical_issues)} critical, {len(result.warning_issues)} warning"
                logger.info(f"⚠ PASS with issues: {course_code} ({issue_summary})")
            else:
                logger.info(f"✓ PASS: {course_code}")
                
        except Exception as e:
            logger.error(f"✗ ERROR: {course_code} - {e}")
    
    # Generate quality reports
    logger.info("\n=== VALIDATION SUMMARY ===")
    
    if strict_failures:
        logger.info(f"Strict mode failures: {len(strict_failures)}")
        for course_code, error in strict_failures[:5]:  # Show first 5
            logger.info(f"  {course_code}: {error}")
        if len(strict_failures) > 5:
            logger.info(f"  ... and {len(strict_failures) - 5} more")
    
    logger.info("\nNon-strict mode quality report:")
    nonstrict_tracker.log_quality_summary()
    
    # Detailed quality report
    quality_report = nonstrict_tracker.get_quality_report()
    
    logger.info("\nMost problematic fields:")
    for field, count in quality_report['top_problematic_fields'][:10]:
        logger.info(f"  {field}: {count} issues")
    
    if quality_report['problematic_courses']:
        logger.info("\nMost problematic courses:")
        for course in quality_report['problematic_courses'][:5]:
            logger.info(f"  {course['course_code']}: {course['critical_count']} critical, {course['warning_count']} warning")


def analyze_prerequisite_quality():
    """Analyze prerequisite parsing quality specifically"""
    courses = load_fa25_data()
    if not courses:
        return
    
    logger.info(f"\n=== PREREQUISITE QUALITY ANALYSIS ===")
    
    total_courses = len(courses)
    courses_with_prereq_text = 0
    courses_with_parsed_prereqs = 0
    low_confidence_prereqs = 0
    
    confidence_scores = []
    
    for raw_course in courses:
        course_code = f"{raw_course.subject} {raw_course.catalogNbr}"
        
        # Check for prerequisite text
        prereq_text = raw_course.catalogPrereqCoreq or getattr(raw_course, 'catalogPrereq', '') or ''
        if prereq_text and prereq_text.strip():
            courses_with_prereq_text += 1
            
            # Try to parse prerequisites
            try:
                from python.graph_analysis.prereq_parser import safe_parse_prerequisites
                parsed_prereq = safe_parse_prerequisites(prereq_text)
                
                if parsed_prereq.ast:
                    courses_with_parsed_prereqs += 1
                    confidence_scores.append(parsed_prereq.confidence)
                    
                    if parsed_prereq.confidence < 0.8:  # Low confidence threshold
                        low_confidence_prereqs += 1
                        logger.debug(f"Low confidence ({parsed_prereq.confidence:.2f}): {course_code}")
                        
            except Exception as e:
                logger.debug(f"Parse error for {course_code}: {e}")
    
    # Calculate statistics
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
    
    logger.info(f"Total courses: {total_courses}")
    logger.info(f"Courses with prerequisite text: {courses_with_prereq_text} ({courses_with_prereq_text/total_courses*100:.1f}%)")
    logger.info(f"Courses with parsed prerequisites: {courses_with_parsed_prereqs} ({courses_with_parsed_prereqs/total_courses*100:.1f}%)")
    logger.info(f"Low confidence prerequisites: {low_confidence_prereqs} ({low_confidence_prereqs/courses_with_parsed_prereqs*100:.1f}% of parsed)")
    logger.info(f"Average confidence score: {avg_confidence:.3f}")
    
    # Show some examples
    if confidence_scores:
        confidence_scores.sort()
        logger.info(f"Confidence score distribution:")
        logger.info(f"  Min: {min(confidence_scores):.3f}")
        logger.info(f"  25th percentile: {confidence_scores[len(confidence_scores)//4]:.3f}")
        logger.info(f"  Median: {confidence_scores[len(confidence_scores)//2]:.3f}")
        logger.info(f"  75th percentile: {confidence_scores[3*len(confidence_scores)//4]:.3f}")
        logger.info(f"  Max: {max(confidence_scores):.3f}")


if __name__ == "__main__":
    logger.info("Testing strict validation on FA25 course data")
    test_validation_modes()
    analyze_prerequisite_quality()
    logger.info("Validation test complete")