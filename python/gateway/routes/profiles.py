from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from ..models import StudentProfile
from ..services.student_profile_service import StudentProfileService
from ..dependencies import get_redis

class ProfilePatch(BaseModel):
    major: Optional[str] = None
    year: Optional[str] = None
    completed_courses: Optional[List[str]] = Field(default=None)
    current_courses: Optional[List[str]] = Field(default=None)
    interests: Optional[List[str]] = Field(default=None)

security = HTTPBearer()

router = APIRouter(
    prefix="/profiles", 
    tags=["profiles"],
    dependencies=[Depends(security)]
)

def get_service(r=Depends(get_redis)):
    return StudentProfileService(r)

@router.get("/{student_id}", response_model=StudentProfile)
async def get_profile(student_id: str, svc: StudentProfileService = Depends(get_service)):
    # TODO: Add token validation to ensure the user is authorized to access this profile
    profile = await svc.get(student_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@router.put("/{student_id}", response_model=StudentProfile)
async def put_profile(student_id: str, profile: StudentProfile, svc: StudentProfileService = Depends(get_service)):
    # TODO: Add token validation
    if profile.student_id and profile.student_id != student_id:
        raise HTTPException(status_code=400, detail="student_id mismatch between path and body")
    profile.student_id = student_id
    ok = await svc.put(profile)
    if not ok:
        raise HTTPException(status_code=503, detail="Failed to persist profile")
    return profile

@router.patch("/{student_id}", response_model=StudentProfile)
async def patch_profile(student_id: str, updates: ProfilePatch, svc: StudentProfileService = Depends(get_service)):
    # TODO: Add token validation
    prof = await svc.patch(student_id, updates.dict(exclude_unset=True))
    if not prof:
        raise HTTPException(status_code=503, detail="Failed to persist profile")
    return prof
