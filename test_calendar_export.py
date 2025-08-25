#!/usr/bin/env python3
"""
Test calendar export functionality
"""

import sys
import os
sys.path.append('python')

from python.gateway.services.ical_export_service import ICalExportService

def test_ical_generation():
    """Test iCal generation for demo courses"""
    
    service = ICalExportService()
    
    # Test course codes
    courses = ["CS 4701", "CS 2110", "CS 3110"] 
    student_name = "Alex Chen"
    
    print(f"🗓️  Generating calendar for: {courses}")
    print(f"   Student: {student_name}")
    print()
    
    # Generate iCal content
    ical_content = service.export_from_course_codes(courses, student_name)
    
    print("📅 Generated iCal content:")
    print("=" * 50)
    print(ical_content)
    print("=" * 50)
    print()
    
    # Validate basic iCal structure
    lines = ical_content.split('\n')
    
    # Check header/footer
    has_begin = any(line.startswith('BEGIN:VCALENDAR') for line in lines)
    has_end = any(line.startswith('END:VCALENDAR') for line in lines)
    
    # Count events
    event_count = sum(1 for line in lines if line.startswith('BEGIN:VEVENT'))
    
    print(f"✅ Validation results:")
    print(f"   Calendar structure: {'✓' if has_begin and has_end else '✗'}")
    print(f"   Events generated: {event_count}")
    print(f"   Total lines: {len(lines)}")
    
    # Check for course codes in content
    for course in courses:
        found = any(course in line for line in lines)
        print(f"   Contains {course}: {'✓' if found else '✗'}")

if __name__ == "__main__":
    test_ical_generation()