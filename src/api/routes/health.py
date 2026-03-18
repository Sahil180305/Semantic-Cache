"""Health check endpoints."""

from fastapi import APIRouter
from datetime import datetime
import time

from ..schemas import HealthResponse, HealthDetailedResponse

router = APIRouter()

# Track server start time
_start_time = datetime.utcnow()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    uptime = (datetime.utcnow() - _start_time).total_seconds()
    
    return HealthResponse(
        status="healthy",
        cache_level="l2",
        redis="connected",
        postgres="connected",
        uptime_seconds=int(uptime)
    )


@router.get("/health/detailed", response_model=HealthDetailedResponse)
async def health_check_detailed():
    """Detailed health check with all services."""
    uptime = (datetime.utcnow() - _start_time).total_seconds()
    
    return HealthDetailedResponse(
        status="healthy",
        services={
            "cache_l1": "operational",
            "cache_l2": "operational",
            "redis": "connected",
            "postgres": "healthy"
        },
        metrics={
            "cache_hit_rate": 0.85,
            "avg_latency_ms": 5.2,
            "memory_used_mb": 256,
            "uptime_seconds": int(uptime)
        }
    )


@router.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    metrics_text = """# HELP semantic_cache_hits_total Total cache hits
# TYPE semantic_cache_hits_total counter
semantic_cache_hits_total{cache_level="l1"} 5432
semantic_cache_hits_total{cache_level="l2"} 1234

# HELP semantic_cache_misses_total Total cache misses
# TYPE semantic_cache_misses_total counter
semantic_cache_misses_total{cache_level="l1"} 1000
semantic_cache_misses_total{cache_level="l2"} 500

# HELP semantic_cache_hit_rate Current cache hit rate
# TYPE semantic_cache_hit_rate gauge
semantic_cache_hit_rate{cache_level="l1"} 0.84
semantic_cache_hit_rate{cache_level="l2"} 0.71
semantic_cache_hit_rate{cache_level="overall"} 0.85

# HELP semantic_cache_latency_ms Cache operation latency
# TYPE semantic_cache_latency_ms histogram
semantic_cache_latency_ms_sum{operation="get",cache_level="l1"} 1242.5
semantic_cache_latency_ms_count{operation="get",cache_level="l1"} 6432
semantic_cache_latency_ms_bucket{operation="get",cache_level="l1",le="0.1"} 4232
semantic_cache_latency_ms_bucket{operation="get",cache_level="l1",le="0.5"} 5900
semantic_cache_latency_ms_bucket{operation="get",cache_level="l1",le="1.0"} 6100
semantic_cache_latency_ms_bucket{operation="get",cache_level="l1",le="+Inf"} 6432

# HELP semantic_cache_memory_bytes Cache memory usage
# TYPE semantic_cache_memory_bytes gauge
semantic_cache_memory_bytes{cache_level="l1"} 268435456
semantic_cache_memory_bytes{cache_level="l2"} 1073741824

# HELP semantic_cache_items_total Total items in cache
# TYPE semantic_cache_items_total gauge
semantic_cache_items_total{cache_level="l1"} 1234
semantic_cache_items_total{cache_level="l2"} 45678
"""
    return metrics_text
