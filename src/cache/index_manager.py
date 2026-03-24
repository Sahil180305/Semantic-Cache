"""
Unified Index Manager for Semantic Cache

Provides a single, thread-safe HNSW index that is shared across:
- L1Cache (for semantic lookups)
- SimilaritySearchService (for search API)
- CacheManager (for unified operations)

This solves the integration gap where separate indexes existed
and items cached were not searchable.
"""

import threading
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

from src.similarity.index import HNSWIndex
from src.similarity.base import (
    SimilarityMetric,
    SimilarityAlgorithmFactory,
    DomainType,
    DomainThresholdConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """Configuration for the unified index."""
    dimension: int = 384  # Default for all-MiniLM-L6-v2
    metric: SimilarityMetric = SimilarityMetric.COSINE
    m: int = 16  # HNSW M parameter
    ef: int = 200  # HNSW ef parameter
    max_m: int = 48  # HNSW max_m parameter
    seed: int = 42


@dataclass
class IndexEntry:
    """Metadata stored alongside each indexed item."""
    item_id: str
    query_text: str
    tenant_id: Optional[str] = None
    domain: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class UnifiedIndexManager:
    """
    Thread-safe unified index manager for semantic cache.
    
    Provides a single HNSW index that:
    - Is shared across all cache components
    - Supports tenant isolation via ID prefixing
    - Tracks metadata for each indexed item
    - Provides domain-aware similarity thresholds
    """
    
    _instance: Optional['UnifiedIndexManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[IndexConfig] = None):
        """Singleton pattern for unified index."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[IndexConfig] = None):
        """Initialize the unified index manager."""
        if self._initialized:
            return
            
        self.config = config or IndexConfig()
        
        # Create HNSW index with configured similarity metric
        similarity_algo = SimilarityAlgorithmFactory.get_algorithm(self.config.metric)
        self._index = HNSWIndex(
            dimension=self.config.dimension,
            similarity_algorithm=similarity_algo,
            m=self.config.m,
            ef=self.config.ef,
            max_m=self.config.max_m,
            seed=self.config.seed,
        )
        
        # Thread lock for index operations
        self._index_lock = threading.RLock()
        
        # Entry metadata storage
        self._entries: Dict[str, IndexEntry] = {}
        
        # Domain threshold configuration
        self._threshold_config = DomainThresholdConfig()
        
        # Metrics
        self._stats = {
            "total_indexed": 0,
            "total_searches": 0,
            "total_deletions": 0,
        }
        
        self._initialized = True
        logger.info(f"UnifiedIndexManager initialized with dimension={self.config.dimension}")
    
    @classmethod
    def get_instance(cls, config: Optional[IndexConfig] = None) -> 'UnifiedIndexManager':
        """Get or create the singleton instance."""
        return cls(config)
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None
    
    def add(
        self,
        item_id: str,
        embedding: List[float],
        query_text: str,
        tenant_id: Optional[str] = None,
        domain: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add an item to the unified index.
        
        Args:
            item_id: Unique identifier (will be prefixed with tenant_id if provided)
            embedding: The embedding vector (must match configured dimension)
            query_text: Original query text for deduplication
            tenant_id: Optional tenant ID for isolation
            domain: Domain type for threshold selection
            metadata: Additional metadata to store
            
        Returns:
            True if successfully added, False otherwise
        """
        if len(embedding) != self.config.dimension:
            logger.error(f"Embedding dimension mismatch: {len(embedding)} != {self.config.dimension}")
            return False
        
        # Create full ID with tenant prefix for isolation
        full_id = self._make_full_id(item_id, tenant_id)
        
        with self._index_lock:
            try:
                # Check if already exists
                if full_id in self._index.data:
                    logger.debug(f"Item {full_id} already in index, updating")
                    # Update metadata only (HNSW doesn't support update)
                    self._entries[full_id] = IndexEntry(
                        item_id=item_id,
                        query_text=query_text,
                        tenant_id=tenant_id,
                        domain=domain,
                        metadata=metadata or {},
                    )
                    return True
                
                # Insert into HNSW index
                self._index.insert(
                    full_id,
                    embedding,
                    metadata={"text": query_text, "domain": domain}
                )
                
                # Store entry metadata
                import time
                self._entries[full_id] = IndexEntry(
                    item_id=item_id,
                    query_text=query_text,
                    tenant_id=tenant_id,
                    domain=domain,
                    metadata=metadata or {},
                    created_at=time.time(),
                )
                
                self._stats["total_indexed"] += 1
                logger.debug(f"Added item {full_id} to unified index")
                return True
                
            except Exception as e:
                logger.error(f"Failed to add item {full_id} to index: {e}")
                return False
    
    def search(
        self,
        embedding: List[float],
        k: int = 10,
        threshold: Optional[float] = None,
        domain: str = "general",
        tenant_id: Optional[str] = None,
    ) -> List[Tuple[str, float, IndexEntry]]:
        """
        Search for similar items in the index.
        
        Args:
            embedding: Query embedding vector
            k: Number of results to return
            threshold: Minimum similarity threshold (uses domain default if None)
            domain: Domain for threshold lookup
            tenant_id: Filter results to specific tenant
            
        Returns:
            List of (item_id, similarity, entry) tuples sorted by similarity
        """
        if len(embedding) != self.config.dimension:
            logger.error(f"Query dimension mismatch: {len(embedding)} != {self.config.dimension}")
            return []
        
        # Get domain-specific threshold if not provided
        if threshold is None:
            try:
                domain_enum = DomainType(domain) if domain in [d.value for d in DomainType] else DomainType.GENERAL
                threshold = self._threshold_config.get_threshold(domain_enum)
            except ValueError:
                threshold = 0.85
        
        with self._index_lock:
            try:
                # Search HNSW index
                raw_results = self._index.search(embedding, k=k * 2)  # Get extra for filtering
                
                self._stats["total_searches"] += 1
                
                # Filter and enrich results
                results = []
                for full_id, similarity in raw_results:
                    # Filter by threshold
                    if similarity < threshold:
                        continue
                    
                    # Filter by tenant if specified
                    entry = self._entries.get(full_id)
                    if entry is None:
                        continue
                    
                    if tenant_id and entry.tenant_id != tenant_id:
                        continue
                    
                    results.append((entry.item_id, similarity, entry))
                    
                    if len(results) >= k:
                        break
                
                return results
                
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
    
    def search_by_text(
        self,
        query_text: str,
        embedding: List[float],
        k: int = 10,
        threshold: Optional[float] = None,
        domain: str = "general",
        tenant_id: Optional[str] = None,
        exact_match_boost: float = 0.05,
    ) -> List[Tuple[str, float, IndexEntry, bool]]:
        """
        Search with both semantic similarity and exact text matching.
        
        Args:
            query_text: Original query text
            embedding: Query embedding
            k: Number of results
            threshold: Similarity threshold
            domain: Domain for threshold
            tenant_id: Tenant filter
            exact_match_boost: Bonus similarity for exact text matches
            
        Returns:
            List of (item_id, similarity, entry, is_exact_match) tuples
        """
        # First check for exact text match
        exact_match = self._find_exact_match(query_text, tenant_id)
        
        # Then do semantic search
        semantic_results = self.search(embedding, k, threshold, domain, tenant_id)
        
        # Combine results
        results = []
        seen_ids = set()
        
        # Add exact match first with boosted score
        if exact_match:
            entry = self._entries.get(self._make_full_id(exact_match, tenant_id))
            if entry:
                results.append((exact_match, 1.0, entry, True))
                seen_ids.add(exact_match)
        
        # Add semantic results
        for item_id, similarity, entry in semantic_results:
            if item_id not in seen_ids:
                # Check for near-exact match
                is_exact = entry.query_text.lower().strip() == query_text.lower().strip()
                final_sim = min(1.0, similarity + exact_match_boost) if is_exact else similarity
                results.append((item_id, final_sim, entry, is_exact))
                seen_ids.add(item_id)
        
        # Sort by similarity
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:k]
    
    def _find_exact_match(self, query_text: str, tenant_id: Optional[str] = None) -> Optional[str]:
        """Find exact text match in index."""
        normalized = query_text.lower().strip()
        
        for full_id, entry in self._entries.items():
            if entry.query_text.lower().strip() == normalized:
                if tenant_id is None or entry.tenant_id == tenant_id:
                    return entry.item_id
        
        return None
    
    def delete(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        """
        Remove an item from the index.
        
        Note: HNSW doesn't support true deletion, so we mark it as deleted
        in metadata and filter during search. Full rebuild needed for cleanup.
        
        Args:
            item_id: Item ID to delete
            tenant_id: Tenant ID for the item
            
        Returns:
            True if deleted, False if not found
        """
        full_id = self._make_full_id(item_id, tenant_id)
        
        with self._index_lock:
            if full_id in self._entries:
                del self._entries[full_id]
                # Note: Can't delete from HNSW, will be orphaned until rebuild
                self._stats["total_deletions"] += 1
                logger.debug(f"Deleted item {full_id} from index metadata")
                return True
            
            return False
    
    def clear(self, tenant_id: Optional[str] = None) -> int:
        """
        Clear all items from the index.
        
        Args:
            tenant_id: If provided, only clear items for this tenant
            
        Returns:
            Number of items cleared
        """
        with self._index_lock:
            if tenant_id is None:
                count = len(self._entries)
                self._entries.clear()
                # Rebuild empty index
                similarity_algo = SimilarityAlgorithmFactory.get_algorithm(self.config.metric)
                self._index = HNSWIndex(
                    dimension=self.config.dimension,
                    similarity_algorithm=similarity_algo,
                    m=self.config.m,
                    ef=self.config.ef,
                    max_m=self.config.max_m,
                    seed=self.config.seed,
                )
                logger.info(f"Cleared all {count} items from unified index")
                return count
            else:
                # Clear only tenant's items
                to_delete = [
                    full_id for full_id, entry in self._entries.items()
                    if entry.tenant_id == tenant_id
                ]
                for full_id in to_delete:
                    del self._entries[full_id]
                logger.info(f"Cleared {len(to_delete)} items for tenant {tenant_id}")
                return len(to_delete)
    
    def get_entry(self, item_id: str, tenant_id: Optional[str] = None) -> Optional[IndexEntry]:
        """Get entry metadata by ID."""
        full_id = self._make_full_id(item_id, tenant_id)
        return self._entries.get(full_id)
    
    def contains(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        """Check if item exists in index."""
        full_id = self._make_full_id(item_id, tenant_id)
        return full_id in self._entries
    
    def size(self, tenant_id: Optional[str] = None) -> int:
        """Get number of items in index."""
        if tenant_id is None:
            return len(self._entries)
        return sum(1 for e in self._entries.values() if e.tenant_id == tenant_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            **self._stats,
            "current_size": len(self._entries),
            "dimension": self.config.dimension,
            "metric": self.config.metric.value,
            "index_stats": self._index.get_stats() if self._index else {},
        }
    
    def get_threshold(self, domain: str = "general") -> float:
        """Get similarity threshold for domain."""
        try:
            domain_enum = DomainType(domain) if domain in [d.value for d in DomainType] else DomainType.GENERAL
            return self._threshold_config.get_threshold(domain_enum)
        except ValueError:
            return 0.85
    
    def set_threshold(self, domain: str, threshold: float) -> None:
        """Set similarity threshold for domain."""
        try:
            domain_enum = DomainType(domain) if domain in [d.value for d in DomainType] else DomainType.GENERAL
            self._threshold_config.set_threshold(domain_enum, threshold)
        except ValueError:
            pass
    
    def _make_full_id(self, item_id: str, tenant_id: Optional[str] = None) -> str:
        """Create full ID with tenant prefix."""
        if tenant_id:
            return f"{tenant_id}:{item_id}"
        return item_id
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self.config.dimension
    
    @property
    def index(self) -> HNSWIndex:
        """Get underlying HNSW index (for advanced operations)."""
        return self._index
