# Phase 1.9: Multi-Tenancy Foundation - Usage Guide

## Overview

Phase 1.9 provides multi-tenancy support with tenant isolation, resource quotas, usage tracking, and verification mechanisms for secure cache sharing across multiple tenants.

## Quick Start

```python
from src.cache.multi_tenancy import (
    TenantAwareCache,
    TenantManager,
    TenantQuota
)

# Initialize multi-tenant cache
cache = TenantAwareCache()

# Create tenant with quota
quota = TenantQuota(
    max_memory=1000,      # 1000 bytes
    max_queries=100,      # 100 queries/day
    max_request_size=100  # 100 bytes per request
)

cache.create_tenant("tenant_1", quota=quota)
cache.create_tenant("tenant_2", quota=quota)

# Use cache (automatically isolated)
cache.put("tenant_1", "key_1", "value_1")
cache.put("tenant_2", "key_1", "value_1")  # Different tenant, independent

value = cache.get("tenant_1", "key_1")  # Returns "value_1"
print(f"Retrieved: {value}")

# Get tenant metrics
metrics = cache.get_tenant_metrics("tenant_1")
print(f"Memory used: {metrics['memory_used']} bytes")
print(f"Queries today: {metrics['queries_today']}")
```

## Tenant Management

### Creating Tenants

```python
from src.cache.multi_tenancy import TenantManager, TenantQuota

manager = TenantManager()

# Create tenant with default quota
manager.create_tenant("tenant_1")

# Create tenant with custom quota
quota = TenantQuota(
    max_memory=5000,
    max_queries=1000,
    max_request_size=500
)
manager.create_tenant("tenant_2", quota=quota)

# List all tenants
tenants = manager.list_tenants()
print(f"Active tenants: {tenants}")
```

### Tenant Quotas

```python
# Conservative quota (small business)
small_quota = TenantQuota(
    max_memory=100,        # 100 bytes
    max_queries=10,        # 10 queries/day
    max_request_size=50
)

# Standard quota (typical SaaS)
standard_quota = TenantQuota(
    max_memory=1000,       # 1 KB
    max_queries=100,       # 100 queries/day
    max_request_size=100
)

# Premium quota (enterprise)
premium_quota = TenantQuota(
    max_memory=10000,      # 10 KB
    max_queries=10000,     # 10K queries/day
    max_request_size=1000
)

# Create tenants with appropriate quotas
manager.create_tenant("small_tenant", quota=small_quota)
manager.create_tenant("standard_tenant", quota=standard_quota)
manager.create_tenant("premium_tenant", quota=premium_quota)
```

### Quota Enforcement

```python
# Quota limits are enforced automatically
try:
    # Tenant 1 has max_memory=100
    manager.cache.put("tenant_1", "key_1", "x" * 200)  # Exceeds quota!
except QuotaExceededError as e:
    print(f"Quota exceeded: {e}")
    # Handle gracefully - cache miss, compute fresh

# Check quota before operation
usage = manager.get_usage("tenant_1")
quota = manager.get_quota("tenant_1")

if usage['memory_used'] + len(new_value) > quota.max_memory:
    print("Would exceed quota - skip caching")
```

## Tenant-Aware Caching

### Basic Usage

```python
from src.cache.multi_tenancy import TenantAwareCache

cache = TenantAwareCache()

# Create tenants
cache.create_tenant("tenant_a")
cache.create_tenant("tenant_b")

# Store data (automatically isolated)
cache.put("tenant_a", "key", "value_a")
cache.put("tenant_b", "key", "value_b")  # Same key, different value

# Retrieve data (tenant-specific)
assert cache.get("tenant_a", "key") == "value_a"
assert cache.get("tenant_b", "key") == "value_b"

# Tenant A cannot see Tenant B's data
assert cache.get("tenant_a", "key") != "value_b"
```

### Automatic Isolation

```python
# Each tenant gets isolated storage
cache.put("tenant_1", "query_1", "result_1")
cache.put("tenant_1", "query_2", "result_2")

cache.put("tenant_2", "query_1", "result_x")
cache.put("tenant_2", "query_2", "result_y")

# Tenant 1 operations only affect Tenant 1
cache.delete("tenant_1", "query_1")
assert cache.get("tenant_1", "query_1") is None

# Tenant 2 unaffected
assert cache.get("tenant_2", "query_1") == "result_x"
```

### Tenant Metrics

```python
# Get per-tenant metrics
metrics = cache.get_tenant_metrics("tenant_1")

print(f"Memory used: {metrics['memory_used']} bytes")
print(f"Memory quota: {metrics['memory_quota']} bytes")
print(f"Items stored: {metrics['item_count']}")
print(f"Hit rate: {metrics['hit_rate']:.2%}")
print(f"Queries today: {metrics['queries_today']}")
```

## Tenant Isolation Verification

### Verifying Data Isolation

```python
from src.cache.multi_tenancy import TenantVerifier

verifier = TenantVerifier(cache)

# Verify tenant isolation
is_isolated = verifier.verify_isolation(
    tenant_1="tenant_1",
    tenant_2="tenant_2"
)

if is_isolated:
    print("✓ Tenants properly isolated")
else:
    print("✗ Isolation breach detected!")

# Detailed verification
isolation_report = verifier.verify_full_isolation()
print(f"Cross-tenant reads: {isolation_report['cross_tenant_access']}")
print(f"Data leakage: {isolation_report['data_leakage']}")
print(f"Quota violations: {isolation_report['quota_violations']}")
```

### Continuous Verification

```python
# Periodic isolation checks
def periodic_isolation_check(cache, interval=300):
    """Check isolation every 5 minutes"""
    import time
    
    verifier = TenantVerifier(cache)
    
    while True:
        time.sleep(interval)
        
        report = verifier.verify_full_isolation()
        
        if not report['is_isolated']:
            print("ALERT: Isolation breach detected!")
            # Log, alert, rollback, etc.
```

## Tenant Metrics

### Usage Tracking

```python
from src.cache.multi_tenancy import TenantMetrics

metrics = TenantMetrics()

# Record operations
metrics.record_cache_access("tenant_1", hit=True)
metrics.record_cache_access("tenant_1", hit=True)
metrics.record_cache_access("tenant_1", hit=False)  # Miss

metrics.record_memory_usage("tenant_1", bytes_used=500)
metrics.record_memory_usage("tenant_1", bytes_used=600)

# Get metrics
stats = metrics.get_stats("tenant_1")
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Avg memory: {stats['avg_memory_bytes']} bytes")
print(f"Total requests: {stats['total_requests']}")
```

### Performance Monitoring per Tenant

```python
# Each tenant has independent performance metrics
def monitor_tenant_performance():
    cache = TenantAwareCache()
    
    # Simulate workload for two tenants
    for i in range(1000):
        # Tenant A workload
        cache.put("tenant_a", f"key_{i}", f"value_{i}")
        if i % 2 == 0:
            cache.get("tenant_a", f"key_{i}")
        
        # Tenant B workload
        cache.put("tenant_b", f"key_{i}", f"value_{i}")
        if i % 3 == 0:
            cache.get("tenant_b", f"key_{i}")
    
    # Get independent metrics
    metrics_a = cache.get_tenant_metrics("tenant_a")
    metrics_b = cache.get_tenant_metrics("tenant_b")
    
    print(f"Tenant A hit rate: {metrics_a['hit_rate']:.2%}")
    print(f"Tenant B hit rate: {metrics_b['hit_rate']:.2%}")
```

## Multi-Tenant Patterns

### Pattern 1: SaaS Cache

```python
class SaasCacheManager:
    def __init__(self):
        self.cache = TenantAwareCache()
        self.manager = TenantManager()
        self.verifier = TenantVerifier(self.cache)
    
    def register_customer(self, customer_id: str, plan: str):
        """Register new customer with appropriate quota"""
        quotas = {
            'free': TenantQuota(100, 10, 50),
            'pro': TenantQuota(1000, 100, 500),
            'enterprise': TenantQuota(10000, 10000, 5000)
        }
        
        self.cache.create_tenant(customer_id, quota=quotas[plan])
    
    def cache_result(self, customer_id: str, key: str, result: Any):
        """Cache result for specific customer"""
        self.cache.put(customer_id, key, result)
    
    def get_result(self, customer_id: str, key: str):
        """Get cached result for customer"""
        return self.cache.get(customer_id, key)
    
    def get_customer_status(self, customer_id: str):
        """Get customer cache usage and health"""
        metrics = self.cache.get_tenant_metrics(customer_id)
        
        return {
            'memory_used': metrics['memory_used'],
            'memory_quota': metrics['memory_quota'],
            'hit_rate': metrics['hit_rate'],
            'items_cached': metrics['item_count']
        }
    
    def daily_quota_reset(self):
        """Reset daily query quotas"""
        for tenant in self.manager.list_tenants():
            self.manager.reset_daily_quota(tenant)
```

### Pattern 2: Multi-Workspace Organization

```python
class MultiWorkspaceCache:
    """Cache for organizations with multiple workspaces"""
    
    def __init__(self):
        self.cache = TenantAwareCache()
    
    def make_tenant_id(self, org_id: str, workspace_id: str) -> str:
        """Create unique tenant ID"""
        return f"{org_id}:{workspace_id}"
    
    def create_workspace(self, org_id: str, workspace_id: str, quota: TenantQuota):
        """Create isolated cache for workspace"""
        tenant_id = self.make_tenant_id(org_id, workspace_id)
        self.cache.create_tenant(tenant_id, quota)
    
    def cache_for_workspace(self, org_id: str, workspace_id: str, key: str, value: Any):
        """Cache data for specific workspace"""
        tenant_id = self.make_tenant_id(org_id, workspace_id)
        self.cache.put(tenant_id, key, value)
    
    def get_workspace_isolation_score(self, org_id: str) -> float:
        """Verify all workspaces properly isolated"""
        workspaces = self.cache.list_tenants()
        org_workspaces = [w for w in workspaces if w.startswith(org_id)]
        
        verifier = TenantVerifier(self.cache)
        
        # Check pairwise isolation
        isolation_count = 0
        total_checks = len(org_workspaces) * (len(org_workspaces) - 1) / 2
        
        for i, w1 in enumerate(org_workspaces):
            for w2 in org_workspaces[i+1:]:
                if verifier.verify_isolation(w1, w2):
                    isolation_count += 1
        
        return isolation_count / total_checks if total_checks > 0 else 1.0
```

### Pattern 3: API Multi-Tenancy

```python
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()
cache = TenantAwareCache()

@app.post("/api/v1/cache/{key}")
async def cache_value(
    key: str,
    value: str,
    x_tenant_id: str = Header(...)
):
    """Cache value for tenant"""
    try:
        cache.put(x_tenant_id, key, value)
        return {"status": "cached"}
    except QuotaExceededError:
        raise HTTPException(status_code=429, detail="Quota exceeded")

@app.get("/api/v1/cache/{key}")
async def get_value(
    key: str,
    x_tenant_id: str = Header(...)
):
    """Get cached value for tenant"""
    result = cache.get(x_tenant_id, key)
    
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    
    return {"value": result}

@app.get("/api/v1/tenant/metrics")
async def get_metrics(x_tenant_id: str = Header(...)):
    """Get tenant metrics"""
    metrics = cache.get_tenant_metrics(x_tenant_id)
    return metrics
```

## Security & Best Practices

### 1. Always Verify Tenant in Request

```python
def get_current_tenant(request) -> str:
    """Extract and verify tenant from request"""
    tenant = request.headers.get("X-Tenant-ID")
    
    if not tenant:
        raise AuthenticationError("Missing tenant ID")
    
    # Verify tenant exists and user has access
    if not is_valid_tenant(tenant):
        raise AuthorizationError("Invalid tenant")
    
    return tenant
```

### 2. Periodic Isolation Checks

```python
import asyncio

async def continuous_isolation_monitoring(cache, interval=300):
    """Monitor isolation continuously"""
    verifier = TenantVerifier(cache)
    
    while True:
        await asyncio.sleep(interval)
        
        report = verifier.verify_full_isolation()
        
        if not report['is_isolated']:
            # Alert security team
            await alert_security_team(report)
```

### 3. Quota Enforcement

```python
def enforce_quota(cache, tenant: str, operation_size: int):
    """Check quota before operation"""
    quota = cache.get_quota(tenant)
    usage = cache.get_usage(tenant)
    
    if usage['memory_used'] + operation_size > quota.max_memory:
        raise QuotaExceededError(
            f"Operation would exceed quota: "
            f"{usage['memory_used'] + operation_size} > {quota.max_memory}"
        )
```

### 4. Audit Logging

```python
def audit_tenant_access(tenant: str, operation: str, key: str, result: str):
    """Log all tenant operations for compliance"""
    audit_log.write({
        'timestamp': datetime.now(),
        'tenant': tenant,
        'operation': operation,
        'key': key,
        'result': result,
        'user': get_current_user()
    })
```

## Testing & Validation

```bash
# Run multi-tenancy tests
pytest tests/unit/cache/test_phase_1_9_multitenancy.py -v

# Test tenant manager
pytest tests/unit/cache/test_phase_1_9_multitenancy.py::TestTenantManager -v

# Test isolation
pytest tests/unit/cache/test_phase_1_9_multitenancy.py::TestTenantAwareCache -v

# Test metrics
pytest tests/unit/cache/test_phase_1_9_multitenancy.py::TestTenantMetrics -v

# Test verification
pytest tests/unit/cache/test_phase_1_9_multitenancy.py::TestTenantVerifier -v
```

## API Reference

```python
class TenantManager:
    def create_tenant(self, tenant_id: str, quota: TenantQuota = None) -> None
    def list_tenants(self) -> List[str]
    def get_quota(self, tenant_id: str) -> TenantQuota
    def reset_daily_quota(self, tenant_id: str) -> None

class TenantAwareCache:
    def create_tenant(self, tenant_id: str, quota: TenantQuota = None) -> None
    def put(self, tenant_id: str, key: str, value: Any) -> None
    def get(self, tenant_id: str, key: str) -> Any
    def delete(self, tenant_id: str, key: str) -> None
    def get_tenant_metrics(self, tenant_id: str) -> Dict

class TenantVerifier:
    def verify_isolation(self, tenant_1: str, tenant_2: str) -> bool
    def verify_full_isolation(self) -> Dict

class TenantMetrics:
    def record_cache_access(self, tenant_id: str, hit: bool) -> None
    def record_memory_usage(self, tenant_id: str, bytes_used: int) -> None
    def get_stats(self, tenant_id: str) -> Dict
```

## Troubleshooting

### Data Leakage

**Symptom:** Tenant A can see Tenant B's data

**Solution:**
1. Run `TenantVerifier.verify_full_isolation()`
2. Check if tenant IDs are properly passed
3. Verify isolation mechanism in cache

### Quota Issues

**Symptom:** Operations failing with "Quota exceeded"

**Solution:**
1. Check current usage: `get_usage(tenant)`
2. Check quota limits: `get_quota(tenant)`
3. Upgrade quota or clear old entries

### Performance Degradation

**Symptom:** Multi-tenant cache slower than single-tenant

**Solution:**
1. Monitor per-tenant metrics
2. Check for hot tenants using excessive quota
3. Adjust quotas or add compute resources

## Next Steps
- Review [Complete Phase 1 Documentation](../PHASE_1_COMPLETE.md)
- Prepare for [Phase 2: FastAPI REST Server](../phase_2/README.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
