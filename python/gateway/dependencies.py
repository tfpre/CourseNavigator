"""
FastAPI dependencies to avoid circular imports
"""
import os
import redis.asyncio as redis
from fastapi import HTTPException


redis_client = None

async def get_redis():
    """Dependency to get Redis client instance"""
    global redis_client
    
    if redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            await redis_client.ping()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Redis service not available: {e}"
            )
    
    return redis_client