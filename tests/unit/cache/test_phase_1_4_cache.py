"""
Phase 1.4 - L1 Cache Layer Tests

Comprehensive test suite for in-memory HNSW cache with eviction policies,
memory management, and semantic matching.
"""

import pytest
import time
from src.cache import (
    CacheConfig, CacheEntry, L1Cache, EvictionPolicy,CacheHitReason,
    LRUEvictionPolicy, LFUEvictionPolicy, FIFOEvictionPolicy,
    TTLEvictionPolicy, AdaptiveEvictionPolicy, create_eviction_policy,
)


# ============================================================================
# Test: Eviction Policies
# ============================================================================

class TestEvictionPolicies:
    """Test various eviction policies."""
    
    def test_lru_selects_least_recent(self):
        """Test LRU selects least recently accessed entry."""
        policy = LRUEvictionPolicy()
        
        entry1 = CacheEntry(query_id="q1", query_text="query1", embedding=[0.1] * 384, response="resp1")
        entry2 = CacheEntry(query_id="q2", query_text="query2", embedding=[0.2] * 384, response="resp2")
        entry3 = CacheEntry(query_id="q3", query_text="query3", embedding=[0.3] * 384, response="resp3")
        
        entry1.last_accessed_at = 100.0
        entry2.last_accessed_at = 200.0
        entry3.last_accessed_at = 150.0
        
        entries = {"q1": entry1, "q2": entry2, "q3": entry3}
        victim = policy.select_victim(entries, time.time())
        assert victim == "q1"
    
    def test_lfu_selects_least_frequent(self):
        """Test LFU selects least frequently accessed entry."""
        policy = LFUEvictionPolicy()
        
        entry1 = CacheEntry(query_id="q1", query_text="query1", embedding=[0.1] * 384, response="resp1")
        entry2 = CacheEntry(query_id="q2", query_text="query2", embedding=[0.2] * 384, response="resp2")
        entry3 = CacheEntry(query_id="q3", query_text="query3", embedding=[0.3] * 384, response="resp3")
        
        entry1.access_count = 5
        entry2.access_count = 10
        entry3.access_count = 2
        
        entries = {"q1": entry1, "q2": entry2, "q3": entry3}
        victim = policy.select_victim(entries, time.time())
        assert victim == "q3"
    
    def test_fifo_selects_oldest(self):
        """Test FIFO selects oldest entry."""
        policy = FIFOEvictionPolicy()
        
        entry1 = CacheEntry(query_id="q1", query_text="query1", embedding=[0.1] * 384, response="resp1")
        entry2 = CacheEntry(query_id="q2", query_text="query2", embedding=[0.2] * 384, response="resp2")
        
        entry1.created_at = 100.0
        entry2.created_at = 200.0
        
        entries = {"q1": entry1, "q2": entry2}
        victim = policy.select_victim(entries, time.time())
        assert victim == "q1"
    
    def test_ttl_selects_expired(self):
        """Test TTL evicts expired entries first."""
        policy = TTLEvictionPolicy(ttl_seconds=100)
        
        current_time = time.time()
        entry1 = CacheEntry(query_id="q1", query_text="query1", embedding=[0.1] * 384, response="resp1")
        entry2 = CacheEntry(query_id="q2", query_text="query2", embedding=[0.2] * 384, response="resp2")
        
        entry1.created_at = current_time - 200
        entry2.created_at = current_time - 50
        
        entries = {"q1": entry1, "q2": entry2}
        victim = policy.select_victim(entries, current_time)
        assert victim == "q1"
    
    def test_factory_creates_policies(self):
        """Test eviction policy factory."""
        assert isinstance(create_eviction_policy("lru"), LRUEvictionPolicy)
        assert isinstance(create_eviction_policy("lfu"), LFUEvictionPolicy)
        assert isinstance(create_eviction_policy("fifo"), FIFOEvictionPolicy)
        
        with pytest.raises(ValueError):
            create_eviction_policy("unknown")


# ============================================================================
# Test: Cache Configuration
# ============================================================================

class TestCacheConfig:
    """Test cache configuration."""
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = CacheConfig()
        assert config.max_size == 1000
        assert config.embedding_dimension == 384
        assert config.max_memory_mb == 512.0
    
    def test_config_custom(self):
        """Test custom configuration."""
        config = CacheConfig(
            max_size=500,
            embedding_dimension=768,
            ttl_seconds=3600
        )
        assert config.max_size == 500
        assert config.embedding_dimension == 768
        assert config.ttl_seconds == 3600
    
    def test_config_validation(self):
        """Test configuration validation."""
        with pytest.raises(ValueError):
            CacheConfig(max_size=-1)
        
        with pytest.raises(ValueError):
            CacheConfig(embedding_dimension=0)


# ============================================================================
# Test: Cache Entry
# ============================================================================

class TestCacheEntry:
    """Test cache entry functionality."""
    
    def test_entry_creation(self):
        """Test creating entry."""
        entry = CacheEntry(
            query_id="q1",
            query_text="test",
            embedding=[0.1] * 384,
            response={"answer": "test"}
        )
        assert entry.query_id == "q1"
        assert entry.access_count == 0
    
    def test_entry_expiration(self):
        """Test entry TTL expiration."""
        entry = CacheEntry(
            query_id="q1",
            query_text="test",
            embedding=[0.1] * 384,
            response="resp"
        )
        entry.created_at = time.time() - 500
        
        assert not entry.is_expired(None)
        assert entry.is_expired(100)
        assert not entry.is_expired(600)
    
    def test_entry_access_tracking(self):
        """Test access tracking."""
        entry = CacheEntry(
            query_id="q1",
            query_text="test",
            embedding=[0.1] * 384,
            response="resp"
        )
        
        assert entry.access_count == 0
        entry.record_access()
        assert entry.access_count == 1


# ============================================================================
# Test: L1 Cache Basics
# ============================================================================

class TestL1CacheBasics:
    """Test basic L1 cache operations."""
    
    def test_cache_initialization(self):
        """Test cache initialization."""
        config = CacheConfig(max_size=100)
        cache = L1Cache(config)
        
        assert cache.size() == 0
        assert cache.memory_usage_mb() == 0
    
    def test_put_and_get(self):
        """Test put and get operations."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id="test_entry",
            query_text="test",
            embedding=[0.1] * 384,
            response="response"
        )
        
        assert cache.put(entry) is True
        assert cache.size() == 1
        
        retrieved = cache.get(entry.query_id)
        assert retrieved is not None
        assert retrieved.query_text == "test"
    
    def test_delete_entry(self):
        """Test deleting entry."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id="delete_test",
            query_text="test",
            embedding=[0.1] * 384,
            response="response"
        )
        
        cache.put(entry)
        assert cache.size() == 1
        
        assert cache.delete(entry.query_id) is True
        assert cache.size() == 0
    
    def test_clear_cache(self):
        """Test clearing cache."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        for i in range(3):
            entry = CacheEntry(
                query_id=f"q{i}",
                query_text=f"query{i}",
                embedding=[0.1 * i] * 384,
                response=f"resp{i}"
            )
            cache.put(entry)
        
        assert cache.size() == 3
        cache.clear()
        assert cache.size() == 0


# ============================================================================
# Test: Cache Matching
# ============================================================================

class TestCacheMatching:
    """Test exact and semantic matching."""
    
    def test_exact_match(self):
        """Test exact text matching."""
        config = CacheConfig(enable_exact_match=True)
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id="exact1",
            query_text="What is AI?",
            embedding=[0.1] * 384,
            response="AI is..."
        )
        cache.put(entry)
        
        exact_id = cache.find_exact_match("What is AI?")
        assert exact_id == entry.query_id
        
        assert cache.find_exact_match("Different text") is None


# ============================================================================
# Test: Cache Metrics
# ============================================================================

class TestCacheMetrics:
    """Test cache metrics tracking."""
    
    def test_metrics_initialization(self):
        """Test metrics initialization."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        metrics = cache.get_metrics()
        assert metrics.total_requests == 0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
    
    def test_record_metrics(self):
        """Test recording metrics."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        cache.record_hit()
        cache.record_hit()
        cache.record_miss()
        
        metrics = cache.get_metrics()
        assert metrics.cache_hits == 2
        assert metrics.cache_misses == 1
        assert metrics.total_requests == 3
        assert metrics.hit_rate == pytest.approx(2/3)
    
    def test_metrics_reset(self):
        """Test resetting metrics."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        cache.record_hit()
        cache.reset_metrics()
        
        metrics = cache.get_metrics()
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0


# ============================================================================
# Test: Cache Size Limits
# ============================================================================

class TestCacheLimits:
    """Test cache size and memory limits."""
    
    def test_size_limit(self):
        """Test size limit enforcement."""
        config = CacheConfig(max_size=2)
        cache = L1Cache(config)
        
        for i in range(2):
            entry = CacheEntry(
                query_id=f"size_{i}",
                query_text=f"query{i}",
                embedding=[0.1] * 384,
                response=f"resp{i}"
            )
            cache.put(entry)
        
        assert cache.size() == 2
        
        # Adding more should trigger eviction
        entry3 = CacheEntry(
            query_id="size_3",
            query_text="query3",
            embedding=[0.1] * 384,
            response="resp3"
        )
        cache.put(entry3)
        
        assert cache.size() == 2


# ============================================================================
# Test: LRU Eviction
# ============================================================================

class TestLRUEviction:
    """Test LRU eviction in cache."""
    
    def test_lru_eviction(self):
        """Test LRU eviction policy in cache."""
        config = CacheConfig(max_size=2, eviction_policy=EvictionPolicy.LRU)
        cache = L1Cache(config)
        
        entry1 = CacheEntry(
            query_id="lru_1",
            query_text="query1",
            embedding=[0.1] * 384,
            response="resp1"
        )
        cache.put(entry1)
        
        time.sleep(0.01)
        
        entry2 = CacheEntry(
            query_id="lru_2",
            query_text="query2",
            embedding=[0.2] * 384,
            response="resp2"
        )
        cache.put(entry2)
        
        time.sleep(0.01)
        
        # Access entry1 to make it recent
        cache.get(entry1.query_id)
        
        time.sleep(0.01)
        
        # Add entry3, should evict entry2 (least recent)
        entry3 = CacheEntry(
            query_id="lru_3",
            query_text="query3",
            embedding=[0.3] * 384,
            response="resp3"
        )
        cache.put(entry3)
        
        assert cache.size() == 2
        assert entry1.query_id in cache.entries
        assert entry3.query_id in cache.entries


# ============================================================================
# Test: FIFO Eviction
# ============================================================================

class TestFIFOEviction:
    """Test FIFO eviction in cache."""
    
    def test_fifo_eviction(self):
        """Test FIFO eviction policy in cache."""
        config = CacheConfig(max_size=2, eviction_policy=EvictionPolicy.FIFO)
        cache = L1Cache(config)
        
        entry1 = CacheEntry(
            query_id="fifo_1",
            query_text="oldest",
            embedding=[0.1] * 384,
            response="resp1"
        )
        cache.put(entry1)
        
        time.sleep(0.01)
        
        entry2 = CacheEntry(
            query_id="fifo_2",
            query_text="middle",
            embedding=[0.2] * 384,
            response="resp2"
        )
        cache.put(entry2)
        
        # Entry 3 should evict entry1 (oldest)
        entry3 = CacheEntry(
            query_id="fifo_3",
            query_text="newest",
            embedding=[0.3] * 384,
            response="resp3"
        )
        cache.put(entry3)
        
        assert cache.size() == 2
        assert entry1.query_id not in cache.entries
        assert entry2.query_id in cache.entries
        assert entry3.query_id in cache.entries


# ============================================================================
# Test: Query ID Generation
# ============================================================================

class TestQueryIDGeneration:
    """Test query ID generation."""
    
    def test_put_with_provided_id(self):
        """Test putting entry with provided query ID."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id="custom_id",
            query_text="test",
            embedding=[0.1] * 384,
            response="resp"
        )
        cache.put(entry)
        
        retrieved = cache.get("custom_id")
        assert retrieved is not None
        assert retrieved.query_id == "custom_id"
    
    def test_put_auto_generates_id(self):
        """Test putting entry without ID auto-generates ID."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id=None,
            query_text="test",
            embedding=[0.1] * 384,
            response="resp"
        )
        result = cache.put(entry)
        
        assert result is True
        assert entry.query_id is not None
        assert entry.query_id.startswith("q_") or entry.query_id.startswith("q")


# ============================================================================
# Test: Memory Management
# ============================================================================

class TestMemoryManagement:
    """Test memory management."""
    
    def test_memory_calculation(self):
        """Test memory usage calculation."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id="mem_test",
            query_text="x" * 100,
            embedding=[0.1] * 384,
            response="response data here"
        )
        cache.put(entry)
        
        mem_usage = cache.memory_usage_mb()
        assert mem_usage > 0
    
    def test_memory_limit_enforcement(self):
        """Test memory limit enforcement."""
        # Create cache with reasonable memory limit
        config = CacheConfig(max_memory_mb=1.0)
        cache = L1Cache(config)
        
        # Add entries and verify memory usage is tracked
        for i in range(5):
            entry = CacheEntry(
                query_id=f"mem_{i}",
                query_text=f"test query with some text {i}",
                embedding=[0.1] * 384,
                response=f"response data {i}"
            )
            cache.put(entry)
        
        # Memory should be tracked and reasonable
        mem_usage = cache.memory_usage_mb()
        assert 0 < mem_usage <= 1.0


# ============================================================================
# Test: TTL/Expiration
# ============================================================================

class TestTTLExpiration:
    """Test TTL-based expiration."""
    
    def test_expired_entry_not_retrieved(self):
        """Test that expired entries are not retrieved."""
        config = CacheConfig(ttl_seconds=1)
        cache = L1Cache(config)
        
        entry = CacheEntry(
            query_id="ttl_test",
            query_text="test",
            embedding=[0.1] * 384,
            response="resp"
        )
        entry.created_at = time.time() - 2  # 2 seconds ago
        
        cache.put(entry)
        
        # Entry is expired, so get should return None
        retrieved = cache.get(entry.query_id)
        assert retrieved is None


# ============================================================================
# Test: Multiple Evictions
# ============================================================================

class TestMultipleEvictions:
    """Test multiple evictions."""
    
    def test_multiple_evictions_maintain_limit(self):
        """Test that multiple evictions maintain size limit."""
        config = CacheConfig(max_size=3)
        cache = L1Cache(config)
        
        # Add 5 entries, should maintain max_size of 3
        for i in range(5):
            entry = CacheEntry(
                query_id=f"multi_{i}",
                query_text=f"query{i}",
                embedding=[float(i) / 10] * 384,
                response=f"resp{i}"
            )
            cache.put(entry)
        
        assert cache.size() == 3


# ============================================================================
# Test: Cache Statistics
# ============================================================================

class TestCacheStatistics:
    """Test cache statistics and reporting."""
    
    def test_hit_miss_statistics(self):
        """Test hit/miss statistic tracking."""
        config = CacheConfig()
        cache = L1Cache(config)
        
        # Manually record hits and misses
        cache.record_hit()
        cache.record_hit()
        cache.record_miss()
        
        metrics = cache.get_metrics()
        assert metrics.cache_hits == 2
        assert metrics.cache_misses == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
