"""
Calendar Export Routes - iCal generation for course schedules

Implements Ground Truth: Actionable Prioritization
- Export course schedules as .ics files
- Support for backup plans and optimized schedules
- Demo-mode integration
"""

from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import Response as FastAPIResponse
from typing import List, Optional
import logging

from ..services.ical_export_service import ICalExportService
from ..services.demo_mode import DemoMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/export.ics")
async def export_course_schedule(
    courses: List[str] = Query(..., description="List of course codes to export"),
    student_name: Optional[str] = Query("Student", description="Student name for calendar title"),
    format: str = Query("ical", description="Export format (currently only 'ical')")
):
    """
    Export course schedule as iCal (.ics) file
    
    Example: /calendar/export.ics?courses=CS 4780&courses=CS 4701&student_name=Alex Chen
    """
    
    try:
        if not courses:
            raise HTTPException(status_code=400, detail="At least one course code is required")
        
        # Clean and validate course codes
        clean_courses = []
        for course in courses:
            course = course.strip().upper()
            if not course:
                continue
            clean_courses.append(course)
        
        if not clean_courses:
            raise HTTPException(status_code=400, detail="No valid course codes provided")
        
        logger.info(f"Exporting calendar for courses: {clean_courses}")
        
        # Generate iCal content
        ical_service = ICalExportService()
        ical_content = ical_service.export_from_course_codes(clean_courses, student_name)
        
        # Create filename
        safe_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_name}_Schedule_Fall2024.ics" if safe_name else "Course_Schedule.ics"
        
        # Return as downloadable file
        return Response(
            content=ical_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/calendar; charset=utf-8"
            }
        )
        
    except Exception as e:
        logger.error(f"Calendar export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate calendar: {str(e)}")

@router.post("/export-backup-plan")
async def export_backup_plan_schedule(
    original_courses: List[str],
    backup_courses: List[str], 
    student_name: Optional[str] = "Student"
):
    """
    Export schedule with backup courses replacing conflicted ones
    
    Body:
    {
        "original_courses": ["CS 4780", "CS 4820"],
        "backup_courses": ["CS 4701", "CS 4810"],
        "student_name": "Alex Chen"
    }
    """
    
    try:
        # For demo purposes, create optimized schedule
        # In production, this would involve more sophisticated conflict resolution
        
        # Remove duplicates and combine
        all_courses = list(set(backup_courses))  # Prefer backup courses
        
        # Add original courses that don't have backups
        backup_set = set(backup_courses)
        for orig in original_courses:
            if orig not in backup_set:
                all_courses.append(orig)
        
        logger.info(f"Exporting backup plan schedule: {all_courses}")
        
        # Generate iCal
        ical_service = ICalExportService()
        ical_content = ical_service.export_from_course_codes(all_courses, student_name)
        
        filename = f"{student_name}_Backup_Plan.ics" if student_name != "Student" else "Backup_Plan_Schedule.ics"
        
        return Response(
            content=ical_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/calendar; charset=utf-8"
            }
        )
        
    except Exception as e:
        logger.error(f"Backup plan export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate backup plan calendar: {str(e)}")

@router.get("/demo-schedule")
async def get_demo_schedule():
    """
    Get a predefined demo schedule for presentations
    
    Returns the golden path schedule from demo dataset
    """
    
    if not DemoMode.is_enabled():
        raise HTTPException(status_code=403, detail="Demo schedules only available in demo mode")
    
    try:
        # Golden path demo schedule
        demo_courses = ["CS 4701", "CS 2110", "CS 3110"]  # Conflict-free combination
        student_name = "Alex Chen"  # Demo student name
        
        ical_service = ICalExportService()
        ical_content = ical_service.export_from_course_codes(demo_courses, student_name)
        
        return Response(
            content=ical_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": "attachment; filename=Demo_Golden_Path_Schedule.ics",
                "Content-Type": "text/calendar; charset=utf-8"
            }
        )
        
    except Exception as e:
        logger.error(f"Demo schedule export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate demo schedule: {str(e)}")

@router.get("/test-ical")
async def test_ical_generation():
    """Test endpoint for iCal generation - returns sample content"""
    
    try:
        ical_service = ICalExportService()
        test_courses = ["CS 4780", "CS 2110"]
        ical_content = ical_service.export_from_course_codes(test_courses, "Test Student")
        
        return {"ical_content": ical_content, "courses": test_courses}
        
    except Exception as e:
        logger.error(f"Test iCal generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate test iCal: {str(e)}")