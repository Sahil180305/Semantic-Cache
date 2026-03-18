# Phase 1 Quick Reference Guide

## Fast Lookup - Common Tasks

### 1. Basic Setup
```python
from src.cache.l1_cache import L1Cache
from src.cache.manager import CacheManager

# Create L1 cache (in-memory)
l1 = L1Cache(max_capacity=1000)

# Create manager (add L2 with Redis)
manager = CacheManager(l1_cache=l1, l2_cache_config={
    'backend': 'redis',
    'host': 'localhost',
    'port': 6379
})
```

### 2. Cache Operations
```python
# Get or compute
result = manager.get(key)
if result is None:
    result = expensive_computation()
    manager.put(key, result)

# Direct operations
manager.put("key", "value")
value = manager.get("key")
manager.delete("key")
```

### 3. Embeddings
```python
from src.embedding.service import EmbeddingService

service = EmbeddingService(provider='openai')
embedding = service.generate("What is AI?")

# Batch generation
embeddings = service.batch_generate([
    "query 1",
    "query 2"
])
```

### 4. Similarity Search
```python
from src.similarity.search import SimilaritySearch

search = SimilaritySearch(metric='cosine')
distance = search.compute("query1", "query2")

# Find similar
candidates = ["q1", "q2", "q3"]
similar = search.find_similar(
    reference="query",
    candidates=candidates,
    top_k=3,
    threshold=0.8
)
```

### 5. Query Deduplication
```python
from src.cache.query_dedup import QueryDeduplicationEngine, DeduplicationStrategy

engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.NORMALIZED
)

canonical, is_duplicate = engine.register_query("What is ML?")
```

### 6. Advanced Policies
```python
from src.cache.advanced_policies import AdvancedCachingPolicyManager

manager = AdvancedCachingPolicyManager(
    max_memory=10000,
    learning_enabled=True,
    cost_aware=True
)

manager.put("key", "value", cost=100)
```

### 7. Performance Optimization
```python
from src.cache.performance_opt import (
    ResponseCompressor,
    PerformanceMonitor,
    ConnectionPool
)

# Compression
compressor = ResponseCompressor()
compressed = compressor.compress(data, method='gzip')

# Monitoring
monitor = PerformanceMonitor()
start = monitor.start_timer()
# operation
latency = monitor.end_timer(start, "operation")

# Pooling
pool = ConnectionPool(pool_size=20)
with pool.get_connection() as conn:
    result = conn.get("key")
```

### 8. Multi-Tenancy
```python
from src.cache.multi_tenancy import (
    TenantAwareCache,
    TenantQuota
)

cache = TenantAwareCache()
quota = TenantQuota(max_memory=1000, max_queries=100)
cache.create_tenant("tenant_1", quota=quota)

cache.put("tenant_1", "key", "value")
value = cache.get("tenant_1", "key")
```

---

## Decision Trees

### Choosing Cache Strategy

```
Single-tenant application?
├─ YES → Use WRITE_THROUGH (keeps data fresh)
└─ NO → Use WRITE_BACK (better performance for multiple tenants)

Need persistence?
├─ YES → Use L2 Cache (Redis backend)
└─ NO → Use L1_ONLY strategy

High frequency access?
├─ YES → Use LFU eviction policy
└─ NO → Use LRU eviction policy
```

### Choosing Similarity Metric

```
Text queries (NLP)?
├─ YES → Use COSINE (standard choice)
└─ NO → Continue

Exact matching important?
├─ YES → Use HAMMING
└─ NO → Continue

Magnitude matters?
├─ YES → Use EUCLIDEAN
└─ NO → Use COSINE
```

### Choosing Batch Size

```
Items process quickly (< 1ms)?
├─ YES → batch_size = 5-10
└─ NO → Continue

Items process medium (1-100ms)?
├─ YES → batch_size = 20-50
└─ NO → batch_size = 100+
```

---

## Common Patterns

### Pattern 1: Smart Cache Wrapper
```python
class SmartCache:
    def __init__(self):
        self.manager = CacheManager()
        
    def get_or_compute(self, key, fn, cost=None):
        result = self.manager.get(key)
        if result: return result
        
        result = fn()
        self.manager.put(key, result, cost=cost)
        return result
```

### Pattern 2: Tenant-Aware GET
```python
def get_from_tenant_cache(tenant_id: str, key: str):
    try:
        return tenant_cache.get(tenant_id, key)
    except TenantExceedQuotaError:
        # Log and return None
        logger.warn(f"Tenant {tenant_id} exceeded quota")
        return None
```

### Pattern 3: Batch Processing
```python
async def process_queries(queries, compute_fn):
    processor = AsyncBatchProcessor(batch_size=20)
    results = await processor.process_async(
        queries,
        compute_fn,
        timeout=30.0
    )
    return results
```

### Pattern 4: Performance Monitoring
```python
def monitored_cache_get(key):
    monitor = PerformanceMonitor()
    start = monitor.start_timer()
    
    result = cache.get(key)
    
    monitor.end_timer(start, "cache_get", result is not None)
    return result
```

---

## Configuration Cheat Sheet

### For Different Scenarios

**Scenario: LLM Inference Caching**
```python
manager = CacheManager(
    l1_cache_config={'max_capacity': 100, 'policy': 'LFU'},
    l2_cache_config={'backend': 'redis'},
    compression=True,
    cost_aware=True  # Prioritize expensive LLM calls
)
```

**Scenario: SaaS Multi-Tenant**
```python
cache = TenantAwareCache()
for customer in customers:
    quota = TenantQuota(
        max_memory=customer.plan.memory,
        max_queries=customer.plan.daily_limit
    )
    cache.create_tenant(customer.id, quota)
```

**Scenario: High-Performance**
```python
manager = CacheManager(
    l1_cache_config={'max_capacity': 10000, 'policy': 'LRU'},
    pool_size=50,
    compression=True,
    batch_size=100
)
```

---

## Metrics Quick Check

### Cache Health Indicators

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| Hit Rate | > 80% | 50-80% | < 50% |
| Avg Latency | < 10ms | 10-50ms | > 50ms |
| Memory Usage | < 80% | 80-95% | > 95% |
| Error Rate | < 1% | 1-5% | > 5% |

### How to Check
```python
metrics = manager.get_metrics()
print(f"Hit rate: {metrics['hit_rate']:.2%}")
print(f"Avg latency: {metrics['avg_latency_ms']:.2f}ms")
print(f"Memory: {metrics['memory_used']}/{metrics['memory_max']}")
```

---

## Environment Variables

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=""

# Embedding Service
OPENAI_API_KEY=sk-...
HUGGINGFACE_API_KEY=hf_...

# Cache Configuration
L1_MAX_CAPACITY=1000
L2_MAX_CAPACITY=10000
COMPRESSION_ENABLED=true

# Performance
CONNECTION_POOL_SIZE=20
BATCH_SIZE=20
```

---

## Testing Commands

```bash
# All tests
pytest tests/unit/ -q --tb=short

# Specific phase
pytest tests/unit/cache/test_phase_1_4_l1_cache.py -v

# With coverage
pytest tests/unit/ --cov=src --cov-report=html

# Integration tests (requires Docker)
pytest tests/integration/ -v

# Watch mode
pytest-watch tests/unit/

# Show output
pytest tests/unit/ -v -s
```

---

## API Summary - All Methods

### L1Cache
```python
l1.get(key)                    # Get value
l1.put(key, value)             # Cache value
l1.delete(key)                 # Remove value
l1.clear()                     # Clear all
l1.get_metrics()               # Get stats
l1.get_eviction_policy()       # Current policy
```

### L2Cache (Redis)
```python
l2.get(key)                    # Get value
l2.put(key, value)             # Cache value
l2.delete(key)                 # Remove value
l2.batch_get(keys)             # Get multiple
l2.batch_put(items)            # Put multiple
```

### CacheManager
```python
manager.get(key)               # Get (L1 then L2)
manager.put(key, value)        # Put (both levels)
manager.delete(key)            # Delete from both
manager.get_metrics()          # Hit rate, latency
manager.optimize()             # Optimize configuration
```

### EmbeddingService
```python
service.generate(text)         # Generate single
service.batch_generate(texts)  # Generate batch
service.get_cached(text)       # Get if cached
service.cache_valid(text)      # Check if in cache
```

### SimilaritySearch
```python
search.compute(a, b)           # Distance between
search.find_similar(ref, candidates, top_k=3)
search.set_threshold(0.8)      # Set threshold
search.get_metric()            # Current metric
```

### QueryDeduplicationEngine
```python
engine.register_query(q)       # Register, get canonical
engine.get_stats()             # Statistics
engine.clear()                 # Clear all
engine.get_canonical(q)        # Get canonical form
```

### TenantAwareCache
```python
cache.create_tenant(id, quota)
cache.put(tenant, key, value)
cache.get(tenant, key)
cache.get_tenant_metrics(tenant)
cache.list_tenants()
cache.delete_tenant(id)
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `QuotaExceededError` | Tenant quota full | Increase quota or clear old data |
| `ConnectionRefusedError` | Redis not running | `docker-compose up redis` |
| `EmbeddingError` | API key invalid | Check `OPENAI_API_KEY` |
| `IsolationViolationError` | Data leakage | Run `TenantVerifier.verify_full_isolation()` |
| `TimeoutError` | Operation too slow | Increase timeout or lower batch size |

---

## Performance Tuning

### Improve Hit Rate
```python
# 1. Lower similarity threshold
search.set_threshold(0.75)  # Was 0.85

# 2. Enable deduplication
engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.SEMANTIC
)

# 3. Increase L1 capacity
l1 = L1Cache(max_capacity=5000)  # Was 1000
```

### Reduce Latency
```python
# 1. Enable connection pooling
pool = ConnectionPool(pool_size=50)

# 2. Enable compression
manager = CacheManager(..., compression=True)

# 3. Use batch operations
results = l2.batch_get(keys)
```

### Reduce Memory Usage
```python
# 1. Decrease L1 capacity
l1 = L1Cache(max_capacity=500)

# 2. Enable compression
compressor.compress(data, method='gzip')

# 3. Use cost-aware eviction
policy = CostAwareEvictionPolicy()
```

---

## Key Takeaways

✅ **Do:**
- Use L1 for hot, recent data
- Use L2 for persistent storage
- Monitor hit rate regularly
- Compress large responses
- Verify tenant isolation in multi-tenant systems

❌ **Don't:**
- Store uncompressed large objects in cache
- Ignore quota limits in multi-tenant
- Use synchronous operations in async code
- Mix tenant data accidentally
- Skip testing with real workloads

---

**Last Updated:** Phase 1 Complete
**Next:** See [INDEX.md](./INDEX.md) for full documentation
