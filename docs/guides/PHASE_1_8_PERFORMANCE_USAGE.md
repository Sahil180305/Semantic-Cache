# Phase 1.8: Performance Optimization - Usage Guide

## Overview

Phase 1.8 provides tools for optimizing cache performance through compression, async batch processing, connection pooling, and detailed performance monitoring.

## Quick Start

```python
from src.cache.performance_opt import (
    PerformanceOptimizer,
    ResponseCompressor,
    AsyncBatchProcessor
)

# Initialize performance optimizer
optimizer = PerformanceOptimizer()

# Simple optimization
result = optimizer.optimize_response("Large result data", compression=True)
print(f"Optimized size: {result['size']} bytes")
print(f"Compression ratio: {result['ratio']:.2%}")

# Measure performance
benchmark = optimizer.benchmark_cache_operation(
    operation="get",
    iterations=1000
)
print(f"Avg latency: {benchmark['avg_latency_ms']:.2f}ms")
```

## Response Compression

### Compression Basics

```python
from src.cache.performance_opt import ResponseCompressor

compressor = ResponseCompressor()

# Original data
original = "This is a sample result that could be cached. " * 100
print(f"Original size: {len(original)} bytes")

# GZIP compression (best for text)
compressed = compressor.compress(original, method='gzip')
print(f"GZIP size: {len(compressed)} bytes")
print(f"GZIP ratio: {len(compressed)/len(original):.2%}")

# Decompress
decompressed = compressor.decompress(compressed, method='gzip')
assert decompressed == original
```

### Compression Methods

```python
# GZIP - Best for text, good balance
gzip_data = compressor.compress(data, method='gzip')

# ZLIB - Similar to GZIP, slightly different format
zlib_data = compressor.compress(data, method='zlib')

# DEFLATE - Raw deflate, less overhead than GZIP
deflate_data = compressor.compress(data, method='deflate')

# Recommendations by data type:
# - JSON: GZIP (typically 80-90% reduction)
# - Python objects: ZLIB (70-80% reduction)
# - Binary: DEFLATE (50-70% reduction)
# - Small data (<1KB): No compression (overhead > benefit)
```

### Automatic Compression Selection

```python
compressor = ResponseCompressor()

# Automatically selects best method based on data type and size
compressed, method = compressor.compress_auto(data)
print(f"Selected method: {method}")
print(f"Size: {len(compressed)} bytes")

# Decompress automatically detects method
decompressed = compressor.decompress_auto(compressed)
```

### When to Compress

```python
def should_compress(data: Any, min_size: int = 1024) -> bool:
    """
    Compression overhead (~50 bytes) only worth it for larger payloads
    Recommendation: Only compress if > 1KB
    """
    data_size = len(str(data))
    compression_overhead = 50
    
    return data_size > min_size

# Use in caching
if should_compress(result):
    compressed = compressor.compress(result)
    cache.put(key, compressed, compressed=True)
else:
    cache.put(key, result, compressed=False)
```

## Async Batch Processing

### Basic Batch Processing

```python
from src.cache.performance_opt import AsyncBatchProcessor
import asyncio

async def expensive_operation(item):
    """Simulate expensive operation"""
    await asyncio.sleep(0.1)
    return f"Result of {item}"

async def main():
    processor = AsyncBatchProcessor(batch_size=10)
    
    # Process items in batches
    items = [f"item_{i}" for i in range(100)]
    results = await processor.process_async(
        items,
        expensive_operation,
        timeout=5.0
    )
    
    print(f"Processed {len(results)} items")

asyncio.run(main())
```

### Batch Size Tuning

```python
# Small batches (fast, more overhead)
# Use when: Items process quickly, latency critical
processor = AsyncBatchProcessor(batch_size=5)

# Medium batches (balanced)
# Use when: General purpose caching
processor = AsyncBatchProcessor(batch_size=20)

# Large batches (slower, less overhead)
# Use when: Long-running operations, throughput critical
processor = AsyncBatchProcessor(batch_size=100)
```

### Timeout Handling

```python
async def get_with_timeout():
    processor = AsyncBatchProcessor(batch_size=10, timeout=5.0)
    
    try:
        results = await processor.process_async(
            items,
            operation_fn,
            timeout=5.0  # 5 second timeout per batch
        )
    except asyncio.TimeoutError:
        print("Batch processing timed out")
        # Fallback to synchronous operation
        results = [operation_fn(item) for item in items]
    
    return results
```

### Practical Examples

```python
# Pattern 1: Batch embedding generation
async def batch_generate_embeddings(queries):
    processor = AsyncBatchProcessor(batch_size=20)
    
    async def generate_embedding(query):
        # Call embedding API
        return embedding_service.generate(query)
    
    embeddings = await processor.process_async(
        queries,
        generate_embedding,
        timeout=30.0
    )
    
    return embeddings

# Pattern 2: Batch cache population
async def populate_cache(queries):
    processor = AsyncBatchProcessor(batch_size=50)
    
    async def cache_query(query):
        result = await compute_result(query)
        cache.put(query, result)
        return result
    
    await processor.process_async(queries, cache_query)
```

## Connection Pooling

### Pool Configuration

```python
from src.cache.performance_opt import ConnectionPool

# Create pool for Redis connections
pool = ConnectionPool(
    host='localhost',
    port=6379,
    pool_size=10,  # Number of connections
    timeout=5.0    # Connection timeout
)

# Get connection from pool
with pool.get_connection() as conn:
    result = conn.get("key")

# Pool automatically manages connections
```

### Pool Sizing

```python
# Conservative pooling (few concurrent operations)
small_pool = ConnectionPool(pool_size=5)  # 5% CPU usage

# Balanced pooling (typical production)
medium_pool = ConnectionPool(pool_size=20)  # Good for most workloads

# Aggressive pooling (high concurrency)
large_pool = ConnectionPool(pool_size=50)  # High performance requirement

# Recommendation: Start with 20, adjust based on metrics
```

### Connection Reuse Benefits

```python
# Without pooling (Connection Per Request)
def get_without_pool(key):
    conn = create_connection()  # Overhead: 10-50ms
    result = conn.get(key)
    conn.close()  # Overhead: 5-10ms
    return result
    # Total overhead: 15-60ms per request

# With pooling (Connection Reuse)
def get_with_pool(key, pool):
    conn = pool.get_connection()  # Overhead: 1-2ms (reused)
    result = conn.get(key)
    # Connection returned to pool
    return result
    # Total overhead: 1-2ms per request

# Result: 10x faster for repeated operations!
```

## Performance Monitoring

### Basic Performance Measurement

```python
from src.cache.performance_opt import PerformanceMonitor

monitor = PerformanceMonitor()

# Measure cache hit
start = monitor.start_timer()
result = cache.get("key")
monitor.end_timer(start, operation="cache_get", success=result is not None)

# Measure computation
start = monitor.start_timer()
result = expensive_computation()
monitor.end_timer(start, operation="computation", success=True)

# Get metrics
metrics = monitor.get_metrics()
print(f"Cache hits: {metrics['cache_get']['hits']}")
print(f"Avg computation time: {metrics['computation']['avg_time_ms']:.2f}ms")
```

### Benchmarking Framework

```python
# Benchmark cache with various operations
benchmark = monitor.benchmark_cache_operation(
    operation="get",
    iterations=1000,
    data_size=1024
)

print(f"Operation: {benchmark['operation']}")
print(f"Iterations: {benchmark['iterations']}")
print(f"Total time: {benchmark['total_time_ms']:.2f}ms")
print(f"Avg latency: {benchmark['avg_latency_ms']:.4f}ms")
print(f"Min latency: {benchmark['min_latency_ms']:.4f}ms")
print(f"Max latency: {benchmark['max_latency_ms']:.4f}ms")
print(f"Throughput: {benchmark['throughput_ops_per_sec']:.2f} ops/sec")
```

### Continuous Monitoring

```python
class MonitoredCache:
    def __init__(self, cache):
        self.cache = cache
        self.monitor = PerformanceMonitor()
    
    def get(self, key):
        start = self.monitor.start_timer()
        result = self.cache.get(key)
        success = result is not None
        self.monitor.end_timer(start, "get", success)
        return result
    
    def put(self, key, value):
        start = self.monitor.start_timer()
        self.cache.put(key, value)
        self.monitor.end_timer(start, "put", True)
    
    def get_health(self):
        metrics = self.monitor.get_metrics()
        hit_rate = metrics['get']['hits'] / metrics['get']['total']
        return {
            'hit_rate': hit_rate,
            'avg_latency': metrics['get']['avg_time_ms'],
            'throughput': metrics['get']['ops_per_sec']
        }
```

## Performance Optimizer

### All-in-One Optimization

```python
from src.cache.performance_opt import PerformanceOptimizer

optimizer = PerformanceOptimizer()

# Optimize response (compress if beneficial)
response = {"data": "..." * 1000}  # Large response
optimized = optimizer.optimize_response(
    response,
    compression=True,
    batch_processing=False
)

print(f"Original: {optimized['original_size']} bytes")
print(f"Optimized: {optimized['size']} bytes")
print(f"Ratio: {optimized['ratio']:.2%}")
```

### Integrated Optimization Pipeline

```python
class OptimizedCache:
    def __init__(self):
        self.cache = Cache()
        self.optimizer = PerformanceOptimizer()
        self.pool = ConnectionPool(pool_size=20)
        self.processor = AsyncBatchProcessor(batch_size=10)
    
    async def get_or_compute(self, key, compute_fn):
        # Try cache
        result = self.cache.get(key)
        if result:
            return result
        
        # Compute and optimize
        computed = await compute_fn(key)
        optimized = self.optimizer.optimize_response(computed)
        
        # Store optimized result
        self.cache.put(key, optimized)
        
        return computed
```

## Integration Patterns

### Pattern 1: Smart Compression Cache

```python
class CompressionAwareCacheManager:
    def __init__(self):
        self.cache = {}
        self.compressor = ResponseCompressor()
        self.compression_threshold = 1024  # Compress if > 1KB
    
    def put(self, key, value):
        value_size = len(str(value))
        
        if value_size > self.compression_threshold:
            compressed = self.compressor.compress(value, method='gzip')
            self.cache[key] = {
                'data': compressed,
                'compressed': True,
                'original_size': value_size
            }
        else:
            self.cache[key] = {
                'data': value,
                'compressed': False,
                'original_size': value_size
            }
    
    def get(self, key):
        entry = self.cache.get(key)
        if entry is None:
            return None
        
        if entry['compressed']:
            return self.compressor.decompress(entry['data'], method='gzip')
        return entry['data']
```

### Pattern 2: Batched Cache Warm-up

```python
async def warm_cache_async(queries, cache):
    processor = AsyncBatchProcessor(batch_size=50)
    optimizer = PerformanceOptimizer()
    
    async def compute_and_cache(query):
        result = await compute_result(query)
        optimized = optimizer.optimize_response(result)
        cache.put(query, optimized)
        return query
    
    # Process all queries in batches
    processed = await processor.process_async(
        queries,
        compute_and_cache,
        timeout=60.0
    )
    
    return len(processed)
```

### Pattern 3: Performance-Aware Caching

```python
class PerformanceAwareCacheManager:
    def __init__(self):
        self.cache = {}
        self.monitor = PerformanceMonitor()
        self.optimizer = PerformanceOptimizer()
        self.performance_threshold = 10  # ms
    
    def get(self, key):
        start = self.monitor.start_timer()
        result = self.cache.get(key)
        latency = self.monitor.end_timer(start, "get")
        
        if latency > self.performance_threshold:
            # Cache is slow, optimize access
            self._optimize_cache()
        
        return result
    
    def _optimize_cache(self):
        # Compress old entries
        for key in self.cache:
            value = self.cache[key]
            optimized = self.optimizer.optimize_response(value)
            self.cache[key] = optimized['data']
```

## Benchmarking Examples

```bash
# Benchmark compression
def benchmark_compression():
    compressor = ResponseCompressor()
    data = "x" * 10000  # 10KB of repeated data
    
    import time
    
    # Compress
    start = time.time()
    compressed = compressor.compress(data, method='gzip')
    compress_time = time.time() - start
    
    # Decompress
    start = time.time()
    decompressed = compressor.decompress(compressed, method='gzip')
    decompress_time = time.time() - start
    
    print(f"Original: {len(data)} bytes")
    print(f"Compressed: {len(compressed)} bytes ({len(compressed)/len(data):.1%})")
    print(f"Compression time: {compress_time*1000:.2f}ms")
    print(f"Decompression time: {decompress_time*1000:.2f}ms")
```

## Configuration Guidelines

### For High-Throughput Systems

```python
# Aggressive optimization
optimizer = PerformanceOptimizer()
pool = ConnectionPool(pool_size=50)
processor = AsyncBatchProcessor(batch_size=100)
compressor = ResponseCompressor()  # Always compress

# Large batches, connection pooling for throughput
```

### For Low-Latency Systems

```python
# Conservative optimization
optimizer = PerformanceOptimizer()
pool = ConnectionPool(pool_size=10)
processor = AsyncBatchProcessor(batch_size=5)

# Small batches, lower pooling for latency
compression_threshold = 10240  # Only compress large data
```

### For Balanced Production

```python
# Balanced optimization (recommended)
optimizer = PerformanceOptimizer()
pool = ConnectionPool(pool_size=20)
processor = AsyncBatchProcessor(batch_size=20)
compressor = ResponseCompressor()

# Medium settings, monitor and adjust
```

## Testing & Validation

```bash
# Run performance tests
pytest tests/unit/cache/test_phase_1_8_performance.py -v

# Test compression
pytest tests/unit/cache/test_phase_1_8_performance.py::TestResponseCompressor -v

# Test batch processing
pytest tests/unit/cache/test_phase_1_8_performance.py::TestAsyncBatchProcessor -v

# Test connection pooling
pytest tests/unit/cache/test_phase_1_8_performance.py::TestConnectionPool -v

# Test monitoring
pytest tests/unit/cache/test_phase_1_8_performance.py::TestPerformanceMonitor -v

# Test integrated optimizer
pytest tests/unit/cache/test_phase_1_8_performance.py::TestPerformanceOptimizer -v
```

## API Reference

```python
class ResponseCompressor:
    def compress(self, data: Any, method: str = 'gzip') -> bytes
    def decompress(self, data: bytes, method: str = 'gzip') -> Any
    def compress_auto(self, data: Any) -> Tuple[bytes, str]
    def decompress_auto(self, data: bytes) -> Any

class AsyncBatchProcessor:
    async def process_async(self, items: List, fn, timeout: float) -> List

class ConnectionPool:
    def get_connection(self)
    def __enter__/__exit__() -> Connection

class PerformanceMonitor:
    def start_timer(self) -> float
    def end_timer(self, start: float, operation: str, success: bool) -> float
    def get_metrics(self) -> Dict

class PerformanceOptimizer:
    def optimize_response(self, response: Any, compression: bool = True) -> Dict
    def benchmark_cache_operation(self, operation: str, iterations: int) -> Dict
```

## Next Steps
- Proceed to [Phase 1.9 Multi-Tenancy](./PHASE_1_9_MULTITENANCY_USAGE.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
