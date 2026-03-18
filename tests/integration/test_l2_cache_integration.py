"""
Phase 1.5 - L2 Cache Integration Tests with Docker Redis

Real integration tests using actual Redis instance from Docker.
These tests require Docker services to be running.
"""

import pytest
import time
from typing import Optional

from src.cache import (
    CacheConfig, CacheEntry, L1Cache,
    RedisConfig, L2Cache,
    CacheManager, CacheManagerConfig, CacheStrategy,
)


# Allow connection to real Redis for integration tests
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0  # Use separate DB for testing


@pytest.fixture
def redis_config() -> RedisConfig:
    """Create Redis config for integration tests."""
    return RedisConfig(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        key_prefix="test_integration:",
        default_ttl_seconds=3600,
    )


@pytest.fixture
def redis_available() -> bool:
    """Check if Redis is available."""
    try:
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception:
        return False


# ============================================================================
# Integration Tests: L2 Cache with Real Redis
# ============================================================================

class TestL2CacheIntegration:
    """Integration tests for L2 cache with real Redis."""
    
    def test_redis_connection(self, redis_config):
        """Test connection to Redis."""
        cache = L2Cache(redis_config)
        
        result = cache.connect()
        
        assert result is True
        assert cache._connected is True
        
        # Cleanup
        cache.disconnect()
    
    def test_l2_cache_put_get_integration(self, redis_config, redis_available):
        """Test L2 cache put/get with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            # Create and store entry
            entry = CacheEntry(
                query_id="integration_q1",
                query_text="What is machine learning?",
                embedding=[0.1] * 384,
                response="Machine learning is a subset of AI..."
            )
            
            result = cache.put(entry)
            assert result is True
            
            # Retrieve entry
            retrieved = cache.get("integration_q1")
            
            assert retrieved is not None
            assert retrieved.query_id == "integration_q1"
            assert retrieved.query_text == "What is machine learning?"
            assert len(retrieved.embedding) == 384
            
        finally:
            cache.clear()
            cache.disconnect()
    
    def test_l2_cache_delete_integration(self, redis_config, redis_available):
        """Test L2 cache delete with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            # Create and store entry
            entry = CacheEntry(
                query_id="integration_q2",
                query_text="test",
                embedding=[0.2] * 384,
                response="response"
            )
            cache.put(entry)
            
            # Verify it exists
            assert cache.exists("integration_q2") is True
            
            # Delete it
            result = cache.delete("integration_q2")
            assert result is True
            
            # Verify it's gone
            retrieved = cache.get("integration_q2")
            assert retrieved is None
            
        finally:
            cache.clear()
            cache.disconnect()
    
    def test_l2_cache_size_integration(self, redis_config, redis_available):
        """Test L2 cache size calculation with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            # Clear first
            cache.clear()
            
            # Add entries
            for i in range(3):
                entry = CacheEntry(
                    query_id=f"size_q{i}",
                    query_text=f"query {i}",
                    embedding=[0.1 * i] * 384,
                    response=f"response {i}"
                )
                cache.put(entry)
            
            # Check size
            size = cache.size()
            assert size == 3
            
        finally:
            cache.clear()
            cache.disconnect()
    
    def test_l2_cache_ttl_integration(self, redis_config, redis_available):
        """Test L2 cache TTL with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            # Create entry
            entry = CacheEntry(
                query_id="ttl_q1",
                query_text="test",
                embedding=[0.1] * 384,
                response="response"
            )
            cache.put(entry)
            
            # Set short TTL
            result = cache.set_ttl("ttl_q1", 2)
            assert result is True
            
            # Get TTL
            ttl = cache.get_ttl("ttl_q1")
            assert ttl is not None
            assert ttl > 0 and ttl <= 2
            
            # Wait for expiration
            time.sleep(2.5)
            
            # Entry should be expired
            retrieved = cache.get("ttl_q1")
            assert retrieved is None
            
        finally:
            cache.clear()
            cache.disconnect()
    
    def test_l2_cache_batch_operations(self, redis_config, redis_available):
        """Test batch operations with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            # Create batch of entries
            entries = [
                CacheEntry(
                    query_id=f"batch_q{i}",
                    query_text=f"query {i}",
                    embedding=[0.1 * i] * 384,
                    response=f"response {i}"
                )
                for i in range(5)
            ]
            
            # Batch put
            successful, failed = cache.batch_put(entries)
            assert successful == 5
            assert failed == 0
            
            # Batch get
            query_ids = [f"batch_q{i}" for i in range(5)]
            results = cache.batch_get(query_ids)
            
            assert len(results) == 5
            assert all(r is not None for r in results)
            
        finally:
            cache.clear()
            cache.disconnect()
    
    def test_l2_cache_health_check(self, redis_config, redis_available):
        """Test health check with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            result = cache.health_check()
            assert result is True
            
        finally:
            cache.disconnect()
    
    def test_l2_cache_stats(self, redis_config, redis_available):
        """Test getting Redis stats."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        cache = L2Cache(redis_config)
        assert cache.connect() is True
        
        try:
            stats = cache.get_stats()
            
            assert "used_memory" in stats
            assert "connected_clients" in stats
            assert stats["cached_entries"] >= 0
            assert stats["hit_rate"] >= 0.0
            
        finally:
            cache.disconnect()


# ============================================================================
# Integration Tests: Cache Manager with Real Redis
# ============================================================================

class TestCacheManagerIntegration:
    """Integration tests for cache manager with real Redis."""
    
    def test_manager_write_through_integration(self, redis_available):
        """Test write-through strategy with real Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="manager_test:"
        )
        
        config = CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            l2_config=l2_config
        )
        
        manager = CacheManager(config)
        assert manager.initialize() is True
        
        try:
            # Create entry
            entry = CacheEntry(
                query_id="manager_q1",
                query_text="test query",
                embedding=[0.1] * 384,
                response="test response"
            )
            
            # Put to manager
            result = manager.put(entry)
            assert result is True
            
            # Get from manager
            retrieved = manager.get("manager_q1")
            assert retrieved is not None
            retrieved_entry, source = retrieved
            assert retrieved_entry.query_id == "manager_q1"
            
        finally:
            manager.clear()
            manager.shutdown()
    
    def test_manager_delete_integration(self, redis_available):
        """Test delete across both tiers."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="manager_del:"
        )
        
        config = CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            l2_config=l2_config
        )
        
        manager = CacheManager(config)
        assert manager.initialize() is True
        
        try:
            # Create and store entry
            entry = CacheEntry(
                query_id="manager_q2",
                query_text="test",
                embedding=[0.1] * 384,
                response="resp"
            )
            manager.put(entry)
            
            # Delete
            result = manager.delete("manager_q2")
            assert result is True
            
            # Verify gone from L1
            assert manager.l1_cache.get("manager_q2") is None
            
        finally:
            manager.clear()
            manager.shutdown()
    
    def test_manager_metrics_integration(self, redis_available):
        """Test metrics tracking."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="manager_metrics:"
        )
        
        config = CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            l2_config=l2_config
        )
        
        manager = CacheManager(config)
        assert manager.initialize() is True
        
        try:
            # Add entry
            entry = CacheEntry(
                query_id="metric_q1",
                query_text="test",
                embedding=[0.1] * 384,
                response="resp"
            )
            manager.put(entry)
            
            # Get the entry (hit)
            manager.get("metric_q1")
            
            # Try nonexistent (miss)
            manager.get("nonexistent")
            
            # Check metrics
            stats = manager.get_combined_stats()
            assert stats["tiered"]["l1_hits"] >= 1
            assert stats["tiered"]["misses"] >= 1
            
        finally:
            manager.clear()
            manager.shutdown()
    
    def test_manager_sync_l1_to_l2_integration(self, redis_available):
        """Test syncing L1 to L2."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="manager_sync:"
        )
        
        config = CacheManagerConfig(
            strategy=CacheStrategy.L1_ONLY,  # Start with L1 only
            l2_config=l2_config
        )
        
        manager = CacheManager(config)
        assert manager.initialize() is True
        
        try:
            # Add entries to L1
            for i in range(3):
                entry = CacheEntry(
                    query_id=f"sync_q{i}",
                    query_text=f"query {i}",
                    embedding=[0.1 * i] * 384,
                    response=f"resp {i}"
                )
                manager.put(entry)
            
            # Verify in L1
            assert manager.l1_cache.size() == 3
            
            # Sync L1 to L2
            if manager.l2_cache:
                successful, failed = manager.sync_l1_to_l2()
                assert successful == 3
                assert failed == 0
            
        finally:
            manager.clear()
            manager.shutdown()


# ============================================================================
# Integration Tests: Real-world Scenarios
# ============================================================================

class TestRealWorldScenarios:
    """Test real-world usage scenarios."""
    
    def test_cache_miss_recovery(self, redis_available):
        """Test recovery from cache miss by fetching from L2."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="scenario_miss:"
        )
        
        config = CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            enable_l1_to_l2_promotion=True,
            l2_config=l2_config
        )
        
        manager = CacheManager(config)
        assert manager.initialize() is True
        
        try:
            # Store in both caches
            entry = CacheEntry(
                query_id="scenario_q1",
                query_text="important query",
                embedding=[0.1] * 384,
                response="important response"
            )
            manager.put(entry)
            
            # Remove from L1 to simulate miss
            manager.l1_cache.delete("scenario_q1")
            assert manager.l1_cache.get("scenario_q1") is None
            
            # Should still be in L2
            if manager.l2_cache:
                l2_entry = manager.l2_cache.get("scenario_q1")
                assert l2_entry is not None
                assert l2_entry.query_id == "scenario_q1"
            
        finally:
            manager.clear()
            manager.shutdown()
    
    def test_high_frequency_queries(self, redis_available):
        """Test handling high frequency queries."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="scenario_freq:"
        )
        
        config = CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            l2_config=l2_config
        )
        
        manager = CacheManager(config)
        assert manager.initialize() is True
        
        try:
            # Store entry
            entry = CacheEntry(
                query_id="freq_q1",
                query_text="popular query",
                embedding=[0.1] * 384,
                response="response"
            )
            manager.put(entry)
            
            # Simulate high-frequency access
            for _ in range(10):
                retrieved = manager.get("freq_q1")
                assert retrieved is not None
            
            # Check hit count
            assert manager.metrics.l1_hits >= 10
            
        finally:
            manager.clear()
            manager.shutdown()
    
    def test_multiple_cache_instances(self, redis_available):
        """Test multiple cache instances accessing same Redis."""
        if not redis_available:
            pytest.skip("Redis not available")
        
        l2_config = RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            key_prefix="scenario_multi:"
        )
        
        # Create two managers
        manager1 = CacheManager(CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            l2_config=l2_config
        ))
        manager2 = CacheManager(CacheManagerConfig(
            strategy=CacheStrategy.WRITE_THROUGH,
            l2_config=l2_config
        ))
        
        assert manager1.initialize() is True
        assert manager2.initialize() is True
        
        try:
            # Manager 1 stores entry
            entry = CacheEntry(
                query_id="multi_q1",
                query_text="shared query",
                embedding=[0.1] * 384,
                response="shared response"
            )
            manager1.put(entry)
            
            # Manager 2 should be able to get from shared L2
            if manager2.l2_cache:
                retrieved = manager2.l2_cache.get("multi_q1")
                assert retrieved is not None
                assert retrieved.query_id == "multi_q1"
            
        finally:
            manager1.clear()
            manager2.clear()
            manager1.shutdown()
            manager2.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
