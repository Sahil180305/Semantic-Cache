# Phase 1.5: L2 Cache & Manager - Usage Guide

## Overview

Phase 1.5 implements a Redis-backed distributed L2 cache and a CacheManager that orchestrates two-tier caching with multiple strategies.

## Quick Start

### L2 Cache

```python
from src.cache.l2_cache import L2Cache
from src.cache.redis_config import RedisConfig

# Initialize L2 cache
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0
)

l2_cache = L2Cache(redis_config=redis_config)

# Store data
l2_cache.put("query_1", result_data, ttl_seconds=3600)

# Retrieve data
result = l2_cache.get("query_1")

# Delete data
l2_cache.delete("query_1")

# Clear cache
l2_cache.clear()
```

### Cache Manager (Two-Tier)

```python
from src.cache.cache_manager import CacheManager, CacheStrategy

# Initialize both L1 and L2
l1_cache = L1Cache(max_entries=10000)
l2_cache = L2Cache(redis_config=redis_config)

# Create manager
manager = CacheManager(
    l1_cache=l1_cache,
    l2_cache=l2_cache,
    strategy=CacheStrategy.WRITE_THROUGH
)

# All operations automatically managed
result = manager.get("query_1")
manager.put("query_1", embedding, result_data)
manager.delete("query_1")
```

## L2 Cache Details

### Basic Operations

```python
# Put with TTL
l2_cache.put("query_1", data, ttl_seconds=7200)  # 2 hours

# Get (returns None if not found or expired)
result = l2_cache.get("query_1")

# Delete
l2_cache.delete("query_1")

# Clear all
l2_cache.clear()

# Check existence
exists = l2_cache.exists("query_1")

# Get remaining TTL
ttl = l2_cache.get_ttl("query_1")
```

### Batch Operations

```python
# Batch put
items = {
    "query_1": data1,
    "query_2": data2,
    "query_3": data3,
}
l2_cache.batch_put(items, ttl_seconds=3600)

# Batch get
keys = ["query_1", "query_2", "query_3"]
results = l2_cache.batch_get(keys)  # Dict[key -> value]

# Batch delete
l2_cache.batch_delete(keys)
```

### TTL Management

```python
# Set TTL on existing key
l2_cache.set_ttl("query_1", 7200)

# Get remaining TTL (seconds)
remaining = l2_cache.get_ttl("query_1")
if remaining == -1:
    print("Key exists but no TTL")
elif remaining == -2:
    print("Key does not exist")
else:
    print(f"Expires in {remaining} seconds")
```

### Serialization

L2 Cache automatically handles serialization:

```python
# Complex objects are automatically serialized
complex_data = {
    "results": [1, 2, 3],
    "metadata": {"source": "api"},
    "timestamp": time.time()
}

l2_cache.put("complex_1", complex_data)

# Retrieved as original type
retrieved = l2_cache.get("complex_1")
assert isinstance(retrieved, dict)
```

### Health Checks

```python
# Check Redis connection
health = l2_cache.health_check()
if health.is_healthy:
    print("Redis is available")
    print(f"Latency: {health.latency_ms}ms")
else:
    print("Redis is unavailable")
    print(f"Error: {health.error}")
```

## Cache Manager Strategies

### 1. WRITE_THROUGH (Recommended)

Both L1 and L2 updated on every write. Highest consistency.

```python
from src.cache.cache_manager import CacheManager, CacheStrategy

manager = CacheManager(
    l1_cache=l1_cache,
    l2_cache=l2_cache,
    strategy=CacheStrategy.WRITE_THROUGH
)

# Both L1 and L2 updated
manager.put("query_1", embedding, result)

# Both checked on read (L1 first)
result = manager.get("query_1")
```

**Use Case:** High consistency required, acceptable latency overhead

### 2. WRITE_BACK (Async)

Writes to L1 immediately, async sync to L2.

```python
manager = CacheManager(
    l1_cache=l1_cache,
    l2_cache=l2_cache,
    strategy=CacheStrategy.WRITE_BACK,
    sync_interval_seconds=5  # Sync to L2 every 5s
)

# Returns immediately (written to L1 only)
manager.put("query_1", embedding, result)

# Asynchronously synced to L2
# Within 5 seconds: L2 updated
```

**Use Case:** High throughput, acceptable eventual consistency

### 3. L1_ONLY

Uses only L1, L2 not accessed.

```python
manager = CacheManager(
    l1_cache=l1_cache,
    l2_cache=l2_cache,
    strategy=CacheStrategy.L1_ONLY
)

# All operations on L1 only
manager.put("query_1", embedding, result)
result = manager.get("query_1")
```

**Use Case:** Single-server deployment, simplified management

### 4. L2_ONLY

Uses only L2, L1 not accessed.

```python
manager = CacheManager(
    l1_cache=l1_cache,
    l2_cache=l2_cache,
    strategy=CacheStrategy.L2_ONLY
)

# All operations on L2 only
manager.put("query_1", embedding, result)
result = manager.get("query_1")
```

**Use Case:** Distributed deployment, shared cache across servers

## Metrics & Monitoring

### Combined Metrics

```python
stats = manager.get_stats()

# Hit/Miss counts
print(f"Total L1 hits: {stats.l1_hits}")
print(f"Total L2 hits: {stats.l2_hits}")
print(f"Total misses: {stats.total_misses}")

# Hit rates
print(f"L1 hit rate: {stats.l1_hit_rate:.2%}")
print(f"L2 hit rate: {stats.l2_hit_rate:.2%}")
print(f"Overall hit rate: {stats.overall_hit_rate:.2%}")

# Memory
print(f"L1 memory: {stats.l1_memory_bytes:,} bytes")
print(f"L2 memory: {stats.l2_memory_bytes:,} bytes")

# Evictions
print(f"L1 evictions: {stats.l1_evictions}")
print(f"L2 evictions: {stats.l2_evictions}")
```

### Strategy-Specific Metrics

```python
# For WRITE_BACK strategy
stats = manager.get_stats()
print(f"Pending sync items: {stats.write_back_pending}")
print(f"Last sync time: {stats.last_write_back_sync}")
```

## Advanced Usage

### Tier Promotion

Promote L2 items to L1:

```python
# Manually promote (not usually needed)
manager.promote_l2_to_l1("query_1")

# L2 copies moved to L1 for faster access
```

### Synchronization

Manually sync L1 to L2:

```python
# Force immediate sync (WRITE_BACK strategy)
deleted_count, failed_count = manager.sync_l1_to_l2()
print(f"Synced: {deleted_count - failed_count}, Failed: {failed_count}")
```

### Cache Invalidation

```python
# Delete from both tiers
manager.delete("query_1")

# Clear all (both tiers)
manager.clear()

# Invalidate by pattern
manager.delete_by_prefix("user_123:")
```

## Performance Tuning

### L1 Size Tuning

```python
# Small L1 (for constrained memory)
l1 = L1Cache(max_entries=1000, max_memory_bytes=10*1024*1024)

# Large L1 (for high cache hit)
l1 = L1Cache(max_entries=100000, max_memory_bytes=500*1024*1024)
```

### L2 Connection Pooling

```python
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0,
    pool_size=50,  # Connection pool size
    timeout_seconds=5
)

l2_cache = L2Cache(redis_config=redis_config)
```

### Batch Size Optimization

```python
# Larger batches for remote L2
results = l2_cache.batch_get(
    keys=["q1", "q2", "q3", ..., "q1000"],  # Bulk operation
    batch_size=100
)
```

## Integration Patterns

### Pattern 1: Read-Through Cache

```python
def get_or_fetch(key: str, embedding, fetch_fn):
    # Try cache
    result = manager.get(key)
    if result is not None:
        return result
    
    # Fetch and cache
    result = fetch_fn()
    manager.put(key, embedding, result)
    return result
```

### Pattern 2: Cache Warming

```python
# Pre-populate cache with hot items
hot_queries = ["common_query_1", "common_query_2", ...]

for query in hot_queries:
    embedding = embedding_service.embed(query)
    result = fetch_result(query)
    manager.put(query, embedding, result, ttl_seconds=86400)
```

### Pattern 3: Cache Invalidation

```python
# Invalidate on data changes
def update_data(item_id: str, new_data):
    # Update source
    save_to_database(item_id, new_data)
    
    # Invalidate related cache entries
    manager.delete_by_prefix(f"item_{item_id}")
```

## Troubleshooting

### Redis Connection Issues

```python
# Check health
health = l2_cache.health_check()
if not health.is_healthy:
    print(f"Error: {health.error}")
    # Fall back to L1 only
    manager.set_strategy(CacheStrategy.L1_ONLY)
```

### High Memory Usage

```python
# Check memory
stats = manager.get_stats()
if stats.l1_memory_bytes > threshold:
    # Reduce L1 size
    # Or increase eviction aggressiveness
```

### Low Hit Rate

```python
# Check hit rates
stats = manager.get_stats()
print(f"L1 hit rate: {stats.l1_hit_rate:.2%}")
print(f"L2 hit rate: {stats.l2_hit_rate:.2%}")

# Solutions:
# 1. Increase L1 size
# 2. Increase TTL
# 3. Pre-warm cache with common queries
```

## Testing

```bash
# Run L2 cache tests
pytest tests/unit/cache/test_l2_cache.py -v

# Run manager tests
pytest tests/unit/cache/test_cache_manager.py -v

# Run integration tests with real Redis
pytest tests/integration/test_l2_cache_integration.py -v
```

## Next Steps
- Proceed to [Phase 1.6 Query Deduplication](./PHASE_1_6_DEDUP_USAGE.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
