"""
Demo Mode Controller - Deterministic Behavior for Presentations

Implements Ground Truth: Information Reliability
- Ensures predictable responses during demos
- Controls data sources and fallback behavior  
- Provides demo-specific feature toggles
"""

import os
import logging
from typing import Dict, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

class DemoMode:
    """Global demo mode controller for consistent behavior"""
    
    _enabled = None
    _demo_profile_id = None
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if demo mode is active"""
        if cls._enabled is None:
            cls._enabled = os.getenv("DEMO_MODE", "false").lower() == "true"
            if cls._enabled:
                logger.info("🎬 Demo mode activated - using deterministic data")
        return cls._enabled
    
    @classmethod 
    def get_demo_profile(cls) -> Optional[str]:
        """Get current demo profile ID"""
        if cls._demo_profile_id is None:
            cls._demo_profile_id = os.getenv("DEMO_PROFILE_ID", "demo_cs_sophomore")
        return cls._demo_profile_id if cls.is_enabled() else None
    
    @classmethod
    def should_use_mock_data(cls, service_name: str) -> bool:
        """Determine if service should use mock data in demo mode"""
        if not cls.is_enabled():
            return False
            
        # Services that should always use demo data in demo mode
        demo_services = {
            "professor_intelligence",
            "course_difficulty", 
            "enrollment_prediction",
            "conflict_detection",
            "grades_service"
        }
        
        return service_name in demo_services
    
    @classmethod
    def get_demo_config(cls) -> Dict[str, Any]:
        """Get demo-specific configuration overrides"""
        if not cls.is_enabled():
            return {}
            
        return {
            "disable_external_apis": True,
            "use_deterministic_fallbacks": True, 
            "force_enhanced_mock": True,
            "cache_bypass": os.getenv("DEMO_CACHE_BYPASS", "false").lower() == "true",
            "response_delay_ms": int(os.getenv("DEMO_RESPONSE_DELAY", "0")),
            "golden_path_mode": os.getenv("DEMO_GOLDEN_PATH", "false").lower() == "true"
        }

def demo_mode_override(service_name: str):
    """Decorator to override service behavior in demo mode"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if DemoMode.should_use_mock_data(service_name):
                logger.debug(f"🎬 Demo mode override for {service_name}.{func.__name__}")
                # Services can check DemoMode.is_enabled() internally
                # This decorator mainly serves as a marker
            return await func(*args, **kwargs)
        return wrapper
    return decorator