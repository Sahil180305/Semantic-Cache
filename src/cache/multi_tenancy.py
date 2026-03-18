"""
Multi-Tenancy Foundation (Phase 1.9)

Implements multi-tenant support for cache system including:
- Tenant isolation in L1 and L2 caches
- Per-tenant quotas and rate limits
- Tenant-aware metrics and monitoring
- Tenant isolation validation
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import time


logger = logging.getLogger(__name__)


@dataclass
class TenantQuota:
    """Resource quota for a tenant."""
    
    tenant_id: str
    max_cache_entries: int
    max_cache_size_bytes: int
    max_queries_per_hour: int
    max_concurrent_requests: int
    
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TenantUsage:
    """Current usage statistics for a tenant."""
    
    tenant_id: str
    cache_entries_used: int = 0
    cache_size_bytes_used: int = 0
    queries_this_hour: int = 0
    concurrent_requests: int = 0
    last_reset_time: float = field(default_factory=time.time)
    
    def reset_hourly(self) -> None:
        """Reset hourly counters."""
        self.queries_this_hour = 0
        self.last_reset_time = time.time()


@dataclass
class TenantMetrics:
    """Metrics for a specific tenant."""
    
    tenant_id: str
    total_cache_hits: int = 0
    total_cache_misses: int = 0
    total_evictions: int = 0
    total_bytes_stored: int = 0
    total_queries: int = 0
    average_query_latency_ms: float = 0.0
    cache_hit_rate: float = 0.0
    
    created_at: datetime = field(default_factory=datetime.now)
    
    def update_hit(self, latency_ms: float) -> None:
        """Record a cache hit.
        
        Args:
            latency_ms: Query latency in milliseconds
        """
        self.total_cache_hits += 1
        self.total_queries += 1
        self._update_latency(latency_ms)
    
    def update_miss(self, latency_ms: float) -> None:
        """Record a cache miss.
        
        Args:
            latency_ms: Query latency in milliseconds
        """
        self.total_cache_misses += 1
        self.total_queries += 1
        self._update_latency(latency_ms)
    
    def _update_latency(self, latency_ms: float) -> None:
        """Update average latency.
        
        Args:
            latency_ms: New latency measurement
        """
        if self.total_queries > 0:
            old_total = self.average_query_latency_ms * (self.total_queries - 1)
            self.average_query_latency_ms = (old_total + latency_ms) / self.total_queries
    
    def update_cache_hit_rate(self) -> None:
        """Recalculate cache hit rate."""
        total = self.total_cache_hits + self.total_cache_misses
        if total > 0:
            self.cache_hit_rate = self.total_cache_hits / total
        else:
            self.cache_hit_rate = 0.0


class TenantIsolationLevel(Enum):
    """Isolation levels for multi-tenancy."""
    
    STRICT = "strict"        # Complete isolation - separate namespaces
    READ_AWARE = "read_aware"  # Shared reads with tenant markers
    PERFORMANCE = "performance"  # Minimal isolation for performance


class TenantManager:
    """Manages tenant registration, quotas, and usage tracking."""
    
    def __init__(self, isolation_level: TenantIsolationLevel = TenantIsolationLevel.STRICT):
        """Initialize tenant manager.
        
        Args:
            isolation_level: Level of tenant isolation
        """
        self.isolation_level = isolation_level
        self.tenants: Dict[str, TenantQuota] = {}
        self.usage: Dict[str, TenantUsage] = {}
        self.metrics: Dict[str, TenantMetrics] = {}
    
    def register_tenant(self, tenant_id: str, quota: TenantQuota) -> bool:
        """Register a new tenant.
        
        Args:
            tenant_id: Unique tenant identifier
            quota: Tenant resource quota
            
        Returns:
            Success of registration
        """
        if tenant_id in self.tenants:
            logger.warning(f"Tenant {tenant_id} already registered")
            return False
        
        self.tenants[tenant_id] = quota
        self.usage[tenant_id] = TenantUsage(tenant_id=tenant_id)
        self.metrics[tenant_id] = TenantMetrics(tenant_id=tenant_id)
        
        logger.info(f"Registered tenant {tenant_id}")
        return True
    
    def unregister_tenant(self, tenant_id: str) -> bool:
        """Unregister a tenant.
        
        Args:
            tenant_id: Tenant to unregister
            
        Returns:
            Success of unregistration
        """
        if tenant_id not in self.tenants:
            return False
        
        del self.tenants[tenant_id]
        del self.usage[tenant_id]
        del self.metrics[tenant_id]
        
        logger.info(f"Unregistered tenant {tenant_id}")
        return True
    
    def get_quota(self, tenant_id: str) -> Optional[TenantQuota]:
        """Get quota for tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Tenant quota or None
        """
        return self.tenants.get(tenant_id)
    
    def get_usage(self, tenant_id: str) -> Optional[TenantUsage]:
        """Get usage for tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Tenant usage or None
        """
        return self.usage.get(tenant_id)
    
    def get_metrics(self, tenant_id: str) -> Optional[TenantMetrics]:
        """Get metrics for tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Tenant metrics or None
        """
        return self.metrics.get(tenant_id)
    
    def check_quota(self, tenant_id: str) -> Dict[str, bool]:
        """Check if tenant is within quota limits.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of quota check results
        """
        quota = self.get_quota(tenant_id)
        usage = self.get_usage(tenant_id)
        
        if not quota or not usage:
            return {}
        
        return {
            "within_entry_limit": usage.cache_entries_used < quota.max_cache_entries,
            "within_size_limit": usage.cache_size_bytes_used < quota.max_cache_size_bytes,
            "within_query_limit": usage.queries_this_hour < quota.max_queries_per_hour,
            "within_concurrency_limit": usage.concurrent_requests < quota.max_concurrent_requests,
        }
    
    def is_within_quota(self, tenant_id: str) -> bool:
        """Check if tenant is completely within quota.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Whether tenant is within all limits
        """
        checks = self.check_quota(tenant_id)
        return all(checks.values())
    
    def record_cache_access(self, tenant_id: str, num_bytes: int, 
                           latency_ms: float, is_hit: bool) -> None:
        """Record cache access for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            num_bytes: Size of cached data
            latency_ms: Access latency
            is_hit: Whether it was a cache hit
        """
        usage = self.get_usage(tenant_id)
        metrics = self.get_metrics(tenant_id)
        
        if not usage or not metrics:
            return
        
        # Update usage
        usage.cache_size_bytes_used += num_bytes
        usage.queries_this_hour += 1
        
        # Update metrics
        if is_hit:
            metrics.update_hit(latency_ms)
        else:
            metrics.update_miss(latency_ms)
        
        metrics.update_cache_hit_rate()
    
    def record_eviction(self, tenant_id: str, num_bytes: int) -> None:
        """Record an eviction for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            num_bytes: Size of evicted data
        """
        usage = self.get_usage(tenant_id)
        metrics = self.get_metrics(tenant_id)
        
        if usage:
            usage.cache_size_bytes_used = max(0, usage.cache_size_bytes_used - num_bytes)
        
        if metrics:
            metrics.total_evictions += 1
    
    def get_all_metrics(self) -> Dict[str, TenantMetrics]:
        """Get metrics for all tenants.
        
        Returns:
            Dictionary of all tenant metrics
        """
        return dict(self.metrics)


class TenantAwareCache:
    """Tenant-aware cache wrapper ensuring isolation."""
    
    def __init__(self, manager: TenantManager):
        """Initialize tenant-aware cache.
        
        Args:
            manager: Tenant manager
        """
        self.manager = manager
        self.cache_storage: Dict[str, Dict[str, bytes]] = {}  # tenant_id -> {key -> value}
    
    def put(self, tenant_id: str, key: str, value: bytes) -> bool:
        """Store value in cache for tenant.
        
        Args:
            tenant_id: Tenant identifier
            key: Cache key
            value: Value to cache
            
        Returns:
            Success of operation
        """
        # Check quota
        if not self.manager.is_within_quota(tenant_id):
            logger.warning(f"Tenant {tenant_id} exceeded quota")
            return False
        
        # Ensure tenant namespace exists
        if tenant_id not in self.cache_storage:
            self.cache_storage[tenant_id] = {}
        
        # Store value
        self.cache_storage[tenant_id][key] = value
        
        # Record usage
        self.manager.record_cache_access(tenant_id, len(value), 0.0, False)
        
        return True
    
    def get(self, tenant_id: str, key: str) -> Optional[bytes]:
        """Retrieve value from cache for tenant.
        
        Args:
            tenant_id: Tenant identifier
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if tenant_id not in self.cache_storage:
            # Record miss
            self.manager.record_cache_access(tenant_id, 0, 0.0, False)
            return None
        
        if key in self.cache_storage[tenant_id]:
            value = self.cache_storage[tenant_id][key]
            # Record hit
            self.manager.record_cache_access(tenant_id, len(value), 0.0, True)
            return value
        
        # Record miss
        self.manager.record_cache_access(tenant_id, 0, 0.0, False)
        return None
    
    def delete(self, tenant_id: str, key: str) -> bool:
        """Delete value from cache for tenant.
        
        Args:
            tenant_id: Tenant identifier
            key: Cache key
            
        Returns:
            Success of deletion
        """
        if tenant_id not in self.cache_storage:
            return False
        
        if key in self.cache_storage[tenant_id]:
            value = self.cache_storage[tenant_id][key]
            del self.cache_storage[tenant_id][key]
            self.manager.record_eviction(tenant_id, len(value))
            return True
        
        return False
    
    def clear_tenant(self, tenant_id: str) -> int:
        """Clear all cache for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Number of entries cleared
        """
        if tenant_id not in self.cache_storage:
            return 0
        
        count = len(self.cache_storage[tenant_id])
        
        # Record evictions
        for value in self.cache_storage[tenant_id].values():
            self.manager.record_eviction(tenant_id, len(value))
        
        self.cache_storage[tenant_id].clear()
        return count
    
    def get_tenant_size(self, tenant_id: str) -> int:
        """Get total cache size for tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Total size in bytes
        """
        if tenant_id not in self.cache_storage:
            return 0
        
        return sum(len(v) for v in self.cache_storage[tenant_id].values())
    
    def get_tenant_entry_count(self, tenant_id: str) -> int:
        """Get number of cache entries for tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Number of entries
        """
        if tenant_id not in self.cache_storage:
            return 0
        
        return len(self.cache_storage[tenant_id])


class TenantVerifier:
    """Verifies tenant isolation enforcement."""
    
    def __init__(self, cache: TenantAwareCache):
        """Initialize verifier.
        
        Args:
            cache: Tenant-aware cache to verify
        """
        self.cache = cache
    
    def verify_strict_isolation(self) -> bool:
        """Verify that tenants cannot access each other's data.
        
        Returns:
            True if isolation is maintained
        """
        cache_storage = self.cache.cache_storage
        
        # Check that tenant namespaces are completely separate
        for tenant_id, namespace in cache_storage.items():
            for key in namespace:
                # Ensure this key is only in this tenant's namespace
                for other_tenant, other_namespace in cache_storage.items():
                    if other_tenant != tenant_id and key in other_namespace:
                        logger.error(f"Isolation violation: key {key} shared between tenants")
                        return False
        
        return True
    
    def verify_quota_enforcement(self, manager: TenantManager) -> bool:
        """Verify that quotas are properly enforced.
        
        Args:
            manager: Tenant manager
            
        Returns:
            True if quotas are enforced
        """
        for tenant_id, namespace in self.cache.cache_storage.items():
            quota = manager.get_quota(tenant_id)
            
            if not quota:
                continue
            
            # Check entry count
            if len(namespace) > quota.max_cache_entries:
                logger.error(f"Quota violation: {tenant_id} has {len(namespace)} entries")
                return False
            
            # Check size
            total_size = sum(len(v) for v in namespace.values())
            if total_size > quota.max_cache_size_bytes:
                logger.error(f"Quota violation: {tenant_id} uses {total_size} bytes")
                return False
        
        return True
    
    def get_isolation_report(self, manager: TenantManager) -> Dict[str, any]:
        """Get comprehensive isolation report.
        
        Args:
            manager: Tenant manager
            
        Returns:
            Report dictionary
        """
        return {
            "isolation_maintained": self.verify_strict_isolation(),
            "quotas_enforced": self.verify_quota_enforcement(manager),
            "total_tenants": len(self.cache.cache_storage),
            "metrics": manager.get_all_metrics(),
        }
