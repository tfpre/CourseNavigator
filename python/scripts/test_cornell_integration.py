#!/usr/bin/env python3
"""
Test Cornell Course Roster API Integration
Validates the complete pipeline from API to Neo4j import
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from cornell_api.data_pipeline import CornellDataPipeline, fetch_cornell_courses_quick_test

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_api_connection():
    """Test basic Cornell API connectivity"""
    logger.info("Testing Cornell API connection...")
    
    from cornell_api.client import CornellAPIClient
    
    try:
        async with CornellAPIClient("SP25") as client:
            subjects = await client.get_subjects()
            logger.info(f"✅ API Connection successful: {len(subjects)} subjects available")
            
            # Test fetching CS courses
            cs_courses = await client.get_courses_for_subject("CS")
            logger.info(f"✅ CS courses fetched: {len(cs_courses)} courses")
            
            # Show sample course
            if cs_courses:
                sample = cs_courses[0]
                logger.info(f"   Sample: {sample.course_code} - {sample.title_short}")
                if sample.prerequisite_text:
                    logger.info(f"   Prerequisites: {sample.prerequisite_text}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ API Connection failed: {e}")
        return False

async def test_prerequisite_parsing():
    """Test prerequisite parsing functionality"""
    logger.info("Testing prerequisite parsing...")
    
    from cornell_api.prerequisite_parser import parse_cornell_prerequisites
    
    test_cases = [
        "Prerequisite: CS 1110 or CS 1112 or equivalent course on programming in a procedural language.",
        "Prerequisites: CS 2110 and MATH 1920.",
        "Corequisite: MATH 1110, MATH 1910, or equivalent.",
        "Prerequisite: CS 2800 or MATH 2300, and CS 2110.",
        ""  # Empty case
    ]
    
    for i, test_text in enumerate(test_cases, 1):
        try:
            result = parse_cornell_prerequisites(test_text)
            logger.info(f"✅ Test {i}: Parsed {len(result.prerequisites)} prerequisites, confidence: {result.parsing_confidence:.2f}")
            
            for prereq in result.prerequisites:
                courses_str = ", ".join(prereq.course_codes)
                logger.info(f"   - {prereq.type.value.upper()}: {courses_str} ({prereq.relation})")
                
        except Exception as e:
            logger.error(f"❌ Test {i} failed: {e}")
    
    return True

async def test_small_data_pipeline():
    """Test the complete pipeline with a small dataset"""
    logger.info("Testing data pipeline with CS and MATH courses...")
    
    try:
        # Run pipeline with limited subjects for testing
        result = await fetch_cornell_courses_quick_test(["CS", "MATH"])
        
        if result["success"]:
            logger.info("✅ Data pipeline completed successfully")
            logger.info(f"   📊 Courses fetched: {result['courses_fetched']}")
            logger.info(f"   📊 Subjects processed: {result['subjects_processed']}")
            logger.info(f"   📊 Prerequisites parsed: {result['prerequisites_parsed']}")
            logger.info(f"   📊 Prerequisite edges: {result['prerequisite_edges']}")
            logger.info(f"   📊 Duration: {result['pipeline_duration_seconds']:.2f}s")
            logger.info(f"   📊 Import script: {result['import_script_path']}")
            
            return True
        else:
            logger.error(f"❌ Data pipeline failed: {result['error']}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Data pipeline test failed: {e}")
        return False

async def main():
    """Run all Cornell API integration tests"""
    logger.info("🚀 Starting Cornell Course Roster API Integration Tests")
    logger.info(f"📅 Test run: {datetime.now().isoformat()}")
    
    tests = [
        ("API Connection", test_api_connection),
        ("Prerequisite Parsing", test_prerequisite_parsing), 
        ("Small Data Pipeline", test_small_data_pipeline)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running: {test_name}")
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            logger.error(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info(f"\n📋 Test Results Summary:")
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"  {status}: {test_name}")
    
    logger.info(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Cornell API integration is ready.")
        return True
    else:
        logger.error("🚨 Some tests failed. Check logs above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)