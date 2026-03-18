"""
Similarity Search Service

High-level service for semantic similarity search with:
- Multi-metric support (cosine, euclidean, inner product, etc.)
- Domain-adaptive thresholds
- HNSW in-memory indexing for fast search
- Query deduplication
- Result ranking and scoring
- Caching and metrics
"""

import time
import hashlib
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
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
from src.similarity.index import HNSWIndex
from src.core.exceptions import (
    SimilarityError,
    CacheError,
)
from src.utils.logging import get_logger

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
        self.query_cache[query_hash] = (text, datetime.utcnow())
    
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
    High-level similarity search service.
    
    Provides semantic similarity search with:
    - Multiple similarity metrics
    - Domain-specific thresholds
    - HNSW indexing
    - Query deduplication
    - Result ranking
    """
    
    def __init__(
        self,
        metric: SimilarityMetric = SimilarityMetric.COSINE,
        dimension: int = 384,  # Default for all-MiniLM-L6-v2
        threshold_config: Optional[DomainThresholdConfig] = None,
        enable_deduplication: bool = True,
        index_config: Optional[Dict] = None,
    ):
        """
        Initialize similarity search service.
        
        Args:
            metric: Similarity metric to use
            dimension: Embedding dimension
            threshold_config: Domain threshold configuration
            enable_deduplication: Whether to enable query deduplication
            index_config: HNSW index configuration
        """
        self.metric = metric
        self.dimension = dimension
        self.threshold_config = threshold_config or DomainThresholdConfig()
        self.enable_deduplication = enable_deduplication
        
        # Get similarity algorithm
        self.similarity_algorithm = SimilarityAlgorithmFactory.get_algorithm(metric)
        
        # Initialize index
        index_cfg = index_config or {}
        self.index = HNSWIndex(
            dimension=dimension,
            similarity_algorithm=self.similarity_algorithm,
            m=index_cfg.get("m", 16),
            ef=index_cfg.get("ef", 200),
            max_m=index_cfg.get("max_m", 48),
        )
        
        # Query deduplication
        self.deduplicator = QueryDeduplicator() if enable_deduplication else None
        
        # Metrics
        self.metrics = SimilaritySearchMetrics()
        
        # Result cache
        self.result_cache: Dict[str, SimilaritySearchResult] = {}
        self.cache_stats = {"hits": 0, "misses": 0}
    
    def add_to_index(
        self,
        item_id: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Add item to similarity search index.
        
        Args:
            item_id: Unique identifier
            embedding: Embedding vector
            metadata: Optional metadata
        """
        if len(embedding) != self.dimension:
            raise SimilarityError(
                f"Embedding dimension {len(embedding)} != expected {self.dimension}",
                error_code="DIMENSION_MISMATCH"
            )
        
        try:
            self.index.insert(item_id, embedding, metadata)
            logger.debug(f"Added item {item_id} to similarity index")
        except Exception as e:
            raise SimilarityError(
                f"Failed to add item to index: {str(e)}",
                error_code="INDEXING_ERROR"
            )
    
    def search(self, request: SimilaritySearchRequest) -> SimilaritySearchResult:
        """
        Perform similarity search.
        
        Args:
            request: Search request with query embedding and parameters
            
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
        
        start_time = time.time()
        is_cached = False
        is_deduped = False
        
        # Check for query deduplication
        if self.enable_deduplication and request.query_text:
            if self.deduplicator.is_duplicate(request.query_text):
                is_deduped = True
                logger.debug(f"Query {request.query_id} is deduplicated")
        
        # Get similarity threshold
        threshold = request.threshold or self.threshold_config.get_threshold(request.domain)
        
        try:
            # Search index
            search_results = self.index.search(
                request.query_embedding,
                k=request.top_k,
                ef=request.metadata.get("ef") if request.metadata else None,
            )
            
            # Convert to SimilarityScore objects
            matches: List[SimilarityScore] = []
            for rank, (item_id, similarity) in enumerate(search_results, 1):
                if similarity >= request.min_score:
                    is_match = similarity >= threshold
                    
                    score = SimilarityScore(
                        query_id=request.query_id,
                        candidate_id=item_id,
                        similarity=similarity,
                        metric=request.metric,
                        is_match=is_match,
                        threshold_used=threshold,
                        rank=rank,
                        metadata=self.index.metadata.get(item_id),
                    )
                    matches.append(score)
            
            search_time_ms = (time.time() - start_time) * 1000
            
            # Create result
            result = SimilaritySearchResult(
                query_id=request.query_id,
                matches=matches,
                total_candidates=len(self.index.data),
                search_time_ms=search_time_ms,
                metric=request.metric,
                threshold=threshold,
                is_cached=is_cached,
            )
            
            # Record metrics
            num_matches = sum(1 for m in matches if m.is_match)
            self.metrics.record_search(
                num_candidates=len(self.index.data),
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
            
        except Exception as e:
            raise SimilarityError(
                f"Similarity search failed: {str(e)}",
                error_code="SEARCH_ERROR"
            )
    
    def batch_search(
        self,
        requests: List[SimilaritySearchRequest],
    ) -> List[SimilaritySearchResult]:
        """
        Perform batch similarity searches.
        
        Args:
            requests: List of search requests
            
        Returns:
            List of search results in same order as requests
        """
        results = []
        for request in requests:
            try:
                result = self.search(request)
                results.append(result)
            except SimilarityError as e:
                logger.error(f"Batch search failed for query {request.query_id}: {e.message}")
                # Return empty result on error
                results.append(SimilaritySearchResult(
                    query_id=request.query_id,
                    matches=[],
                    total_candidates=len(self.index.data),
                    search_time_ms=0.0,
                    metric=request.metric,
                    threshold=self.threshold_config.get_threshold(request.domain),
                ))
        
        return results
    
    def get_metrics(self) -> Dict:
        """Get comprehensive service metrics."""
        return {
            "search_metrics": self.metrics.get_stats(),
            "deduplication": (
                self.deduplicator.get_stats() if self.enable_deduplication else None
            ),
            "index": self.index.get_stats(),
            "threshold_config": self.threshold_config.to_dict(),
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = SimilaritySearchMetrics()
        if self.deduplicator:
            self.deduplicator.dedup_stats = {"total_checks": 0, "duplicates_found": 0}
    
    def clear_index(self) -> None:
        """Clear all indexed items."""
        self.index.data.clear()
        self.index.metadata.clear()
        self.index.graph.clear()
        self.index.node_id_map.clear()
        self.index.node_reverse_map.clear()
        self.index.node_levels.clear()
        self.index.entry_point = None
        self.index.next_node_id = 0
        logger.info("Similarity search index cleared")
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SimilaritySearchService("
            f"metric={self.metric.value}, "
            f"dimension={self.dimension}, "
            f"items={len(self.index.data)}"
            f")"
        )
