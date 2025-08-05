"""
Performance Service for Cornell Course Navigator
Provides performance monitoring, caching, and optimization utilities
"""

import logging
import time
import asyncio
import psutil
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import functools

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for API endpoints"""
    endpoint: str
    request_count: int
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
    error_rate: float
    last_24h_requests: int


@dataclass
class SystemHealth:
    """System health metrics"""
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    active_connections: int
    cache_hit_rate: float
    uptime_seconds: float


class PerformanceService:
    """Service for monitoring and optimizing performance"""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_metrics: Dict[str, List[float]] = {}
        self.error_counts: Dict[str, int] = {}
        self.request_counts: Dict[str, int] = {}
        
    def time_function(self, func_name: str = None):
        """Decorator to time function execution"""
        def decorator(func):
            name = func_name or f"{func.__module__}.{func.__name__}"
            
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    start_time = time.time()
                    try:
                        result = await func(*args, **kwargs)
                        self._record_request(name, time.time() - start_time, success=True)
                        return result
                    except Exception as e:
                        self._record_request(name, time.time() - start_time, success=False)
                        raise
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                        self._record_request(name, time.time() - start_time, success=True)
                        return result
                    except Exception as e:
                        self._record_request(name, time.time() - start_time, success=False)
                        raise
                return sync_wrapper
        return decorator
    
    def _record_request(self, endpoint: str, duration_seconds: float, success: bool = True):
        """Record request metrics"""
        duration_ms = duration_seconds * 1000
        
        if endpoint not in self.request_metrics:
            self.request_metrics[endpoint] = []
            self.error_counts[endpoint] = 0
            self.request_counts[endpoint] = 0
        
        self.request_metrics[endpoint].append(duration_ms)
        self.request_counts[endpoint] += 1
        
        if not success:
            self.error_counts[endpoint] += 1
        
        # Keep only last 1000 requests per endpoint to prevent memory bloat
        if len(self.request_metrics[endpoint]) > 1000:
            self.request_metrics[endpoint] = self.request_metrics[endpoint][-1000:]
    
    def get_performance_metrics(self, endpoint: str = None) -> Dict[str, PerformanceMetrics]:
        """Get performance metrics for endpoints"""
        if endpoint:
            endpoints_to_check = [endpoint] if endpoint in self.request_metrics else []
        else:
            endpoints_to_check = list(self.request_metrics.keys())
        
        metrics = {}
        
        for ep in endpoints_to_check:
            if not self.request_metrics[ep]:
                continue
                
            times = self.request_metrics[ep]
            request_count = self.request_counts[ep]
            error_count = self.error_counts[ep]
            
            # Calculate percentiles
            sorted_times = sorted(times)
            p95_index = int(len(sorted_times) * 0.95)
            
            metrics[ep] = PerformanceMetrics(
                endpoint=ep,
                request_count=request_count,
                avg_response_time_ms=sum(times) / len(times),
                min_response_time_ms=min(times),
                max_response_time_ms=max(times),
                p95_response_time_ms=sorted_times[p95_index] if sorted_times else 0.0,
                error_rate=error_count / request_count if request_count > 0 else 0.0,
                last_24h_requests=request_count  # Simplified for now
            )
        
        return metrics
    
    async def get_system_health(self) -> SystemHealth:
        """Get current system health metrics"""
        try:
            # CPU usage - non-blocking version
            cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=None)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Uptime
            uptime = time.time() - self.start_time
            
            # Calculate cache hit rate (simplified)
            total_requests = sum(self.request_counts.values())
            cache_hits = total_requests * 0.7  # Simplified estimation
            cache_hit_rate = cache_hits / total_requests if total_requests > 0 else 0.0
            
            return SystemHealth(
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory_percent,
                disk_usage_percent=disk_percent,
                active_connections=len(self.request_metrics),  # Simplified
                cache_hit_rate=cache_hit_rate,
                uptime_seconds=uptime
            )
            
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return SystemHealth(
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                disk_usage_percent=0.0,
                active_connections=0,
                cache_hit_rate=0.0,
                uptime_seconds=time.time() - self.start_time
            )
    
    def check_performance_thresholds(self) -> Dict[str, Any]:
        """Check if performance metrics meet required thresholds"""
        target_response_time_ms = 1200  # 1.2s target from Week 4 requirements
        max_error_rate = 0.05  # 5% max error rate
        
        metrics = self.get_performance_metrics()
        health_status = self.get_system_health()
        
        issues = []
        warnings = []
        
        # Check response times
        for endpoint, metric in metrics.items():
            if metric.p95_response_time_ms > target_response_time_ms:
                issues.append(f"{endpoint}: P95 response time {metric.p95_response_time_ms:.0f}ms exceeds target {target_response_time_ms}ms")
            elif metric.avg_response_time_ms > target_response_time_ms * 0.8:
                warnings.append(f"{endpoint}: Average response time {metric.avg_response_time_ms:.0f}ms approaching target")
            
            if metric.error_rate > max_error_rate:
                issues.append(f"{endpoint}: Error rate {metric.error_rate:.2%} exceeds maximum {max_error_rate:.2%}")
        
        # Check system resources
        if health_status.cpu_usage_percent > 80:
            issues.append(f"High CPU usage: {health_status.cpu_usage_percent:.1f}%")
        elif health_status.cpu_usage_percent > 60:
            warnings.append(f"Elevated CPU usage: {health_status.cpu_usage_percent:.1f}%")
        
        if health_status.memory_usage_percent > 85:
            issues.append(f"High memory usage: {health_status.memory_usage_percent:.1f}%")
        elif health_status.memory_usage_percent > 70:
            warnings.append(f"Elevated memory usage: {health_status.memory_usage_percent:.1f}%")
        
        # Overall status
        if issues:
            status = "critical"
        elif warnings:
            status = "warning"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "metrics_summary": {
                "total_endpoints": len(metrics),
                "total_requests": sum(m.request_count for m in metrics.values()),
                "avg_response_time_ms": sum(m.avg_response_time_ms * m.request_count for m in metrics.values()) / sum(m.request_count for m in metrics.values()) if metrics else 0,
                "overall_error_rate": sum(m.error_rate * m.request_count for m in metrics.values()) / sum(m.request_count for m in metrics.values()) if metrics else 0
            },
            "system_health": health_status
        }
    
    def get_optimization_recommendations(self) -> List[str]:
        """Get recommendations for performance optimization"""
        recommendations = []
        
        metrics = self.get_performance_metrics()
        health_status = self.get_system_health()
        
        # Slow endpoint recommendations
        slow_endpoints = [
            (endpoint, metric) for endpoint, metric in metrics.items()
            if metric.avg_response_time_ms > 1000
        ]
        
        if slow_endpoints:
            recommendations.append(f"Consider caching for slow endpoints: {', '.join(ep for ep, _ in slow_endpoints)}")
        
        # High error rate recommendations
        error_endpoints = [
            endpoint for endpoint, metric in metrics.items()
            if metric.error_rate > 0.02
        ]
        
        if error_endpoints:
            recommendations.append(f"Investigate error causes for: {', '.join(error_endpoints)}")
        
        # System resource recommendations
        if health_status.cpu_usage_percent > 70:
            recommendations.append("Consider horizontal scaling or CPU optimization")
        
        if health_status.memory_usage_percent > 70:
            recommendations.append("Consider memory optimization or increased RAM")
        
        if health_status.cache_hit_rate < 0.5:
            recommendations.append("Improve caching strategy to increase hit rate")
        
        # Graph algorithm specific recommendations
        graph_endpoints = [ep for ep in metrics.keys() if any(term in ep.lower() for term in ['centrality', 'community', 'path', 'semester'])]
        
        if graph_endpoints:
            avg_graph_time = sum(metrics[ep].avg_response_time_ms for ep in graph_endpoints) / len(graph_endpoints)
            if avg_graph_time > 800:
                recommendations.append("Graph algorithms taking >800ms average - consider pre-computation or better caching")
        
        if not recommendations:
            recommendations.append("Performance is within acceptable thresholds")
        
        return recommendations
    
    def reset_metrics(self):
        """Reset all performance metrics"""
        self.request_metrics.clear()
        self.error_counts.clear()
        self.request_counts.clear()
        logger.info("Performance metrics reset")


# Global performance service instance
performance_service = PerformanceService()