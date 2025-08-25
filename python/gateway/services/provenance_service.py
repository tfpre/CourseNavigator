"""
ProvenanceService - Redis-backed provenance tracking with TTL and version invalidation.

Implements Ground Truth: Information Reliability
- Source tracking for all data with timestamps and versions
- Cache invalidation on version changes
- Freshness monitoring with TTL policies
- Prometheus metrics for observability
"""

from __future__ import annotations
import asyncio
import contextlib
import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Any
from enum import StrEnum

try:
    from prometheus_client import Counter, Histogram, Gauge
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

class InvalReason(StrEnum):
    """Enumerated invalidation reasons for cardinality control"""
    DATASET_VERSION = "dataset_version"
    DATA_VERSION = "data_version" 
    TTL_EXPIRED = "ttl_expired"
    MANUAL = "manual"
    SOURCE_UPDATED = "source_updated"

ISO = "%Y-%m-%dT%H:%M:%S.%fZ"

# Prometheus metrics (only if available)
if METRICS_AVAILABLE:
    p_record = Counter("prov_record_total", "Provenance records", ["source", "result"])  # result=success|fail
    p_get = Counter("prov_get_total", "Provenance gets", ["source", "hit"])
    p_stale = Counter("prov_stale_total", "Provenance stale determinations", ["source", "kind"])  # kind=hard|soft
    p_inval = Counter("prov_invalidate_total", "Provenance invalidations", ["source", "reason"])
    p_latency = Histogram("prov_op_ms", "Provenance op latency (ms)", ["op"])
    p_index_size = Gauge("prov_index_size", "Current per-source index set size", ["source"])
    p_parse_fallback = Counter("prov_parse_fallback_total", "ISO parser fallbacks", ["source"])
else:
    # Mock metrics if prometheus not available
    class MockMetric:
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def time(self): return contextlib.nullcontext()
    
    p_record = p_get = p_stale = p_inval = p_latency = p_index_size = p_parse_fallback = MockMetric()

def _now_utc() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    """Convert datetime to ISO string"""
    return dt.astimezone(timezone.utc).strftime(ISO)

def _parse_iso(s: str, source: str = "unknown") -> datetime:
    """Parse ISO string with or without microseconds, handling both Z and offset formats
    
    Args:
        s: ISO timestamp string to parse
        source: Source name for metrics tracking (e.g., "professors", "graphctx")
    """
    s = s.strip()
    
    # Try Z formats first (most common)
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"]:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    
    # Try offset format (e.g., +00:00, -05:00) and convert to UTC
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)  # Ensure UTC normalization
    except Exception:
        # Last resort: return current time to avoid crashes
        logging.warning(f"Failed to parse timestamp '{s}' from source '{source}', using current time")
        p_parse_fallback.labels(source=source).inc()
        return _now_utc()

def compute_data_version(obj: Any) -> str:
    """
    Stable hash for JSON-like payloads; preserves dict key order deterministically.
    Used for detecting when data payload content changes.
    """
    try:
        norm = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        norm = repr(obj)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()

@dataclass
class ProvenanceTag:
    """
    Provenance metadata for tracking data sources, versions, and freshness.
    
    Stores comprehensive attribution and lifecycle information for any data entity.
    """
    source: str                           # e.g., "grades", "roster", "professors", "enrollment", "graph"
    entity_id: str                        # e.g., "CS 4780", "FA25:CS:4780", or professor_id
    tenant: Optional[str] = None          # multi-tenant support for future
    source_id: Optional[str] = None       # upstream identifier if different from entity_id
    url: Optional[str] = None             # source URL if applicable
    term: Optional[str] = None            # e.g., "FA25" for academic term
    version: Optional[str] = None         # upstream dataset version or our ETL version
    data_version: Optional[str] = None    # hash/checksum/etag of the payload content
    observed_at: Optional[str] = None     # when the fact originates (source's timestamp)
    fetched_at: Optional[str] = None      # when we fetched into our system
    expires_at: Optional[str] = None      # explicit expiration timestamp
    ttl_seconds: int = 0                  # TTL for cache expiration
    soft_ttl_seconds: Optional[int] = None # serve cached but refresh when > soft_ttl
    serialization_version: int = 1        # for future schema evolution
    meta: Optional[Dict[str, Any]] = None # additional metadata
    
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ProvenanceTag":
        """Create ProvenanceTag from dictionary, tolerating missing optional fields"""
        # Filter out None values and unknown fields for backward compatibility
        known_fields = {
            'source', 'entity_id', 'tenant', 'source_id', 'url', 'term',
            'version', 'data_version', 'observed_at', 'fetched_at', 'expires_at',
            'ttl_seconds', 'soft_ttl_seconds', 'serialization_version', 'meta'
        }
        filtered = {k: v for k, v in d.items() if k in known_fields and v is not None}
        return ProvenanceTag(**filtered)
    
    def dump(self) -> str:
        """Serialize to JSON string for Redis storage"""
        d = asdict(self)
        # Remove None values to keep storage compact
        d = {k: v for k, v in d.items() if v is not None}
        return json.dumps(d, separators=(",", ":"), ensure_ascii=False)

class ProvenanceService:
    """
    Redis-backed provenance store with indexing and freshness helpers.
    
    Keys:
      prov:{tenant?}:{source}:{entity_id} -> serialized ProvenanceTag (TTL applied)
      prov:index:{tenant?}:{source}       -> set(entity_id) (enables future sweeps)
    
    Features:
    - Hard and soft staleness detection
    - Version-based cache invalidation  
    - Prometheus metrics for observability
    - Graceful degradation when Redis unavailable
    """
    
    def __init__(self, redis_client, op_timeout_ms: int = 75):
        """
        Initialize provenance service.
        
        Args:
            redis_client: Async Redis client (aioredis)
            op_timeout_ms: Timeout for Redis operations in milliseconds
        """
        self.r = redis_client
        self.timeout = op_timeout_ms / 1000.0
    
    def _key(self, source: str, entity_id: str, tenant: Optional[str] = None) -> str:
        """Generate Redis key for provenance tag"""
        if tenant:
            return f"prov:{tenant}:{source}:{entity_id}"
        return f"prov:{source}:{entity_id}"
    
    def _index_key(self, source: str, tenant: Optional[str] = None) -> str:
        """Generate Redis key for source index with monthly sharding to prevent unbounded growth"""
        # Shard by month to prevent unbounded growth
        month_shard = _now_utc().strftime("%Y%m")
        if tenant:
            return f"prov:index:{tenant}:{source}:{month_shard}"
        return f"prov:index:{source}:{month_shard}"
    
    async def record(self, tag: ProvenanceTag) -> bool:
        """
        Record a provenance tag in Redis with TTL.
        
        Args:
            tag: ProvenanceTag to store
            
        Returns:
            True if successful, False if Redis unavailable or error
        """
        if not self.r:
            return False
            
        # Set fetched_at if not provided
        if not tag.fetched_at:
            tag.fetched_at = _iso(_now_utc())
        
        # TTL precedence: explicit ttl_seconds > expires_at delta > 0
        ttl = tag.ttl_seconds or 0
        if ttl <= 0 and tag.expires_at:
            try:
                exp = _parse_iso(tag.expires_at, tag.source)
                ttl = max(1, int((exp - _now_utc()).total_seconds()))
            except Exception:
                ttl = 0
        
        key = self._key(tag.source, tag.entity_id, tag.tenant)
        idx = self._index_key(tag.source, tag.tenant)
        
        t0 = time.perf_counter()
        try:
            # Use pipeline for single round trip
            pipe = self.r.pipeline(transaction=False)
            
            # Store the tag with TTL
            if ttl > 0:
                pipe.setex(key, ttl, tag.dump())
            else:
                pipe.set(key, tag.dump())
            
            # Add to index with 60-day TTL to prevent unbounded growth
            pipe.sadd(idx, tag.entity_id)
            pipe.expire(idx, 60 * 24 * 3600)  # 60 days
            
            results = await asyncio.wait_for(pipe.execute(), timeout=self.timeout)
            
            # Update index size gauge incrementally (avoid SCARD on every write)
            # SADD returns 1 if element was added, 0 if already existed
            if results and len(results) >= 1 and results[0] == 1:
                p_index_size.labels(tag.source).inc()
            
            # Note: Periodic SCARD reconciliation happens elsewhere to correct drift
            
            p_record.labels(tag.source, "success").inc()
            p_latency.labels("record").observe((time.perf_counter() - t0) * 1000.0)
            return True
            
        except Exception as e:
            logging.warning(f"Provenance record failed for {tag.source}:{tag.entity_id}: {e}")
            p_record.labels(tag.source, "fail").inc()
            p_latency.labels("record").observe((time.perf_counter() - t0) * 1000.0)
            return False
    
    async def get(self, source: str, entity_id: str, tenant: Optional[str] = None) -> Optional[ProvenanceTag]:
        """
        Retrieve a provenance tag from Redis.
        
        Args:
            source: Data source name (e.g., "grades")
            entity_id: Entity identifier (e.g., "CS 4780")
            tenant: Optional tenant for multi-tenant setups
            
        Returns:
            ProvenanceTag if found, None otherwise
        """
        if not self.r:
            return None
            
        key = self._key(source, entity_id, tenant)
        t0 = time.perf_counter()
        
        try:
            raw = await asyncio.wait_for(self.r.get(key), timeout=self.timeout)
            p_get.labels(source, "hit" if raw else "miss").inc()
            p_latency.labels("get").observe((time.perf_counter() - t0) * 1000.0)
            
            return ProvenanceTag.from_dict(json.loads(raw)) if raw else None
            
        except Exception as e:
            if t0 and time.perf_counter() - t0 > self.timeout:
                logging.warning(f"Provenance get timeout for {source}:{entity_id}: {e}")
            p_latency.labels("get").observe((time.perf_counter() - t0) * 1000.0)
            return None
    
    async def is_stale(self, source: str, entity_id: str, tenant: Optional[str] = None) -> bool:
        """
        Check if data is hard stale (expired or missing).
        
        Args:
            source: Data source name
            entity_id: Entity identifier
            tenant: Optional tenant
            
        Returns:
            True if data is stale or missing, False if fresh
        """
        tag = await self.get(source, entity_id, tenant)
        if not tag:
            p_stale.labels(source, "hard").inc()
            return True
            
        if tag.expires_at:
            try:
                expires_time = _parse_iso(tag.expires_at, source)
                if _now_utc() >= expires_time:
                    p_stale.labels(source, "hard").inc()
                    return True
            except Exception:
                # If parse fails, fall back to Redis TTL presence (best effort)
                return False
        
        return False
    
    async def is_soft_stale(self, source: str, entity_id: str, tenant: Optional[str] = None) -> bool:
        """
        Check if data is soft stale (should trigger background refresh but still usable).
        
        Args:
            source: Data source name
            entity_id: Entity identifier  
            tenant: Optional tenant
            
        Returns:
            True if data should be refreshed, False if still fresh
        """
        tag = await self.get(source, entity_id, tenant)
        if not tag:
            p_stale.labels(source, "hard").inc()
            return True
            
        if tag.soft_ttl_seconds is None:
            return False
            
        try:
            if tag.fetched_at:
                fetched = _parse_iso(tag.fetched_at, source)
            else:
                fetched = _now_utc()
            soft_expiry = fetched + timedelta(seconds=tag.soft_ttl_seconds)
            if _now_utc() >= soft_expiry:
                p_stale.labels(source, "soft").inc()
                return True
        except Exception:
            return False
            
        return False
    
    async def invalidate_on_version_change(
        self,
        source: str,
        entity_id: str,
        current_version: Optional[str],
        current_data_version: Optional[str],
        tenant: Optional[str] = None,
        drop_cache_fn: Optional[Callable[[], Any]] = None,
    ) -> bool:
        """
        Invalidate cached data if version or data content has changed.
        
        Args:
            source: Data source name
            entity_id: Entity identifier
            current_version: Current dataset/ETL version
            current_data_version: Current data content hash
            tenant: Optional tenant
            drop_cache_fn: Optional callback to drop downstream caches
            
        Returns:
            True if invalidation occurred, False if no change detected
        """
        tag = await self.get(source, entity_id, tenant)
        if not tag:
            return False
            
        changed = False
        reason = InvalReason.MANUAL  # Default fallback
        
        if current_version and tag.version != current_version:
            changed = True
            reason = InvalReason.DATASET_VERSION
        elif current_data_version and tag.data_version != current_data_version:
            changed = True
            reason = InvalReason.DATA_VERSION
            
        if not changed:
            return False
        
        key = self._key(source, entity_id, tenant)
        
        try:
            # Drop downstream caches first
            if drop_cache_fn:
                maybe = drop_cache_fn()
                if asyncio.iscoroutine(maybe):
                    with contextlib.suppress(asyncio.CancelledError):
                        await maybe
            
            # Delete the stale provenance tag
            await asyncio.wait_for(self.r.delete(key), timeout=self.timeout)
            p_inval.labels(source, reason).inc()
            return True
            
        except Exception as e:
            logging.warning(f"Provenance invalidation failed for {source}:{entity_id}: {e}")
            return False
    
    async def reconcile_index_sizes(self) -> Dict[str, int]:
        """
        Reconcile p_index_size gauges with actual SCARD values.
        Should be called periodically (e.g., every 100 ops or 1-minute background task).
        
        Returns:
            Dict mapping source names to actual sizes
        """
        if not self.r:
            return {}
            
        try:
            # Find all index keys
            index_pattern = f"{self.PREFIX}:index:*"
            index_keys = await self.r.keys(index_pattern)
            
            sizes = {}
            for idx_key in index_keys:
                # Extract source from key: "prov:index:professors" -> "professors"  
                source = idx_key.decode() if isinstance(idx_key, bytes) else idx_key
                source = source.split(':')[-1] if ':' in source else source
                try:
                    actual_size = await asyncio.wait_for(self.r.scard(idx_key), timeout=0.5)
                    p_index_size.labels(source).set(actual_size)
                    sizes[source] = actual_size
                except Exception as e:
                    logging.debug(f"SCARD reconciliation failed for {source}: {e}")
                    
            logging.info(f"Index size reconciliation complete: {sizes}")
            return sizes
            
        except Exception as e:
            logging.warning(f"Index size reconciliation failed: {e}")
            return {}