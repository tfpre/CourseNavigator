# Graph Metadata & Versioning for Cache Invalidation
# Implements friend's Priority 3 recommendation: graph_version in cache keys

import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class GraphMetadata:
    """Graph version and metadata for cache invalidation"""
    version: int
    last_updated: datetime
    node_count: int
    relationship_count: int
    etl_source: str = "manual"
    
    def to_dict(self) -> Dict[str, any]:
        return {
            "version": self.version,
            "last_updated": self.last_updated.isoformat(),
            "node_count": self.node_count, 
            "relationship_count": self.relationship_count,
            "etl_source": self.etl_source
        }

class GraphMetadataService:
    """
    Centralized graph versioning service
    
    Implements friend's recommendation:
    - graph_meta node in Neo4j: {version: 42, last_updated: 2025-08-05T09:13}
    - Every API response embeds graph_version
    - Redis keys namespaced: centrality:v42:{params}
    - Nightly ETL bumps version and invalidates old cache
    """
    
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service
        self._cached_metadata: Optional[GraphMetadata] = None
        self._cache_timestamp: Optional[float] = None
        self.cache_ttl = 300  # 5 minutes
        
    async def get_current_metadata(self, use_cache: bool = True) -> GraphMetadata:
        """Get current graph metadata with caching"""
        
        # Check cache first
        if (use_cache and self._cached_metadata and self._cache_timestamp and 
            time.time() - self._cache_timestamp < self.cache_ttl):
            return self._cached_metadata
        
        try:
            # Get metadata from Neo4j
            query = """
            // Get or create graph metadata node
            MERGE (meta:GraphMetadata {id: 'main'})
            ON CREATE SET 
                meta.version = 1,
                meta.last_updated = datetime(),
                meta.etl_source = 'initial'
            
            WITH meta
            
            // Get current graph stats
            CALL {
                MATCH (c:Course) 
                WITH count(c) as node_count
                MATCH ()-[r:REQUIRES]->()
                WITH node_count, count(r) as rel_count
                RETURN node_count, rel_count
            }
            
            // Update stats on metadata node
            SET meta.node_count = node_count,
                meta.relationship_count = rel_count
            
            RETURN meta.version as version,
                   meta.last_updated as last_updated,
                   meta.node_count as node_count, 
                   meta.relationship_count as relationship_count,
                   meta.etl_source as etl_source
            """
            
            result = await self.neo4j.execute_query(query)
            
            if not result:
                raise Exception("Failed to get graph metadata from Neo4j")
            
            record = result[0]
            metadata = GraphMetadata(
                version=int(record["version"]),
                last_updated=record["last_updated"],
                node_count=int(record["node_count"]),
                relationship_count=int(record["relationship_count"]),
                etl_source=record["etl_source"] or "manual"
            )
            
            # Cache the result
            self._cached_metadata = metadata
            self._cache_timestamp = time.time()
            
            logger.info(f"Retrieved graph metadata: v{metadata.version}, {metadata.node_count} nodes, {metadata.relationship_count} edges")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get graph metadata: {e}")
            # Return default metadata if database is unavailable
            return GraphMetadata(
                version=1,
                last_updated=datetime.now(),
                node_count=0,
                relationship_count=0,
                etl_source="error_fallback"
            )
    
    async def increment_version(self, etl_source: str = "manual_update") -> int:
        """
        Increment graph version after ETL/data changes
        This invalidates all version-based cache keys
        """
        try:
            query = """
            MATCH (meta:GraphMetadata {id: 'main'})
            SET meta.version = meta.version + 1,
                meta.last_updated = datetime(),
                meta.etl_source = $etl_source
            
            WITH meta
            
            // Get updated stats
            CALL {
                MATCH (c:Course) 
                WITH count(c) as node_count
                MATCH ()-[r:REQUIRES]->()
                WITH node_count, count(r) as rel_count
                RETURN node_count, rel_count
            }
            
            SET meta.node_count = node_count,
                meta.relationship_count = rel_count
                
            RETURN meta.version as new_version
            """
            
            result = await self.neo4j.execute_query(query, etl_source=etl_source)
            
            if not result:
                raise Exception("Failed to increment graph version")
            
            new_version = int(result[0]["new_version"])
            
            # Clear cache to force refresh
            self._cached_metadata = None
            self._cache_timestamp = None
            
            logger.info(f"Incremented graph version to v{new_version} (source: {etl_source})")
            return new_version
            
        except Exception as e:
            logger.error(f"Failed to increment graph version: {e}")
            raise
    
    def generate_cache_key(self, base_key: str, **params) -> str:
        """
        Generate versioned cache key
        Format: {base_key}:v{version}:{param_hash}
        
        Example: centrality:v42:top_20_damping_085
        """
        try:
            # Get version from cache if available, otherwise use fallback
            version = 1
            if (self._cached_metadata and self._cache_timestamp and
                time.time() - self._cache_timestamp < self.cache_ttl):
                version = self._cached_metadata.version
            
            # Create parameter hash
            param_parts = []
            for key, value in sorted(params.items()):
                if isinstance(value, float):
                    param_parts.append(f"{key}_{value:.3f}".replace(".", ""))
                else:
                    param_parts.append(f"{key}_{value}")
            
            param_hash = "_".join(param_parts) if param_parts else "default"
            
            cache_key = f"{base_key}:v{version}:{param_hash}"
            return cache_key
            
        except Exception as e:
            logger.warning(f"Failed to generate versioned cache key, using fallback: {e}")
            return f"{base_key}:v1:fallback"
    
    async def invalidate_version_cache(self, version: int, cache_prefixes: list[str] = None):
        """
        Invalidate all cache entries for a specific version
        This would integrate with Redis in production
        
        Args:
            version: Graph version to invalidate
            cache_prefixes: List of cache prefixes to clear (e.g., ['centrality', 'communities'])
        """
        if cache_prefixes is None:
            cache_prefixes = ['centrality', 'communities', 'subgraph', 'layout']
        
        # NOTE: In production this would use Redis SCAN + DELETE
        # For now, this is a placeholder for the architecture
        logger.info(f"Would invalidate cache entries: {cache_prefixes} for version v{version}")
        
        # Production implementation would be:
        # for prefix in cache_prefixes:
        #     pattern = f"{prefix}:v{version}:*"
        #     keys = await redis.scan(match=pattern)
        #     if keys:
        #         await redis.delete(*keys)
        #         logger.info(f"Invalidated {len(keys)} cache entries for {pattern}")