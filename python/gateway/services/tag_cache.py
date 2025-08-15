# Versioned Tag Cache - Avoid Delete Storms
# Implements expert friend's recommendation: increment tag versions instead of deleting keys

import json
import hashlib
from typing import Any, Callable, Dict, Optional, Union
import logging
import time

logger = logging.getLogger(__name__)

class TagCache:
    """
    Versioned tag-based caching that prevents delete storms.
    
    Key Features:
    - Cache keys include tag version: `graphctx:v42:hash`
    - Invalidation increments tag version, old keys expire naturally
    - No explicit deletes, better Redis performance
    - Perfect for graph data that changes infrequently
    
    Pattern from expert friend's architecture review.
    """
    
    def __init__(self, redis_client, ttl_s: int = 3600):
        self.redis = redis_client
        self.ttl = ttl_s
    
    async def _get_tag_version(self, tag: str) -> int:
        """Get current version for a tag, initializing to 1 if not exists"""
        version_key = f"tagver:{tag}"
        try:
            version = await self.redis.get(version_key)
            if version is None:
                await self.redis.set(version_key, 1)
                return 1
            return int(version)
        except Exception as e:
            logger.exception(f"Failed to get tag version for {tag}: {e}")
            return 1  # Default version
    
    async def get_or_set(
        self, 
        tag: str, 
        key_fields: Dict[str, Any], 
        loader: Callable[[], Any],
        custom_ttl: Optional[int] = None
    ) -> Any:
        """
        Get cached value or load and cache it.
        
        Args:
            tag: Cache tag for versioning (e.g., "graphctx", "professors")
            key_fields: Dict of fields to create unique key hash
            loader: Async function to load data if cache miss
            custom_ttl: Override default TTL for this entry
        
        Returns:
            Cached or freshly loaded data with cache_hit metadata
        """
        try:
            # Build versioned cache key
            version = await self._get_tag_version(tag)
            key_hash = self._hash_key_fields(key_fields)
            cache_key = f"{tag}:v{version}:{key_hash}"
            
            # Try cache hit first
            cached_value = await self.redis.get(cache_key)
            if cached_value is not None:
                try:
                    data = json.loads(cached_value)
                    # Add cache hit metadata
                    if isinstance(data, dict):
                        data["cache_hit"] = True
                    return data
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse cached JSON for key {cache_key}")
            
            # Cache miss - load fresh data
            fresh_data = await loader()
            if fresh_data is not None:
                # Cache the fresh data
                try:
                    serialized = json.dumps(fresh_data, default=self._json_serializer)
                    ttl = custom_ttl or self.ttl
                    await self.redis.setex(cache_key, ttl, serialized)
                    logger.debug(f"Cached data for {cache_key} with TTL {ttl}s")
                except Exception as e:
                    logger.warning(f"Failed to cache data for {cache_key}: {e}")
            
            # Add cache miss metadata
            result = fresh_data or {}
            if isinstance(result, dict):
                result["cache_hit"] = False
            
            return result
            
        except Exception as e:
            logger.exception(f"Cache operation failed for tag {tag}: {e}")
            # Fallback to loader on cache errors
            return await loader()
    
    async def invalidate_tag(self, tag: str) -> bool:
        """
        Invalidate all cache entries for a tag by incrementing its version.
        Old keys will expire naturally via TTL.
        """
        try:
            version_key = f"tagver:{tag}"
            new_version = await self.redis.incr(version_key)
            logger.info(f"Invalidated tag '{tag}' -> version {new_version}")
            return True
        except Exception as e:
            logger.exception(f"Failed to invalidate tag {tag}: {e}")
            return False
    
    async def get_tag_stats(self, tag: str) -> Dict[str, Any]:
        """Get statistics for a cache tag"""
        try:
            version = await self._get_tag_version(tag)
            
            # Count keys for current version (approximate)
            pattern = f"{tag}:v{version}:*"
            keys = await self.redis.keys(pattern)
            
            return {
                "tag": tag,
                "current_version": version,
                "approximate_keys": len(keys) if keys else 0,
                "ttl_seconds": self.ttl
            }
        except Exception as e:
            logger.exception(f"Failed to get tag stats for {tag}: {e}")
            return {"tag": tag, "error": str(e)}
    
    def _hash_key_fields(self, key_fields: Dict[str, Any]) -> str:
        """Create stable hash from key fields"""
        # Sort keys for consistent hashing
        sorted_json = json.dumps(key_fields, sort_keys=True, default=str)
        return hashlib.sha1(sorted_json.encode()).hexdigest()[:12]
    
    def _json_serializer(self, obj) -> str:
        """Custom JSON serializer for complex objects"""
        if hasattr(obj, 'isoformat'):  # datetime objects
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):  # Pydantic models, etc.
            return obj.__dict__
        return str(obj)


class ContextCache:
    """
    High-level cache for course context services.
    Pre-configured with appropriate tags and TTLs.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        
        # Different TTLs for different context types
        self.caches = {
            "graphctx": TagCache(redis_client, ttl_s=24 * 3600),    # 24h for graph data
            "professors": TagCache(redis_client, ttl_s=7 * 24 * 3600),  # 7d for professor ratings
            "difficulty": TagCache(redis_client, ttl_s=24 * 3600),  # 24h for grade distributions
            "enrollment": TagCache(redis_client, ttl_s=1 * 3600),   # 1h for enrollment predictions
            "vector": TagCache(redis_client, ttl_s=3 * 24 * 3600),  # 3d for vector search
        }
    
    async def get_graph_context(
        self, 
        course_code: str, 
        student_profile: Dict[str, Any],
        loader: Callable
    ) -> Any:
        """Cache graph/prerequisite context"""
        key_fields = {
            "course_code": course_code,
            "student_id": student_profile.get("student_id", "unknown"),
            "completed_courses": sorted(student_profile.get("completed_courses", [])),
        }
        return await self.caches["graphctx"].get_or_set("graphctx", key_fields, loader)
    
    async def get_professor_context(
        self,
        course_code: str,
        loader: Callable
    ) -> Any:
        """Cache professor intelligence context"""
        key_fields = {"course_code": course_code}
        return await self.caches["professors"].get_or_set("professors", key_fields, loader)
    
    async def get_vector_context(
        self,
        query: str,
        top_k: int,
        loader: Callable
    ) -> Any:
        """Cache vector search results"""
        # Hash query for stable caching
        query_hash = hashlib.sha1(query.encode()).hexdigest()[:8]
        key_fields = {"query_hash": query_hash, "top_k": top_k}
        return await self.caches["vector"].get_or_set("vector", key_fields, loader)
    
    async def invalidate_graph_data(self) -> bool:
        """Invalidate all graph-related caches (e.g., after data update)"""
        return await self.caches["graphctx"].invalidate_tag("graphctx")
    
    async def invalidate_professor_data(self) -> bool:
        """Invalidate professor rating caches"""
        return await self.caches["professors"].invalidate_tag("professors")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics for all cache tags"""
        stats = {}
        for tag, cache in self.caches.items():
            stats[tag] = await cache.get_tag_stats(tag)
        return stats