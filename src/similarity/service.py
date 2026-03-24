"""
Similarity Search Service (Facade Pattern)

High-level service for semantic similarity search that delegates to UnifiedIndexManager.
Provides additional features on top of the unified index:
- Multi-metric support (cosine, euclidean, inner product, etc.)
- Query deduplication (fast SHA256 pre-check)
- Result ranking and scoring
- Rich search metrics and analytics
- Batch search operations

NOTE: This service does NOT maintain its own index. All indexing operations
are delegated to UnifiedIndexManager for consistency across the system.
"""

import time
import hashlib
from typing import List, Dict, Optional, Tuple, Set, Any, TYPE_CHECKING
from datetime import datetime, timezone
import logging
from collections import defaultdict

from src.similarity.base import (
    SimilarityMetric,
    SimilarityAlgorithm,
    SimilarityScore,
    SimilaritySearchRequest,
    SimilaritySearchResult,
    DomainType,
    DomainThresholdConfig,
    SimilarityAlgorithmFactory,
)
from src.core.exceptions import (
    SimilarityError,
    CacheError,
)
from src.utils.logging import get_logger

# Avoid circular import
if TYPE_CHECKING:
    from src.cache.index_manager import UnifiedIndexManager

logger = get_logger(__name__)


class QueryDeduplicator:
    """Handles query deduplication to avoid duplicate processing."""
    
    def __init__(self, similarity_threshold: float = 0.99, cache_size: int = 10000):
        """
        Initialize deduplicator.
        
        Args:
            similarity_threshold: Minimum similarity to consider queries duplicates
            cache_size: Maximum number of cached queries
        """
        self.similarity_threshold = similarity_threshold
        self.cache_size = cache_size
        self.query_cache: Dict[str, Tuple[List[float], datetime]] = {}
        self.dedup_stats = {"total_checks": 0, "duplicates_found": 0}
    
    def _get_query_hash(self, text: str) -> str:
        """Get SHA256 hash of query text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def is_duplicate(self, text: str) -> bool:
        """
        Check if query text is a duplicate of a recent query.
        
        Args:
            text: Query text
            
        Returns:
            True if text is a duplicate of recent query
        """
        self.dedup_stats["total_checks"] += 1
        query_hash = self._get_query_hash(text)
        
        if query_hash in self.query_cache:
            self.dedup_stats["duplicates_found"] += 1
            return True
        
        return False
    
    def add_query(self, text: str) -> None:
        """Register a query as seen."""
        if len(self.query_cache) >= self.cache_size:
            # Remove oldest entry
            oldest_key = min(
                self.query_cache.keys(),
                key=lambda k: self.query_cache[k][1]
            )
            del self.query_cache[oldest_key]
        
        query_hash = self._get_query_hash(text)
        self.query_cache[query_hash] = (text, datetime.now(timezone.utc))
    
    def get_stats(self) -> Dict:
        """Get deduplication statistics."""
        return {
            "total_checks": self.dedup_stats["total_checks"],
            "duplicates_found": self.dedup_stats["duplicates_found"],
            "dedup_rate": (
                self.dedup_stats["duplicates_found"] / self.dedup_stats["total_checks"]
                if self.dedup_stats["total_checks"] > 0 else 0
            ),
            "cached_queries": len(self.query_cache),
        }


class SimilaritySearchMetrics:
    """Track similarity search metrics."""
    
    def __init__(self):
        """Initialize metrics."""
        self.total_searches = 0
        self.total_candidates_searched = 0
        self.total_matches_found = 0
        self.total_search_time_ms = 0.0
        self.queries_deduped = 0
        self.metric_usage: Dict[str, int] = defaultdict(int)
        self.domain_usage: Dict[str, int] = defaultdict(int)
        self.start_time = datetime.utcnow()
    
    def record_search(
        self,
        num_candidates: int,
        num_matches: int,
        search_time_ms: float,
        metric: SimilarityMetric,
        domain: DomainType,
        is_deduplicated: bool = False,
    ):
        """Record metrics for a search."""
        self.total_searches += 1
        self.total_candidates_searched += num_candidates
        self.total_matches_found += num_matches
        self.total_search_time_ms += search_time_ms
        
        if is_deduplicated:
            self.queries_deduped += 1
        
        self.metric_usage[metric.value] += 1
        self.domain_usage[domain.value] += 1
    
    def get_stats(self) -> Dict:
        """Get aggregated metrics."""
        elapsed_minutes = (datetime.utcnow() - self.start_time).total_seconds() / 60
        
        return {
            "total_searches": self.total_searches,
            "total_candidates": self.total_candidates_searched,
            "total_matches": self.total_matches_found,
            "match_rate": (
                self.total_matches_found / self.total_candidates_searched
                if self.total_candidates_searched > 0 else 0
            ),
            "avg_search_time_ms": (
                self.total_search_time_ms / self.total_searches
                if self.total_searches > 0 else 0
            ),
            "queries_deduped": self.queries_deduped,
            "dedup_rate": self.queries_deduped / self.total_searches if self.total_searches > 0 else 0,
            "metric_usage": dict(self.metric_usage),
            "domain_usage": dict(self.domain_usage),
            "searches_per_minute": self.total_searches / elapsed_minutes if elapsed_minutes > 0 else 0,
        }


class SimilaritySearchService:
    """
    High-level similarity search service (Facade Pattern).
    
    This service provides semantic similarity search with:
    - Multiple similarity metrics
    - Domain-specific thresholds
    - Query deduplication
    - Result ranking
    - Rich metrics and analytics
    - Batch search operations
    
    IMPORTANT: This service delegates ALL indexing operations to UnifiedIndexManager.
    It does NOT maintain its own index. This ensures consistency across the system.
    """
    
    def __init__(
        self,
        metric: SimilarityMetric = SimilarityMetric.COSINE,
        dimension: int = 384,  # Default for all-MiniLM-L6-v2
        threshold_config: Optional[DomainThresholdConfig] = None,
        enable_deduplication: bool = True,
        index_config: Optional[Dict] = None,
        index_manager: Optional['UnifiedIndexManager'] = None,
    ):
        """
        Initialize similarity search service.
        
        Args:
            metric: Similarity metric to use
            dimension: Embedding dimension
            threshold_config: Domain threshold configuration (deprecated - uses index_manager)
            enable_deduplication: Whether to enable query deduplication
            index_config: HNSW index configuration (deprecated - uses index_manager)
            index_manager: UnifiedIndexManager instance for all index operations
        """
        self.metric = metric
        self.dimension = dimension
        self.enable_deduplication = enable_deduplication
        
        # Get similarity algorithm (for reference)
        self.similarity_algorithm = SimilarityAlgorithmFactory.get_algorithm(metric)
        
        # Unified index manager - the single source of truth
        self._index_manager: Optional['UnifiedIndexManager'] = index_manager
        
        # Fallback threshold config (used only if index_manager not available)
        self._fallback_threshold_config = threshold_config or DomainThresholdConfig()
        
        # Query deduplication (value-add feature)
        self.deduplicator = QueryDeduplicator() if enable_deduplication else None
        
        # Metrics (value-add feature)
        self.metrics = SimilaritySearchMetrics()
        
        # Result cache (for repeated identical queries)
        self.result_cache: Dict[str, SimilaritySearchResult] = {}
        self.cache_stats = {"hits": 0, "misses": 0}
        
        logger.info(
            f"SimilaritySearchService initialized: metric={metric.value}, "
            f"dimension={dimension}, index_manager={'connected' if index_manager else 'not set'}"
        )
    
    def set_index_manager(self, index_manager: 'UnifiedIndexManager') -> None:
        """
        Set the unified index manager for index operations.
        
        Args:
            index_manager: UnifiedIndexManager instance
        """
        self._index_manager = index_manager
        logger.info("Index manager connected to SimilaritySearchService")
    
    @property
    def index_manager(self) -> Optional['UnifiedIndexManager']:
        """Get the current index manager."""
        return self._index_manager
    
    @property
    def is_ready(self) -> bool:
        """Check if service is ready (index manager connected)."""
        return self._index_manager is not None
    
    def _get_threshold(self, domain: DomainType) -> float:
        """Get threshold from index manager or fallback config."""
        if self._index_manager:
            return self._index_manager.get_threshold(domain.value)
        return self._fallback_threshold_config.get_threshold(domain)
    
    def _get_index_size(self) -> int:
        """Get current index size."""
        if self._index_manager:
            return self._index_manager.size()
        return 0
    
    def add_to_index(
        self,
        item_id: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
        query_text: str = "",
        tenant_id: Optional[str] = None,
        domain: str = "general",
    ) -> None:
        """
        Add item to similarity search index via UnifiedIndexManager.
        
        Args:
            item_id: Unique identifier
            embedding: Embedding vector
            metadata: Optional metadata
            query_text: Original query text (for dedup and exact matching)
            tenant_id: Tenant ID for multi-tenancy
            domain: Domain type for threshold selection
            
        Raises:
            SimilarityError: If index_manager not set or indexing fails
        """
        if len(embedding) != self.dimension:
            raise SimilarityError(
                f"Embedding dimension {len(embedding)} != expected {self.dimension}",
                error_code="DIMENSION_MISMATCH"
            )
        
        if not self._index_manager:
            raise SimilarityError(
                "Index manager not configured. Call set_index_manager() first.",
                error_code="INDEX_NOT_CONFIGURED"
            )
        
        try:
            success = self._index_manager.add(
                item_id=item_id,
                embedding=embedding,
                query_text=query_text,
                tenant_id=tenant_id,
                domain=domain,
                metadata=metadata,
            )
            
            if success:
                logger.debug(f"Added item {item_id} to unified index via SimilaritySearchService")
            else:
                raise SimilarityError(
                    f"Failed to add item {item_id} to index",
                    error_code="INDEXING_FAILED"
                )
                
        except SimilarityError:
            raise
        except Exception as e:
            raise SimilarityError(
                f"Failed to add item to index: {str(e)}",
                error_code="INDEXING_ERROR"
            )
    
    def search(
        self,
        request: SimilaritySearchRequest,
        tenant_id: Optional[str] = None,
    ) -> SimilaritySearchResult:
        """
        Perform similarity search via UnifiedIndexManager.
        
        Args:
            request: Search request with query embedding and parameters
            tenant_id: Tenant ID for multi-tenancy filtering
            
        Returns:
            SimilaritySearchResult with ranked matches
        
        Raises:
            SimilarityError: If search fails
        """
        if len(request.query_embedding) != self.dimension:
            raise SimilarityError(
                f"Query dimension {len(request.query_embedding)} != expected {self.dimension}",
                error_code="QUERY_DIMENSION_MISMATCH"
            )
        
        if not self._index_manager:
            raise SimilarityError(
                "Index manager not configured. Call set_index_manager() first.",
                error_code="INDEX_NOT_CONFIGURED"
            )
        
        start_time = time.time()
        is_cached = False
        is_deduped = False
        
        # Check for query deduplication (fast pre-check)
        if self.enable_deduplication and request.query_text:
            if self.deduplicator.is_duplicate(request.query_text):
                is_deduped = True
                logger.debug(f"Query {request.query_id} is deduplicated")
        
        # Get similarity threshold
        threshold = request.threshold or self._get_threshold(request.domain)
        
        try:
            # Delegate search to UnifiedIndexManager
            search_results = self._index_manager.search(
                embedding=request.query_embedding,
                k=request.top_k,
                threshold=request.min_score,  # Use min_score for initial filtering
                domain=request.domain.value if hasattr(request.domain, 'value') else str(request.domain),
                tenant_id=tenant_id,
            )
            
            # Convert to SimilarityScore objects with ranking
            matches: List[SimilarityScore] = []
            for rank, (item_id, similarity, entry) in enumerate(search_results, 1):
                if similarity >= request.min_score:
                    is_match = similarity >= threshold
                    
                    # Get metadata from entry
                    entry_metadata = entry.metadata if entry else {}
                    
                    score = SimilarityScore(
                        query_id=request.query_id,
                        candidate_id=item_id,
                        similarity=similarity,
                        metric=request.metric,
                        is_match=is_match,
                        threshold_used=threshold,
                        rank=rank,
                        metadata=entry_metadata,
                    )
                    matches.append(score)
            
            search_time_ms = (time.time() - start_time) * 1000
            
            # Create result
            result = SimilaritySearchResult(
                query_id=request.query_id,
                matches=matches,
                total_candidates=self._get_index_size(),
                search_time_ms=search_time_ms,
                metric=request.metric,
                threshold=threshold,
                is_cached=is_cached,
            )
            
            # Record metrics (value-add analytics)
            num_matches = sum(1 for m in matches if m.is_match)
            self.metrics.record_search(
                num_candidates=self._get_index_size(),
                num_matches=num_matches,
                search_time_ms=search_time_ms,
                metric=request.metric,
                domain=request.domain,
                is_deduplicated=is_deduped,
            )
            
            # Register query for future deduplication
            if self.enable_deduplication and request.query_text:
                self.deduplicator.add_query(request.query_text)
            
            return result
            
        except SimilarityError:
            raise
        except Exception as e:
            raise SimilarityError(
                f"Similarity search failed: {str(e)}",
                error_code="SEARCH_ERROR"
            )
    
    def batch_search(
        self,
        requests: List[SimilaritySearchRequest],
        tenant_id: Optional[str] = None,
    ) -> List[SimilaritySearchResult]:
        """
        Perform batch similarity searches.
        
        Args:
            requests: List of search requests
            tenant_id: Tenant ID for multi-tenancy filtering
            
        Returns:
            List of search results in same order as requests
        """
        results = []
        for request in requests:
            try:
                result = self.search(request, tenant_id=tenant_id)
                results.append(result)
            except SimilarityError as e:
                logger.error(f"Batch search failed for query {request.query_id}: {e.message}")
                # Return empty result on error
                results.append(SimilaritySearchResult(
                    query_id=request.query_id,
                    matches=[],
                    total_candidates=self._get_index_size(),
                    search_time_ms=0.0,
                    metric=request.metric,
                    threshold=self._get_threshold(request.domain),
                ))
        
        return results
    
    def get_metrics(self) -> Dict:
        """Get comprehensive service metrics."""
        index_stats = {}
        if self._index_manager:
            index_stats = self._index_manager.get_stats()
        
        return {
            "search_metrics": self.metrics.get_stats(),
            "deduplication": (
                self.deduplicator.get_stats() if self.enable_deduplication else None
            ),
            "index": index_stats,
            "index_manager_connected": self._index_manager is not None,
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = SimilaritySearchMetrics()
        if self.deduplicator:
            self.deduplicator.dedup_stats = {"total_checks": 0, "duplicates_found": 0}
    
    def clear_index(self, tenant_id: Optional[str] = None) -> None:
        """
        Clear items from the unified index.
        
        Args:
            tenant_id: If provided, only clear items for this tenant
        """
        if not self._index_manager:
            logger.warning("Index manager not configured, nothing to clear")
            return
            
        count = self._index_manager.clear(tenant_id)
        logger.info(f"Cleared {count} items from unified index via SimilaritySearchService")
    
    def delete_from_index(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        """
        Delete a specific item from the unified index.
        
        Args:
            item_id: Item ID to delete
            tenant_id: Tenant ID for the item
            
        Returns:
            True if deleted, False if not found
        """
        if not self._index_manager:
            logger.warning("Index manager not configured")
            return False
            
        return self._index_manager.delete(item_id, tenant_id)
    
    def contains(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        """Check if item exists in the unified index."""
        if not self._index_manager:
            return False
        return self._index_manager.contains(item_id, tenant_id)
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SimilaritySearchService("
            f"metric={self.metric.value}, "
            f"dimension={self.dimension}, "
            f"index_manager={'connected' if self._index_manager else 'not set'}, "
            f"items={self._get_index_size()}"
            f")"
        )
