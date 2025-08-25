#!/usr/bin/env python3
"""
Analyze cross-listing data to identify which parsing strategy actually works.

This will guide simplification from 5 strategies to 1 robust approach.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import gzip
import logging
from pathlib import Path
from collections import defaultdict
from python.data_ingestion.models import RawCourse

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def analyze_cross_listing_strategies():
    """Analyze which cross-listing strategies are actually used in real data"""
    
    # Load raw FA25 data
    raw_data_dir = Path("/mnt/c/dev/CourseNavigator/data/raw")
    fa25_files = list(raw_data_dir.glob("FA25_*.json.gz"))
    
    strategy_stats = {
        'catalogGroup': 0,
        'crossListGroup': 0, 
        'simpleCombinations': 0,
        'class_section_subjects': 0,
        'title_parsing': 0,
        'no_cross_listings': 0
    }
    
    cross_listing_examples = {}
    total_courses = 0
    
    for file_path in fa25_files:
        logger.info(f"Analyzing {file_path.name}")
        
        try:
            with gzip.open(file_path, 'rt') as f:
                data = json.load(f)
                
            classes_data = data.get('data', {}).get('classes', [])
            
            for class_data in classes_data:
                total_courses += 1
                course_code = f"{class_data.get('subject', 'UNKNOWN')} {class_data.get('catalogNbr', 'UNKNOWN')}"
                
                # Strategy 1: catalogGroup field
                catalog_group = class_data.get('catalogGroup')
                if catalog_group and isinstance(catalog_group, list) and len(catalog_group) > 0:
                    strategy_stats['catalogGroup'] += 1
                    cross_listing_examples['catalogGroup'] = course_code
                    logger.debug(f"catalogGroup found in {course_code}: {catalog_group}")
                    continue
                
                # Strategy 2: crossListGroup field
                cross_list_group = class_data.get('crossListGroup')
                if cross_list_group and isinstance(cross_list_group, list) and len(cross_list_group) > 0:
                    strategy_stats['crossListGroup'] += 1
                    cross_listing_examples['crossListGroup'] = course_code
                    logger.debug(f"crossListGroup found in {course_code}: {cross_list_group}")
                    continue
                
                # Strategy 3: simpleCombinations field
                found_simple_combinations = False
                enroll_groups = class_data.get('enrollGroups', [])
                for enroll_group in enroll_groups:
                    simple_combinations = enroll_group.get('simpleCombinations', [])
                    if simple_combinations and len(simple_combinations) > 0:
                        strategy_stats['simpleCombinations'] += 1
                        cross_listing_examples['simpleCombinations'] = course_code
                        logger.debug(f"simpleCombinations found in {course_code}: {simple_combinations}")
                        found_simple_combinations = True
                        break
                if found_simple_combinations:
                    continue
                
                # Strategy 4: Different subjects in class sections
                found_different_subjects = False
                main_subject = class_data.get('subject')
                for enroll_group in enroll_groups:
                    for class_section in enroll_group.get('classSections', []):
                        section_subject = class_section.get('subject')
                        if section_subject and section_subject != main_subject:
                            strategy_stats['class_section_subjects'] += 1
                            cross_listing_examples['class_section_subjects'] = course_code
                            logger.debug(f"Different subject in section for {course_code}: {section_subject} vs {main_subject}")
                            found_different_subjects = True
                            break
                    if found_different_subjects:
                        break
                if found_different_subjects:
                    continue
                
                # Strategy 5: Title parsing
                title = class_data.get('titleLong', '')
                if ('also listed as' in title.lower() or 'cross-listed' in title.lower()):
                    strategy_stats['title_parsing'] += 1
                    cross_listing_examples['title_parsing'] = course_code
                    logger.debug(f"Cross-listing text in title for {course_code}: {title}")
                    continue
                
                # No cross-listing found
                strategy_stats['no_cross_listings'] += 1
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    
    # Print analysis results
    logger.info(f"\n=== CROSS-LISTING STRATEGY ANALYSIS ===")
    logger.info(f"Total courses analyzed: {total_courses}")
    logger.info(f"")
    
    for strategy, count in strategy_stats.items():
        percentage = (count / total_courses * 100) if total_courses > 0 else 0
        logger.info(f"{strategy}: {count} courses ({percentage:.1f}%)")
        if strategy in cross_listing_examples:
            logger.info(f"  Example: {cross_listing_examples[strategy]}")
    
    # Find actual cross-listing examples
    logger.info(f"\n=== DETAILED CROSS-LISTING EXAMPLES ===")
    
    # Look for known cross-listed courses
    known_cross_listed = ['CS 2110', 'CS 2112', 'CS 4750', 'MATH 4250']
    
    for file_path in fa25_files:
        try:
            with gzip.open(file_path, 'rt') as f:
                data = json.load(f)
                
            classes_data = data.get('data', {}).get('classes', [])
            
            for class_data in classes_data:
                course_code = f"{class_data.get('subject', '')} {class_data.get('catalogNbr', '')}"
                
                if course_code in known_cross_listed:
                    logger.info(f"\nDetailed analysis for {course_code}:")
                    logger.info(f"  catalogGroup: {class_data.get('catalogGroup', 'None')}")
                    logger.info(f"  crossListGroup: {class_data.get('crossListGroup', 'None')}")
                    
                    # Check simpleCombinations
                    for i, enroll_group in enumerate(class_data.get('enrollGroups', [])):
                        simple_combos = enroll_group.get('simpleCombinations', [])
                        if simple_combos:
                            logger.info(f"  enrollGroups[{i}].simpleCombinations: {simple_combos}")
                    
                    logger.info(f"  titleLong: {class_data.get('titleLong', 'None')}")
                    
        except Exception as e:
            logger.error(f"Error in detailed analysis: {e}")


def test_simplified_cross_listing():
    """Test a simplified cross-listing approach based on analysis"""
    
    def simplified_parse_cross_listings(raw_course_data):
        """
        Simplified cross-listing parsing with single strategy.
        Based on analysis of real Cornell data.
        """
        cross_listings = []
        main_subject = raw_course_data.get('subject', '')
        main_catalog = raw_course_data.get('catalogNbr', '')
        
        # Primary strategy: simpleCombinations field (most reliable)
        for enroll_group in raw_course_data.get('enrollGroups', []):
            simple_combinations = enroll_group.get('simpleCombinations', [])
            for combo in simple_combinations:
                if isinstance(combo, dict):
                    subject = combo.get('subject', '')
                    catalog_nbr = combo.get('catalogNbr', '')
                    if subject and catalog_nbr:
                        # Don't include the course as a cross-listing of itself
                        if not (subject == main_subject and catalog_nbr == main_catalog):
                            cross_listings.append(f"{subject} {catalog_nbr}")
        
        return sorted(list(set(cross_listings)))
    
    # Test on sample data
    logger.info(f"\n=== TESTING SIMPLIFIED APPROACH ===")
    
    # Load sample data and test simplified parsing
    raw_data_dir = Path("/mnt/c/dev/CourseNavigator/data/raw")
    fa25_cs_file = raw_data_dir / "FA25_CS.json.gz"
    
    if fa25_cs_file.exists():
        try:
            with gzip.open(fa25_cs_file, 'rt') as f:
                data = json.load(f)
                
            classes_data = data.get('data', {}).get('classes', [])
            
            cross_listing_count = 0
            for class_data in classes_data:
                course_code = f"{class_data.get('subject', '')} {class_data.get('catalogNbr', '')}"
                cross_listings = simplified_parse_cross_listings(class_data)
                
                if cross_listings:
                    cross_listing_count += 1
                    logger.info(f"{course_code}: {cross_listings}")
            
            logger.info(f"\nSimplified approach found cross-listings for {cross_listing_count} out of {len(classes_data)} CS courses")
            
        except Exception as e:
            logger.error(f"Error testing simplified approach: {e}")


if __name__ == "__main__":
    logger.info("Analyzing cross-listing strategies in Cornell data")
    analyze_cross_listing_strategies()
    test_simplified_cross_listing()
    logger.info("Analysis complete")