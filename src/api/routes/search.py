"""Search and similarity endpoints with unified index integration."""

import sys
import os
import time
from fastapi import APIRouter, Depends, Request, HTTPException, status
from typing import Optional, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..schemas import SearchRequest, SearchResponse, SearchResult
from ..auth.jwt import get_current_user, get_tenant_id, TokenPayload
from src.similarity.base import SimilarityMetric, DomainType

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_cache(
    request: SearchRequest,
    http_request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Find semantically similar cached queries.
    
    This endpoint searches the unified similarity index for cached items
    that are semantically similar to the query. It uses the same index
    that cache PUT operations populate.
    """
    # Get services from app state
    embedding_service = getattr(http_request.app.state, 'embedding_service', None)
    cache_manager = getattr(http_request.app.state, 'cache_manager', None)
    index_manager = getattr(http_request.app.state, 'index_manager', None)
    domain_classifier = getattr(http_request.app.state, 'domain_classifier', None)
    threshold_manager = getattr(http_request.app.state, 'adaptive_thresholds', None)
    
    if embedding_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service not available"
        )
    
    if index_manager is None and cache_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search index not available"
        )
    
    try:
        start_time = time.time()
        
        # Generate embedding for query
        embedding_record = await embedding_service.embed_text(request.query)
        embedding = embedding_record.embedding
        
        # Detect domain for adaptive thresholds
        domain_str = "general"
        if domain_classifier:
            domain_str = domain_classifier.classify(request.query)
        
        # Get adaptive threshold
        final_threshold = request.threshold
        if threshold_manager and request.threshold == 0.75:  # Default value
            final_threshold = threshold_manager.get_threshold(domain_str)
        
        results = []
        
        # Use UnifiedIndexManager directly if available (preferred)
        if index_manager:
            search_results = index_manager.search(
                embedding=embedding,
                k=request.top_k,
                threshold=final_threshold,
                domain=domain_str,
                tenant_id=tenant_id,
            )
            
            for item_id, similarity, entry in search_results:
                # Get cached value
                cached_value = None
                cache_level = "index"
                
                if cache_manager:
                    cache_key = f"{tenant_id}:{item_id}" if tenant_id else item_id
                    cache_entry = cache_manager.get(cache_key)
                    if cache_entry:
                        cached_value = cache_entry[0].response
                        cache_level = cache_entry[1].lower()
                
                results.append(SearchResult(
                    key=item_id,
                    similarity=round(similarity, 4),
                    value=cached_value,
                    cache_level=cache_level
                ))
        
        # Fallback to CacheManager's semantic search
        elif cache_manager and hasattr(cache_manager, 'get_semantic_async'):
            semantic_result = await cache_manager.get_semantic_async(
                query_text=request.query,
                tenant_id=tenant_id,
                domain=domain_str,
                threshold=final_threshold,
            )
            
            if semantic_result and semantic_result.entry:
                results.append(SearchResult(
                    key=semantic_result.entry.query_id,
                    similarity=round(semantic_result.similarity, 4),
                    value=semantic_result.entry.response,
                    cache_level=semantic_result.hit_source.lower()
                ))
        
        search_time = (time.time() - start_time) * 1000
        
        return SearchResponse(
            query=request.query,
            metric=request.metric,
            results=results,
            count=len(results),
            search_time_ms=round(search_time, 2)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/similarity/embedding")
async def embedding_search(
    query: str,
    top_k: int = 10,
    threshold: float = 0.75,
    http_request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Generate embedding and find similar cached items.
    
    Returns both the generated embedding metadata and similar items
    from the unified search index.
    """
    embedding_service = getattr(http_request.app.state, 'embedding_service', None)
    index_manager = getattr(http_request.app.state, 'index_manager', None)
    cache_manager = getattr(http_request.app.state, 'cache_manager', None)
    
    if embedding_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service not available"
        )
    
    try:
        start_time = time.time()
        
        # Generate embedding
        embedding_record = await embedding_service.embed_text(query)
        embedding = embedding_record.embedding
        embedding_time = (time.time() - start_time) * 1000
        
        # Search unified index
        similar_items = []
        
        if index_manager:
            search_results = index_manager.search(
                embedding=embedding,
                k=top_k,
                threshold=threshold,
                tenant_id=tenant_id,
            )
            
            for rank, (item_id, similarity, entry) in enumerate(search_results, 1):
                cached_value = None
                
                if cache_manager:
                    cache_key = f"{tenant_id}:{item_id}" if tenant_id else item_id
                    cache_entry = cache_manager.get(cache_key)
                    if cache_entry:
                        cached_value = cache_entry[0].response
                
                similar_items.append({
                    "key": item_id,
                    "similarity": round(similarity, 4),
                    "value": cached_value,
                    "rank": rank,
                    "query_text": entry.query_text if entry else None,
                    "domain": entry.domain if entry else "general",
                })
        
        search_time = (time.time() - start_time) * 1000
        
        return {
            "text": query,
            "embedding_dimension": len(embedding),
            "embedding_time_ms": round(embedding_time, 2),
            "similar_items": similar_items,
            "count": len(similar_items),
            "search_time_ms": round(search_time, 2),
            "model": embedding_record.model,
            "index_available": index_manager is not None,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding search failed: {str(e)}"
        )


@router.get("/index/stats")
async def get_index_stats(
    http_request: Request = None,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    """Get unified search index statistics."""
    index_manager = getattr(http_request.app.state, 'index_manager', None)
    
    if index_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Index manager not available"
        )
    
    return {
        "index_stats": index_manager.get_stats(),
        "tenant_id": tenant_id,
    }
