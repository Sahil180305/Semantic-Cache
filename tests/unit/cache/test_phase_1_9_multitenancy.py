"""
Tests for Multi-Tenancy Foundation (Phase 1.9)

Comprehensive test suite covering:
- Tenant isolation
- Quota management
- Per-tenant metrics
- Usage tracking
- Real-world scenarios
"""

import pytest
from src.cache.multi_tenancy import (
    TenantQuota,
    TenantUsage,
    TenantMetrics,
    TenantManager,
    TenantIsolationLevel,
    TenantAwareCache,
    TenantVerifier,
)


class TestTenantQuota:
    """Tests for TenantQuota."""
    
    def test_create_quota(self):
        """Test creating tenant quota."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=1000,
            max_cache_size_bytes=1000000,
            max_queries_per_hour=10000,
            max_concurrent_requests=100
        )
        
        assert quota.tenant_id == "tenant1"
        assert quota.max_cache_entries == 1000


class TestTenantUsage:
    """Tests for TenantUsage."""
    
    def test_initialize_usage(self):
        """Test initializing tenant usage."""
        usage = TenantUsage(tenant_id="tenant1")
        
        assert usage.tenant_id == "tenant1"
        assert usage.cache_entries_used == 0
        assert usage.queries_this_hour == 0
    
    def test_reset_hourly_counters(self):
        """Test resetting hourly counters."""
        usage = TenantUsage(tenant_id="tenant1")
        usage.queries_this_hour = 50
        
        usage.reset_hourly()
        assert usage.queries_this_hour == 0


class TestTenantMetrics:
    """Tests for TenantMetrics."""
    
    def test_initialize_metrics(self):
        """Test initializing tenant metrics."""
        metrics = TenantMetrics(tenant_id="tenant1")
        
        assert metrics.tenant_id == "tenant1"
        assert metrics.total_cache_hits == 0
    
    def test_update_hit(self):
        """Test recording a cache hit."""
        metrics = TenantMetrics(tenant_id="tenant1")
        metrics.update_hit(10.0)
        
        assert metrics.total_cache_hits == 1
        assert metrics.total_queries == 1
    
    def test_update_miss(self):
        """Test recording a cache miss."""
        metrics = TenantMetrics(tenant_id="tenant1")
        metrics.update_miss(10.0)
        
        assert metrics.total_cache_misses == 1
        assert metrics.total_queries == 1
    
    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        metrics = TenantMetrics(tenant_id="tenant1")
        
        metrics.update_hit(10.0)
        metrics.update_hit(10.0)
        metrics.update_miss(20.0)
        metrics.update_cache_hit_rate()
        
        assert metrics.cache_hit_rate == pytest.approx(2/3)
    
    def test_average_latency(self):
        """Test average latency calculation."""
        metrics = TenantMetrics(tenant_id="tenant1")
        
        metrics.update_hit(10.0)
        metrics.update_hit(20.0)
        assert metrics.average_query_latency_ms == pytest.approx(15.0)


class TestTenantManager:
    """Tests for TenantManager."""
    
    def setup_method(self):
        """Setup for each test."""
        self.manager = TenantManager()
    
    def test_register_tenant(self):
        """Test registering a tenant."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=1000,
            max_cache_size_bytes=1000000,
            max_queries_per_hour=10000,
            max_concurrent_requests=100
        )
        
        success = self.manager.register_tenant("tenant1", quota)
        assert success
        assert "tenant1" in self.manager.tenants
    
    def test_register_duplicate_tenant(self):
        """Test that duplicate registration fails."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=1000,
            max_cache_size_bytes=1000000,
            max_queries_per_hour=10000,
            max_concurrent_requests=100
        )
        
        self.manager.register_tenant("tenant1", quota)
        success = self.manager.register_tenant("tenant1", quota)
        assert not success
    
    def test_unregister_tenant(self):
        """Test unregistering a tenant."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=1000,
            max_cache_size_bytes=1000000,
            max_queries_per_hour=10000,
            max_concurrent_requests=100
        )
        
        self.manager.register_tenant("tenant1", quota)
        success = self.manager.unregister_tenant("tenant1")
        assert success
        assert "tenant1" not in self.manager.tenants
    
    def test_get_quota(self):
        """Test getting tenant quota."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=1000,
            max_cache_size_bytes=1000000,
            max_queries_per_hour=10000,
            max_concurrent_requests=100
        )
        
        self.manager.register_tenant("tenant1", quota)
        retrieved = self.manager.get_quota("tenant1")
        
        assert retrieved is not None
        assert retrieved.max_cache_entries == 1000
    
    def test_check_quota_within_limits(self):
        """Test checking quota when within limits."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        self.manager.register_tenant("tenant1", quota)
        checks = self.manager.check_quota("tenant1")
        
        assert all(checks.values())
    
    def test_is_within_quota(self):
        """Test checking if within quota."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        self.manager.register_tenant("tenant1", quota)
        assert self.manager.is_within_quota("tenant1")
    
    def test_record_cache_access_hit(self):
        """Test recording cache hit."""
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        self.manager.register_tenant("tenant1", quota)
        self.manager.record_cache_access("tenant1", 100, 10.0, is_hit=True)
        
        metrics = self.manager.get_metrics("tenant1")
        assert metrics.total_cache_hits == 1
    
    def test_get_all_metrics(self):
        """Test getting metrics for all tenants."""
        quota1 = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        quota2 = TenantQuota(
            tenant_id="tenant2",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        self.manager.register_tenant("tenant1", quota1)
        self.manager.register_tenant("tenant2", quota2)
        
        all_metrics = self.manager.get_all_metrics()
        assert len(all_metrics) == 2
        assert "tenant1" in all_metrics
        assert "tenant2" in all_metrics


class TestTenantAwareCache:
    """Tests for TenantAwareCache."""
    
    def setup_method(self):
        """Setup for each test."""
        self.manager = TenantManager()
        self.cache = TenantAwareCache(self.manager)
        
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        self.manager.register_tenant("tenant1", quota)
    
    def test_put_value(self):
        """Test storing value in cache."""
        success = self.cache.put("tenant1", "key1", b"value1")
        assert success
    
    def test_get_value(self):
        """Test retrieving value from cache."""
        self.cache.put("tenant1", "key1", b"value1")
        value = self.cache.get("tenant1", "key1")
        
        assert value == b"value1"
    
    def test_get_nonexistent_key(self):
        """Test getting nonexistent key returns None."""
        value = self.cache.get("tenant1", "nonexistent")
        assert value is None
    
    def test_delete_value(self):
        """Test deleting value from cache."""
        self.cache.put("tenant1", "key1", b"value1")
        success = self.cache.delete("tenant1", "key1")
        
        assert success
        assert self.cache.get("tenant1", "key1") is None
    
    def test_clear_tenant(self):
        """Test clearing all cache for a tenant."""
        self.cache.put("tenant1", "key1", b"value1")
        self.cache.put("tenant1", "key2", b"value2")
        
        count = self.cache.clear_tenant("tenant1")
        assert count == 2
        assert self.cache.get_tenant_entry_count("tenant1") == 0
    
    def test_get_tenant_size(self):
        """Test getting total cache size for tenant."""
        self.cache.put("tenant1", "key1", b"value1")  # 6 bytes
        self.cache.put("tenant1", "key2", b"value2")  # 6 bytes
        
        size = self.cache.get_tenant_size("tenant1")
        assert size == 12
    
    def test_get_tenant_entry_count(self):
        """Test getting number of entries for tenant."""
        self.cache.put("tenant1", "key1", b"value1")
        self.cache.put("tenant1", "key2", b"value2")
        
        count = self.cache.get_tenant_entry_count("tenant1")
        assert count == 2
    
    def test_tenant_isolation(self):
        """Test that different tenants have isolated caches."""
        quota2 = TenantQuota(
            tenant_id="tenant2",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        self.manager.register_tenant("tenant2", quota2)
        
        self.cache.put("tenant1", "key1", b"value1")
        self.cache.put("tenant2", "key1", b"other_value")
        
        # Each tenant should see only their own values
        assert self.cache.get("tenant1", "key1") == b"value1"
        assert self.cache.get("tenant2", "key1") == b"other_value"


class TestTenantVerifier:
    """Tests for TenantVerifier."""
    
    def test_verify_strict_isolation(self):
        """Test verifying strict isolation."""
        manager = TenantManager(isolation_level=TenantIsolationLevel.STRICT)
        cache = TenantAwareCache(manager)
        verifier = TenantVerifier(cache)
        
        quota1 = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        quota2 = TenantQuota(
            tenant_id="tenant2",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        manager.register_tenant("tenant1", quota1)
        manager.register_tenant("tenant2", quota2)
        
        cache.put("tenant1", "key1", b"value1")
        cache.put("tenant2", "key2", b"value2")
        
        assert verifier.verify_strict_isolation()
    
    def test_verify_quota_enforcement(self):
        """Test verifying quota enforcement."""
        manager = TenantManager()
        cache = TenantAwareCache(manager)
        verifier = TenantVerifier(cache)
        
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        manager.register_tenant("tenant1", quota)
        cache.put("tenant1", "key1", b"value1")
        
        assert verifier.verify_quota_enforcement(manager)
    
    def test_get_isolation_report(self):
        """Test getting isolation report."""
        manager = TenantManager()
        cache = TenantAwareCache(manager)
        verifier = TenantVerifier(cache)
        
        quota = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        manager.register_tenant("tenant1", quota)
        cache.put("tenant1", "key1", b"value1")
        
        report = verifier.get_isolation_report(manager)
        assert report["isolation_maintained"]
        assert report["quotas_enforced"]
        assert report["total_tenants"] == 1


class TestPhase19RealWorldScenarios:
    """Real-world scenario tests for Phase 1.9."""
    
    def test_multi_tenant_fair_resource_allocation(self):
        """Test fair resource allocation among tenants."""
        manager = TenantManager()
        cache = TenantAwareCache(manager)
        
        # Register multiple tenants with different quotas
        quota_large = TenantQuota(
            tenant_id="premium",
            max_cache_entries=1000,
            max_cache_size_bytes=1000000,
            max_queries_per_hour=100000,
            max_concurrent_requests=100
        )
        
        quota_small = TenantQuota(
            tenant_id="free",
            max_cache_entries=10,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        manager.register_tenant("premium", quota_large)
        manager.register_tenant("free", quota_small)
        
        # Premium tenant can store more
        for i in range(100):
            cache.put("premium", f"key{i}", b"x" * 1000)
        
        assert cache.get_tenant_entry_count("premium") == 100
        
        # Free tenant is limited
        success = True
        for i in range(20):
            if not cache.put("free", f"key{i}", b"x" * 1000):
                success = False
                break
        
        assert cache.get_tenant_entry_count("free") <= 10
    
    def test_tenant_isolation_with_shared_data(self):
        """Test tenant isolation even with similar data."""
        manager = TenantManager()
        cache = TenantAwareCache(manager)
        
        quota1 = TenantQuota(
            tenant_id="tenant1",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        quota2 = TenantQuota(
            tenant_id="tenant2",
            max_cache_entries=100,
            max_cache_size_bytes=10000,
            max_queries_per_hour=1000,
            max_concurrent_requests=10
        )
        
        manager.register_tenant("tenant1", quota1)
        manager.register_tenant("tenant2", quota2)
        
        # Store same key with different values
        cache.put("tenant1", "same_key", b"tenant1_secret")
        cache.put("tenant2", "same_key", b"tenant2_secret")
        
        # Verify isolation
        assert cache.get("tenant1", "same_key") == b"tenant1_secret"
        assert cache.get("tenant2", "same_key") == b"tenant2_secret"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
