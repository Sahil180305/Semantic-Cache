"""
L1 In-Memory Cache Layer

High-performance in-memory cache using HNSW for semantic similarity search.
Integrates embeddings and similarity search with configurable eviction policies
and comprehensive metrics tracking.

Features:
- HNSW-based semantic search for query matching
- Query deduplication with exact and semantic matching
- Configurable eviction policies (LRU, LFU, TTL, FIFO, Adaptive)
- Memory management with configurable limits
- Comprehensive hit rate and performance metrics
- Domain-aware threshold configuration
"""

import hashlib
import time
from typing import Dict, List, Optional, Tuple, Any
from collections import OrderedDict

from src.cache.base import (
    CacheEntry, CacheMetrics, CacheConfig, EvictionPolicy, CacheHitReason,
    CacheBackendInterface, EvictionPolicyInterface
)
from src.cache.policies import create_eviction_policy
from src.similarity.index import HNSWIndex
from src.similarity.base import (
    SimilarityAlgorithm, SimilarityAlgorithmFactory, SimilarityMetric, DomainType
)


class L1Cache(CacheBackendInterface):
    """
    L1 In-Memory Cache using HNSW for similarity-based retrieval.
    
    Provides:
    - Fast semantic search using HNSW indexing
    - Exact text deduplication for identical queries
    - Configurable memory and size limits
    - Pluggable eviction policies
    - Domain-aware threshold configuration
    - Comprehensive metrics tracking
    """
    
    def __init__(self, config: CacheConfig):
        """
        Initialize L1 cache.
        
        Args:
            config: Cache configuration
        """
        self.config = config
        
        # Storage
        self.entries: Dict[str, CacheEntry] = OrderedDict()  # query_id -> entry
        self.text_to_id: Dict[str, str] = {}  # query_text_hash -> query_id (for dedup)
        
        # HNSW indexing for similarity search
        similarity_algo = SimilarityAlgorithmFactory.get_algorithm(SimilarityMetric.COSINE)
        self.hnsw_index = HNSWIndex(
            dimension=config.embedding_dimension,
            similarity_algorithm=similarity_algo,
            m=16,
            ef=200,
            max_m=48,
            seed=42,
        )
        
        # Eviction policy
        self.eviction_policy = create_eviction_policy(
            config.eviction_policy.value,
            ttl_seconds=config.ttl_seconds
        )
        
        # Metrics
        self.metrics = CacheMetrics()
        
        # Internal state
        self._next_query_id = 0
    
    def _generate_query_id(self) -> str:
        """Generate unique query ID."""
        query_id = f"q_{self._next_query_id}"
        self._next_query_id += 1
        return query_id
    
    def _hash_query_text(self, text: str) -> str:
        """Compute SHA256 hash of query text for deduplication."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def _check_memory_limit(self, new_entry_size: float) -> None:
        """
        Check if adding new entry would exceed memory limit.
        Evict entries if necessary.
        
        Args:
            new_entry_size: Size of new entry in bytes
        """
        total_memory = self.memory_usage_mb()
        new_total = total_memory + (new_entry_size / 1024 / 1024)
        
        while new_total > self.config.max_memory_mb and len(self.entries) > 0:
            victim_id = self.eviction_policy.select_victim(self.entries, time.time())
            if victim_id is None:
                break
            
            self._evict_entry(victim_id, "memory")
            total_memory = self.memory_usage_mb()
            new_total = total_memory + (new_entry_size / 1024 / 1024)
    
    def _check_size_limit(self) -> None:
        """
        Check if cache exceeds size limit.
        Evict entries if necessary.
        """
        while len(self.entries) > self.config.max_size:
            victim_id = self.eviction_policy.select_victim(self.entries, time.time())
            if victim_id is None:
                break
            self._evict_entry(victim_id, "size")
    
    def _evict_entry(self, query_id: str, reason: str) -> None:
        """
        Evict entry from cache.
        
        Args:
            query_id: ID of entry to evict
            reason: Reason for eviction ("lru", "lfu", "ttl", "memory", "size")
        """
        if query_id not in self.entries:
            return
        
        entry = self.entries[query_id]
        
        # Remove from HNSW index
        try:
            # HNSW index doesn't have delete, so mark as invalid in separate tracking
            pass
        except Exception:
            pass
        
        # Remove from text dedup cache
        text_hash = self._hash_query_text(entry.query_text)
        if text_hash in self.text_to_id:
            del self.text_to_id[text_hash]
        
        # Remove from main storage
        del self.entries[query_id]
        
        # Update metrics
        if reason == "lru":
            self.metrics.evictions_lru += 1
        elif reason == "lfu":
            self.metrics.evictions_lfu += 1
        elif reason == "ttl":
            self.metrics.evictions_ttl += 1
        elif reason == "memory":
            self.metrics.evictions_memory += 1
    
    def put(self, entry: CacheEntry) -> bool:
        """
        Store entry in cache.
        
        Args:
            entry: CacheEntry to store
            
        Returns:
            True if stored successfully
        """
        # Calculate memory footprint
        memory_size = entry.calculate_memory(self.config.embedding_dimension)
        
        # Check memory limits
        self._check_memory_limit(memory_size)
        
        # Use provided query_id or generate new one
        if not entry.query_id or entry.query_id.startswith("q_"):
            entry.query_id = self._generate_query_id()
        
        # Don't overwrite if already exists
        if entry.query_id in self.entries:
            # Update existing entry instead
            self.entries[entry.query_id] = entry
        else:
            self.entries[entry.query_id] = entry
        
        # Add to HNSW index
        try:
            self.hnsw_index.insert(
                entry.query_id,
                entry.embedding,
                metadata={"text": entry.query_text, "domain": entry.domain}
            )
        except ValueError:
            # Entry already in index, that's ok
            pass
        
        # Update text deduplication cache
        text_hash = self._hash_query_text(entry.query_text)
        self.text_to_id[text_hash] = entry.query_id
        
        # Check size limit
        self._check_size_limit()
        
        # Update metrics
        self.metrics.current_entries = len(self.entries)
        self.metrics.current_memory_mb = self.memory_usage_mb()
        if self.metrics.current_memory_mb > self.metrics.peak_memory_mb:
            self.metrics.peak_memory_mb = self.metrics.current_memory_mb
        
        return True
    
    def get(self, query_id: str) -> Optional[CacheEntry]:
        """
        Retrieve entry by ID.
        
        Args:
            query_id: Query identifier
            
        Returns:
            CacheEntry if found and not expired, None otherwise
        """
        if query_id not in self.entries:
            return None
        
        entry = self.entries[query_id]
        
        # Check expiration
        if entry.is_expired(self.config.ttl_seconds):
            self._evict_entry(query_id, "ttl")
            return None
        
        # Record access for eviction policies
        entry.record_access()
        self.eviction_policy.update_on_access(entry, time.time())
        
        return entry
    
    def search_similar(
        self,
        embedding: List[float],
        k: int = 5,
        threshold: float = 0.85,
    ) -> List[Tuple[str, float]]:
        """
        Search for semantically similar entries using HNSW.
        
        Args:
            embedding: Query embedding
            k: Number of results
            threshold: Minimum similarity threshold
            
        Returns:
            List of (query_id, similarity) tuples sorted by similarity (descending)
        """
        if len(self.entries) == 0:
            return []
        
        # Search HNSW index
        results = self.hnsw_index.search(embedding, k=k)
        
        # Filter by threshold
        filtered = [(qid, sim) for qid, sim in results if sim >= threshold]
        
        # Verify entries are not expired
        valid_results = []
        for query_id, similarity in filtered:
            entry = self.entries.get(query_id)
            if entry and not entry.is_expired(self.config.ttl_seconds):
                valid_results.append((query_id, similarity))
        
        return valid_results
    
    def find_exact_match(self, query_text: str) -> Optional[str]:
        """
        Find entry by exact query text match.
        
        Args:
            query_text: Original query text
            
        Returns:
            Query ID if exact match found, None otherwise
        """
        if not self.config.enable_exact_match:
            return None
        
        text_hash = self._hash_query_text(query_text)
        if text_hash in self.text_to_id:
            query_id = self.text_to_id[text_hash]
            entry = self.entries.get(query_id)
            if entry and not entry.is_expired(self.config.ttl_seconds):
                return query_id
        
        return None
    
    def find_match(
        self,
        query_text: str,
        embedding: List[float],
        domain: str = "general",
        similarity_threshold: Optional[float] = None,
        dedup_threshold: float = 0.99,
    ) -> Optional[Tuple[str, CacheHitReason, float]]:
        """
        Find matching cache entry using both exact and semantic matching.
        
        High-priority matching strategy:
        1. Exact text match (deterministic, fastest)
        2. Semantic similarity match (similarity search)
        3. Hybrid: combine both for robustness
        
        Args:
            query_text: Original query text
            embedding: Query embedding
            domain: Domain for threshold lookup
            similarity_threshold: Override threshold (uses domain default if None)
            dedup_threshold: Threshold for dedup hits (default 0.99)
            
        Returns:
            Tuple of (query_id, hit_reason, similarity) if match found, None otherwise
        """
        # Default threshold based on domain
        if similarity_threshold is None:
            # Use default threshold if not specified
            try:
                from src.similarity.base import DomainThresholdConfig, DomainType
                # Try to map string domain to DomainType enum
                domain_type_map = {
                    "medical": DomainType.MEDICAL,
                    "legal": DomainType.LEGAL,
                    "financial": DomainType.FINANCIAL,
                    "ecommerce": DomainType.ECOMMERCE,
                    "general": DomainType.GENERAL,
                }
                domain_enum = domain_type_map.get(domain.lower(), DomainType.GENERAL)
                domain_config = DomainThresholdConfig()
                similarity_threshold = domain_config.get_threshold(domain_enum)
            except Exception:
                # Fallback to 0.85 if config fails
                similarity_threshold = 0.85
        
        # Strategy 1: Exact match (fastest path)
        if self.config.enable_exact_match:
            exact_match_id = self.find_exact_match(query_text)
            if exact_match_id:
                self.metrics.exact_match_hits += 1
                return (exact_match_id, CacheHitReason.EXACT_MATCH, 1.0)
        
        # Strategy 2: Semantic similarity
        semantic_results = self.search_similar(embedding, k=1, threshold=similarity_threshold)
        
        if semantic_results:
            query_id, similarity = semantic_results[0]
            
            # Check if it's a dedup hit (very high similarity)
            if similarity >= dedup_threshold:
                self.metrics.duplicate_queries += 1
            
            self.metrics.semantic_match_hits += 1
            return (query_id, CacheHitReason.SEMANTIC_MATCH, similarity)
        
        # No match found
        return None
    
    def delete(self, query_id: str) -> bool:
        """
        Delete entry from cache.
        
        Args:
            query_id: ID of entry to delete
            
        Returns:
            True if deleted, False if not found
        """
        if query_id not in self.entries:
            return False
        
        self._evict_entry(query_id, "manual")
        return True
    
    def clear(self) -> None:
        """Clear all entries from cache."""
        self.entries.clear()
        self.text_to_id.clear()
        self.eviction_policy.reset()
        # Note: Can't fully reset HNSW without recreating it
    
    def size(self) -> int:
        """Get number of entries."""
        return len(self.entries)
    
    def memory_usage_mb(self) -> float:
        """Estimate total memory usage in MB."""
        total_bytes = sum(
            entry.memory_estimate or 0
            for entry in self.entries.values()
        )
        return total_bytes / 1024 / 1024
    
    def get_metrics(self) -> CacheMetrics:
        """Get current metrics snapshot."""
        # Update current metrics
        self.metrics.current_entries = len(self.entries)
        self.metrics.current_memory_mb = self.memory_usage_mb()
        
        return self.metrics
    
    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        self.metrics = CacheMetrics()
    
    def record_hit(self) -> None:
        """Record a cache hit."""
        self.metrics.cache_hits += 1
        self.metrics.total_requests += 1
    
    def record_miss(self) -> None:
        """Record a cache miss."""
        self.metrics.cache_misses += 1
        self.metrics.total_requests += 1
    
    def record_lookup_time(self, latency_ms: float) -> None:
        """Record lookup latency."""
        self.metrics.total_latency_ms += latency_ms
    
    def record_response_time(self, latency_ms: float) -> None:
        """Record response time for hit."""
        self.metrics.total_response_time_ms += latency_ms
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        metrics = self.get_metrics()
        return metrics.to_dict()
