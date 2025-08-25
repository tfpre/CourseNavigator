#!/usr/bin/env python3
"""
Quick test for conflict detection service - demo validation
"""

import sys
import os
sys.path.append('python')

from python.gateway.services.conflict_detection_service import ConflictDetectionService

def test_demo_conflict():
    """Test the demo CS 4780 vs CS 4820 conflict"""
    
    service = ConflictDetectionService()
    
    # Test the golden conflict from demo dataset
    courses = ["CS 4780", "CS 4820"]
    
    print(f"🔍 Testing conflict detection for: {courses}")
    print()
    
    # Detect conflicts
    conflicts = service.detect_conflicts(courses)
    
    if conflicts:
        print(f"⚠️  Detected {len(conflicts)} conflict(s):")
        for conflict in conflicts:
            print(f"   - {conflict.course_a} vs {conflict.course_b}")
            print(f"     Type: {conflict.conflict_type.value}")
            print(f"     Description: {conflict.description}")
            print(f"     Severity: {conflict.severity}")
            print()
    else:
        print("✅ No conflicts detected")
        print()
    
    # Test backup suggestions
    backup_plans = service.suggest_backup_plans(conflicts)
    
    if backup_plans:
        print("💡 Backup plan suggestions:")
        for course, plans in backup_plans.items():
            print(f"   For {course}:")
            for plan in plans:
                print(f"     → {plan.backup_course}: {plan.rationale}")
                print(f"       Difficulty: {plan.difficulty_delta}")
            print()
    
    # Test formatting
    print("📄 Formatted output:")
    print(service.format_conflict_summary(conflicts))
    print(service.format_backup_suggestions(backup_plans))

if __name__ == "__main__":
    test_demo_conflict()