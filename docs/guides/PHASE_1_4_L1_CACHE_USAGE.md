# Phase 1.4: L1 Cache - Usage Guide

## Overview

Phase 1.4 implements an in-memory L1 cache with HNSW-backed similarity search, configurable eviction policies, and comprehensive metrics tracking.

## Quick Start

```python
from src.cache.l1_cache import L1Cache, EvictionPolicy
from src.core.config import CacheConfig

# Initialize L1 cache
config = CacheConfig(
    l1=L1CacheConfig(
        max_entries=10000,
        max_memory_bytes=100*1024*1024,  # 100MB
        eviction_policy=EvictionPolicy.LRU
    )
)

cache = L1Cache(config=config)

# Store data
cache.put("query_1", embedding, result_data)

# Retrieve data
result = cache.get("query_1")

# Delete data
cache.delete("query_1")

# Clear cache
cache.clear()
```

## Eviction Policies

### 1. LRU (Least Recently Used) - Default

Evicts least recently accessed entries when capacity exceeded.

```python
from src.cache.l1_cache import L1Cache, EvictionPolicy

cache = L1Cache(eviction_policy=EvictionPolicy.LRU)
```

**Best for:** General-purpose caching, mixed workloads

### 2. LFU (Least Frequently Used)

Evicts least frequently accessed entries.

```python
cache = L1Cache(eviction_policy=EvictionPolicy.LFU)
```

**Best for:** Analytics, predictable access patterns

### 3. TTL (Time To Live)

Entries expire after configurable duration.

```python
cache = L1Cache(eviction_policy=EvictionPolicy.TTL, ttl_seconds=3600)

# Set per-entry TTL
cache.put("query_1", embedding, result, ttl_seconds=1800)
```

**Best for:** Temporary data, session caching

### 4. Random

Randomly evicts entries. Fastest eviction.

```python
cache = L1Cache(eviction_policy=EvictionPolicy.RANDOM)
```

**Best for:** High-throughput with less concern for hit rate

### 5. FIFO (First In First Out)

Evicts oldest entries regardless of access.

```python
cache = L1Cache(eviction_policy=EvictionPolicy.FIFO)
```

**Best for:** Time-series data, event streams

## Capacity Management

### Entry Limits

```python
from src.core.config import CacheConfig, L1CacheConfig

config = CacheConfig(
    l1=L1CacheConfig(max_entries=100000)
)

cache = L1Cache(config=config)

# Monitor entries
stats = cache.get_stats()
print(f"Entries: {stats.entries}")
print(f"Entry limit: {stats.max_entries}")
```

### Memory Limits

```python
config = CacheConfig(
    l1=L1CacheConfig(max_memory_bytes=100*1024*1024)  # 100MB
)

cache = L1Cache(config=config)

# Monitor memory
stats = cache.get_stats()
print(f"Memory used: {stats.memory_bytes} bytes")
print(f"Memory limit: {stats.max_memory_bytes} bytes")
print(f"Memory util: {stats.memory_utilization}%")
```

## TTL Management

### Entry-Level TTL

```python
# Set TTL when storing
cache.put("query_1", embedding, result, ttl_seconds=3600)  # 1 hour

# Get with TTL
ttl_remaining = cache.get_ttl("query_1")

# Extend TTL
cache.set_ttl("query_1", ttl_seconds=7200)
```

### Get TTL Information

```python
# Get remaining TTL
remaining = cache.get_ttl("query_1")
if remaining > 0:
    print(f"Expires in {remaining} seconds")
```

## Metrics & Monitoring

### Basic Metrics

```python
stats = cache.get_stats()

print(f"Cache Hits: {stats.hits}")
print(f"Cache Misses: {stats.misses}")
print(f"Hit Rate: {stats.hit_rate:.2%}")
print(f"Total Evictions: {stats.total_evictions}")
```

### Detailed Metrics

```python
# By eviction type
print(f"LRU Evictions: {stats.evictions_lru}")
print(f"LFU Evictions: {stats.evictions_lfu}")
print(f"TTL Evictions: {stats.evictions_ttl}")
print(f"Memory Evictions: {stats.evictions_memory}")

# Memory tracking
print(f"Memory used: {stats.memory_bytes:,} bytes")
print(f"Average entry size: {stats.avg_entry_size} bytes")
```

### Real-Time Monitoring

```python
import time
from collections import deque

# Track metrics over time
metrics_history = deque(maxlen=60)  # Last 60 seconds

while True:
    stats = cache.get_stats()
    metrics_history.append({
        "timestamp": time.time(),
        "hit_rate": stats.hit_rate,
        "memory_util": stats.memory_utilization,
        "entries": stats.entries
    })
    
    # Average hit rate over last 60 seconds
    avg_hit_rate = sum(m["hit_rate"] for m in metrics_history) / len(metrics_history)
    print(f"Avg hit rate: {avg_hit_rate:.2%}")
    
    time.sleep(1)
```

## Advanced Usage

### Batch Operations

```python
# Batch put
items = [
    ("query_1", embedding1, result1),
    ("query_2", embedding2, result2),
    ("query_3", embedding3, result3),
]
cache.put_batch(items)

# Batch get
keys = ["query_1", "query_2", "query_3"]
results = cache.get_batch(keys)

# Batch delete
cache.delete_batch(keys)
```

### Conditional Operations

```python
# Get or set
def get_or_compute(key: str, embedding, compute_fn):
    result = cache.get(key)
    if result is None:
        result = compute_fn()
        cache.put(key, embedding, result)
    return result

result = get_or_compute("query_1", embedding, lambda: expensive_operation())
```

### Prefix Operations

```python
# Get all entries matching prefix
entries = cache.get_by_prefix("user_123:")
for key, value in entries:
    print(f"{key}: {value}")

# Delete all entries matching prefix
cache.delete_by_prefix("temp_:")
```

## Performance Optimization

### Size Optimization

```python
# Compress large results
import zlib

def cache_with_compression(key, embedding, result):
    compressed = zlib.compress(result)
    cache.put(key, embedding, compressed)

def get_with_decompression(key):
    compressed = cache.get(key)
    return zlib.decompress(compressed) if compressed else None
```

### HNSW Tuning

```python
# Adjust HNSW parameters for speed vs accuracy
config = CacheConfig(
    l1=L1CacheConfig(
        hnsw_max_m=8,        # Lower = faster, less memory
        hnsw_ef_construction=100,
        hnsw_ef=50
    )
)
```

## Troubleshooting

### Low Hit Rate

```python
# Check eviction frequency
stats = cache.get_stats()
if stats.total_evictions > stats.hits:
    print("Cache too small for workload")
    # Solution: Increase max_entries or max_memory_bytes
```

### Memory Pressure

```python
# Monitor memory usage
stats = cache.get_stats()
if stats.memory_utilization > 0.9:
    print("Cache near capacity")
    # Solution: Reduce TTL or increase max_memory_bytes
```

### Slow Lookups

```python
# HNSW search might be slow if too many entries
stats = cache.get_stats()
if stats.entries > 50000:
    # Solution: Decrease max_entries or tune HNSW parameters
```

## Integration with L2 Cache

```python
# L1 acts as front-end to L2
from src.cache.l2_cache import L2Cache

l1_cache = L1Cache(max_entries=10000)
l2_cache = L2Cache(redis_config=config.redis)

# Try L1 first
result = l1_cache.get(key)
if result is None:
    # Fall back to L2
    result = l2_cache.get(key)
    if result is not None:
        # Promote to L1
        l1_cache.put(key, embedding, result)
```

## Testing

```bash
# Run L1 cache tests
pytest tests/unit/cache/test_phase_1_4_cache.py -v

# Test eviction policies
pytest tests/unit/cache/test_phase_1_4_cache.py::TestEvictionPolicies -v

# Test metrics
pytest tests/unit/cache/test_phase_1_4_cache.py::TestMetrics -v
```

## API Reference

```python
class L1Cache:
    def put(self, key: str, embedding: ndarray, value: Any, ttl_seconds: int = None) -> None
    def get(self, key: str) -> Optional[Any]
    def delete(self, key: str) -> bool
    def clear(self) -> None
    
    def get_stats(self) -> CacheStats
    def get_ttl(self, key: str) -> int
    def set_ttl(self, key: str, ttl_seconds: int) -> None
    
    def put_batch(self, items: List[Tuple[str, ndarray, Any]]) -> None
    def get_batch(self, keys: List[str]) -> Dict[str, Any]
    def delete_batch(self, keys: List[str]) -> None
```

## Next Steps
- Proceed to [Phase 1.5 L2 Cache & Manager](./PHASE_1_5_L2_CACHE_USAGE.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
