"""Cache operations endpoints."""

import time
from fastapi import APIRouter, Depends, Path, Query, Request, HTTPException, status
from typing import Optional, Any
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..schemas import (
    CachePutRequest, CachePutResponse, CacheGetResponse,
    CacheBatchRequest, CacheBatchResponse, CacheBatchResult
)
from ..auth.jwt import get_current_user, get_tenant_id, TokenPayload
from ..middleware.error import CacheNotFoundException
from src.cache.base import CacheEntry

router = APIRouter()


@router.get("/{key}", response_model=CacheGetResponse)
async def get_cache(
    key: str = Path(..., description="Cache key"),
    request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """Retrieve value from cache."""
    # Get cache manager from app state
    cache_manager = request.app.state.cache_manager if hasattr(request.app.state, 'cache_manager') else None
    
    if cache_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache manager not available"
        )
    
    # Use tenant_id as part of the cache key
    cache_key = f"{tenant_id}:{key}"
    
    # Record start time for latency measurement
    start_time = time.time()
    
    # Retrieve from cache
    result = cache_manager.get(cache_key)
    latency_ms = (time.time() - start_time) * 1000
    
    if result is None:
        raise CacheNotFoundException(f"Key '{key}' not found in cache")
    
    entry, source = result
    
    # Calculate TTL remaining
    ttl_remaining = None
    if cache_manager.config.l1_config.ttl_seconds:
        age = time.time() - entry.created_at
        remaining = cache_manager.config.l1_config.ttl_seconds - age
        ttl_remaining = max(0, int(remaining))
    
    return CacheGetResponse(
        key=key,
        value=entry.response,
        hit=True,
        cache_level=("l1" if source == "L1" else "l2"),
        latency_ms=round(latency_ms, 2),
        ttl_remaining_seconds=ttl_remaining
    )


@router.put("/{key}", response_model=CachePutResponse, status_code=201)
async def put_cache(
    key: str = Path(..., description="Cache key"),
    request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """Cache a value."""
    cache_manager = request.app.state.cache_manager if hasattr(request.app.state, 'cache_manager') else None
    
    if cache_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache manager not available"
        )
    
    # Get the raw request body as the value to cache
    try:
        import json
        raw_body = await request.body()
        value = json.loads(raw_body) if raw_body else {}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in request body: {str(e)}"
        )
    
    # Use tenant_id as part of the cache key
    cache_key = f"{tenant_id}:{key}"
    
    # Create cache entry
    entry = CacheEntry(
        query_id=cache_key,
        query_text=key,
        embedding=[0.0] * 10,  # Placeholder embedding
        response=value,
        metadata={"source": "api", "object": "cache_put"},
        domain="general"
    )
    
    # Calculate memory
    entry.calculate_memory(10)
    
    # Store in cache
    success = cache_manager.put(entry)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cache value"
        )
    
    return CachePutResponse(
        key=key,
        cached=True,
        cache_level="l2" if cache_manager.config.strategy.name == "WRITE_THROUGH" else "l1",
        size_bytes=int(entry.memory_estimate)
    )


@router.delete("/{key}", status_code=204)
async def delete_cache(
    key: str = Path(..., description="Cache key"),
    request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """Delete cached value."""
    cache_manager = request.app.state.cache_manager if hasattr(request.app.state, 'cache_manager') else None
    
    if cache_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache manager not available"
        )
    
    # Use tenant_id as part of the cache key
    cache_key = f"{tenant_id}:{key}"
    
    # Delete from cache
    success = cache_manager.delete(cache_key)
    
    if not success:
        raise CacheNotFoundException(f"Key '{key}' not found or deletion failed")


@router.post("/batch", response_model=CacheBatchResponse)
async def batch_get_cache(
    request: Request = None,
    body: CacheBatchRequest = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """Get multiple cache values in one request."""
    cache_manager = request.app.state.cache_manager if hasattr(request.app.state, 'cache_manager') else None
    
    if cache_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache manager not available"
        )
    
    if body is None or not body.keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No keys provided"
        )
    
    results = []
    hit_count = 0
    miss_count = 0
    
    for key in body.keys:
        cache_key = f"{tenant_id}:{key}"
        result = cache_manager.get(cache_key)
        
        if result is not None:
            entry, _source = result
            results.append(CacheBatchResult(key=key, value=entry.response, hit=True))
            hit_count += 1
        else:
            results.append(CacheBatchResult(key=key, value=None, hit=False))
            miss_count += 1
    
    hit_rate = hit_count / len(body.keys) if body.keys else 0.0
    
    return CacheBatchResponse(
        results=results,
        hit_count=hit_count,
        miss_count=miss_count,
        hit_rate=round(hit_rate, 3)
    )


@router.delete("", status_code=200)
async def clear_cache(
    request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """Clear all cache (admin only)."""
    # Check admin role
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    cache_manager = request.app.state.cache_manager if hasattr(request.app.state, 'cache_manager') else None
    
    if cache_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache manager not available"
        )
    
    success = cache_manager.clear()
    
    # Cache manager might return None or False - treat None as success for L1
    if success is False:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear cache"
        )
    
    return {
        "cleared": True,
        "message": "All cache entries cleared"
    }
