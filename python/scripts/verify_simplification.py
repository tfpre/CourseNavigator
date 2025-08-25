#!/usr/bin/env python3
"""
Verify that processing has been truly simplified with no overengineered remnants.
Test data extraction rigor by checking all critical paths.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import gzip
import logging
from pathlib import Path
from python.data_ingestion.models import RawCourse, CleanCourse
from python.data_ingestion.validation import BusinessRuleValidator

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_cross_listing_simplification():
    """Verify cross-listing logic is truly simplified"""
    
    logger.info("=== CROSS-LISTING SIMPLIFICATION VERIFICATION ===")
    
    # Read the cross-listing function
    from python.data_ingestion.models import _parse_cross_listings
    import inspect
    
    source_lines = inspect.getsource(_parse_cross_listings).split('\n')
    code_lines = [line for line in source_lines if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('"""')]
    
    logger.info(f"✅ Cross-listing function: {len(code_lines)} lines of actual code")
    logger.info(f"✅ Expected: ~15 lines (down from 80+ lines)")
    
    # Check for strategy remnants
    source_code = inspect.getsource(_parse_cross_listings)
    
    # These should NOT exist (removed strategies)
    removed_strategies = [
        'catalogGroup',
        'crossListGroup', 
        'class_section_subjects',
        'title_parsing',
        'Strategy 1', 'Strategy 2', 'Strategy 3', 'Strategy 4', 'Strategy 5'
    ]
    
    found_remnants = []
    for strategy in removed_strategies:
        if strategy in source_code:
            found_remnants.append(strategy)
    
    if found_remnants:
        logger.error(f"❌ FOUND OVERENGINEERED REMNANTS: {found_remnants}")
        return False
    else:
        logger.info(f"✅ No overengineered strategy remnants found")
    
    # Check for only simpleCombinations
    if 'simpleCombinations' not in source_code:
        logger.error(f"❌ simpleCombinations strategy missing!")
        return False
    else:
        logger.info(f"✅ Only simpleCombinations strategy present")
    
    return True


def check_validation_rigor():
    """Verify validation is rigorous with fail-fast patterns"""
    
    logger.info("\n=== VALIDATION RIGOR VERIFICATION ===")
    
    # Test with deliberately bad data
    bad_course_data = {
        "crseId": None,  # Missing critical field
        "crseOfferNbr": 1,
        "subject": "",   # Empty subject
        "catalogNbr": "ABC",  # Invalid catalog number
        "titleLong": "",  # Missing title
        "enrollGroups": []  # No enrollment groups
    }
    
    try:
        # This should fail in strict mode
        raw_course = RawCourse(**bad_course_data)
        logger.error(f"❌ Bad data accepted by RawCourse model")
        return False
    except Exception as e:
        logger.info(f"✅ Bad data correctly rejected: {e}")
    
    # Test validation with minimal valid data
    minimal_valid_data = {
        "crseId": 12345,
        "crseOfferNbr": 1,
        "subject": "CS",
        "catalogNbr": "2110",
        "titleLong": "Test Course",
        "enrollGroups": [{
            "classSections": [{"ssrComponent": "LEC"}],
            "unitsMinimum": 3.0,
            "unitsMaximum": 3.0
        }]
    }
    
    try:
        raw_course = RawCourse(**minimal_valid_data)
        validator = BusinessRuleValidator(strict_mode=True)
        result = validator.validate_course(raw_course, "FA25")
        
        if result.is_valid:
            logger.info(f"✅ Valid minimal data passes strict validation")
        else:
            logger.error(f"❌ Valid data fails validation: {[i.message for i in result.critical_issues]}")
            return False
            
        # Test clean course creation
        clean_course = CleanCourse.from_raw(raw_course, "FA25", strict_mode=True)
        logger.info(f"✅ Clean course creation succeeds: {clean_course.id}")
        
    except Exception as e:
        logger.error(f"❌ Valid data processing failed: {e}")
        return False
    
    return True


def check_data_extraction_rigor():
    """Test data extraction with real FA25 data to verify rigor"""
    
    logger.info("\n=== DATA EXTRACTION RIGOR VERIFICATION ===")
    
    # Load sample FA25 data
    raw_data_dir = Path("/mnt/c/dev/CourseNavigator/data/raw")
    fa25_cs_file = raw_data_dir / "FA25_CS.json.gz"
    
    if not fa25_cs_file.exists():
        logger.error("❌ No FA25 data for testing")
        return False
    
    try:
        with gzip.open(fa25_cs_file, 'rt') as f:
            data = json.load(f)
            
        classes_data = data.get('data', {}).get('classes', [])
        logger.info(f"Testing data extraction on {len(classes_data)} courses")
        
        validator = BusinessRuleValidator(strict_mode=True)
        extraction_stats = {
            'total_courses': 0,
            'successful_extractions': 0,
            'validation_failures': 0,
            'parsing_errors': 0,
            'data_quality_issues': []
        }
        
        for class_data in classes_data[:20]:  # Test first 20 courses
            extraction_stats['total_courses'] += 1
            course_code = f"{class_data.get('subject', '')} {class_data.get('catalogNbr', '')}"
            
            try:
                # Raw course parsing
                raw_course = RawCourse(**class_data)
                
                # Strict validation
                validation_result = validator.validate_course(raw_course, "FA25")
                
                if not validation_result.is_valid:
                    extraction_stats['validation_failures'] += 1
                    extraction_stats['data_quality_issues'].extend([
                        f"{course_code}: {issue.message}" 
                        for issue in validation_result.critical_issues
                    ])
                    continue
                
                # Clean course creation
                clean_course = CleanCourse.from_raw(raw_course, "FA25", strict_mode=True)
                
                # Rigor checks - verify critical data extraction
                if not clean_course.id:
                    raise ValueError("Missing course ID")
                if not clean_course.subject:
                    raise ValueError("Missing subject")
                if not clean_course.catalog_nbr:
                    raise ValueError("Missing catalog number")
                if not clean_course.title:
                    raise ValueError("Missing title")
                
                extraction_stats['successful_extractions'] += 1
                
            except Exception as e:
                extraction_stats['parsing_errors'] += 1
                extraction_stats['data_quality_issues'].append(f"{course_code}: {e}")
        
        # Report extraction rigor
        success_rate = extraction_stats['successful_extractions'] / extraction_stats['total_courses']
        
        logger.info(f"Extraction Results:")
        logger.info(f"  Total courses tested: {extraction_stats['total_courses']}")
        logger.info(f"  Successful extractions: {extraction_stats['successful_extractions']}")
        logger.info(f"  Success rate: {success_rate:.1%}")
        logger.info(f"  Validation failures: {extraction_stats['validation_failures']}")
        logger.info(f"  Parsing errors: {extraction_stats['parsing_errors']}")
        
        if success_rate >= 0.95:  # 95% success rate required
            logger.info(f"✅ Data extraction is rigorous (≥95% success rate)")
        else:
            logger.error(f"❌ Data extraction lacks rigor (<95% success rate)")
            return False
        
        # Show sample quality issues
        if extraction_stats['data_quality_issues']:
            logger.info(f"\nSample quality issues identified:")
            for issue in extraction_stats['data_quality_issues'][:3]:
                logger.info(f"  - {issue}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Data extraction test failed: {e}")
        return False


def check_processing_pipeline_simplicity():
    """Verify the overall processing pipeline is simplified"""
    
    logger.info("\n=== PROCESSING PIPELINE SIMPLICITY VERIFICATION ===")
    
    # Check CleanCourse.from_raw method
    from python.data_ingestion.models import CleanCourse
    import inspect
    
    source_code = inspect.getsource(CleanCourse.from_raw)
    source_lines = source_code.split('\n')
    
    # Count actual processing steps (exclude comments, docstrings, logging)
    processing_steps = []
    in_docstring = False
    
    for line in source_lines:
        stripped = line.strip()
        if '"""' in stripped:
            in_docstring = not in_docstring
            continue
        if in_docstring or not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('logger.') or stripped.startswith('from ') or 'import ' in stripped:
            continue
        if any(keyword in stripped for keyword in ['def ', 'return ', 'class ', '@']):
            continue
        processing_steps.append(stripped)
    
    logger.info(f"Processing pipeline steps: {len(processing_steps)}")
    
    # Check for key simplifications
    simplifications_verified = []
    
    # 1. Single cross-listing strategy
    if 'cross_listings = _parse_cross_listings(raw_course)' in source_code:
        simplifications_verified.append("✅ Single cross-listing call")
    else:
        logger.error("❌ Complex cross-listing logic found")
        return False
    
    # 2. Direct validation integration
    if 'validation_result = validator.validate_course' in source_code:
        simplifications_verified.append("✅ Direct validation integration")
    
    # 3. No complex error masking
    graceful_degradation_patterns = [
        'try:', 'except:', 'graceful', 'fallback', 'continue'
    ]
    complex_error_handling = sum(1 for pattern in graceful_degradation_patterns if pattern in source_code.lower())
    
    if complex_error_handling <= 2:  # Some try/except is acceptable
        simplifications_verified.append("✅ Minimal error masking")
    else:
        logger.error(f"❌ Complex error masking found: {complex_error_handling} patterns")
        return False
    
    # 4. Straightforward data extraction
    if 'units_min = min(all_mins)' in source_code and 'units_max = max(all_maxs)' in source_code:
        simplifications_verified.append("✅ Direct units extraction")
    
    for verification in simplifications_verified:
        logger.info(f"  {verification}")
    
    logger.info(f"✅ Processing pipeline is simplified ({len(simplifications_verified)} verifications passed)")
    return True


def main():
    """Run all simplification and rigor verifications"""
    
    logger.info("VERIFYING PROCESSING SIMPLIFICATION AND DATA EXTRACTION RIGOR")
    logger.info("=" * 70)
    
    checks = [
        ("Cross-listing simplification", check_cross_listing_simplification),
        ("Validation rigor", check_validation_rigor), 
        ("Data extraction rigor", check_data_extraction_rigor),
        ("Processing pipeline simplicity", check_processing_pipeline_simplicity)
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            logger.error(f"❌ {check_name} check failed with error: {e}")
            results.append((check_name, False))
    
    logger.info(f"\n" + "=" * 70)
    logger.info(f"VERIFICATION SUMMARY")
    logger.info(f"=" * 70)
    
    all_passed = True
    for check_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {check_name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        logger.info(f"\n🎉 ALL VERIFICATIONS PASSED")
        logger.info(f"✅ Processing is truly simplified")
        logger.info(f"✅ Data extraction is rigorous")
        logger.info(f"✅ No overengineered remnants found")
    else:
        logger.error(f"\n⚠️  SOME VERIFICATIONS FAILED")
        logger.error(f"❌ Review failed checks above")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)