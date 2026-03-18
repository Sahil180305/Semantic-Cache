"""
Performance Optimization Module (Phase 1.8)

Implements performance optimizations including:
- Response compression
- Asynchronous batch operations
- Connection pooling
- Performance monitoring
"""

import logging
import gzip
import json
import asyncio
import pickle
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Coroutine
from collections import deque
import time
import zlib


logger = logging.getLogger(__name__)


class CompressionFormat(Enum):
    """Supported compression formats."""
    NONE = "none"
    GZIP = "gzip"
    ZLIB = "zlib"


@dataclass
class CompressionMetrics:
    """Metrics for compression performance."""
    
    original_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0
    compression_time_ms: float = 0.0
    decompression_time_ms: float = 0.0
    
    def calculate_ratio(self) -> float:
        """Calculate compression ratio.
        
        Returns:
            Ratio of compressed to original size
        """
        if self.original_size == 0:
            return 0.0
        return self.compressed_size / self.original_size


class ResponseCompressor:
    """Compresses cache responses for efficient storage."""
    
    def __init__(self, format: CompressionFormat = CompressionFormat.GZIP,
                 min_size_bytes: int = 1024):
        """Initialize compressor.
        
        Args:
            format: Compression format to use
            min_size_bytes: Minimum size to attempt compression
        """
        self.format = format
        self.min_size_bytes = min_size_bytes
        self.metrics = CompressionMetrics()
    
    def should_compress(self, data_size: int) -> bool:
        """Determine if data should be compressed.
        
        Args:
            data_size: Size of data in bytes
            
        Returns:
            Whether to compress
        """
        return self.format != CompressionFormat.NONE and data_size >= self.min_size_bytes
    
    def compress(self, data: bytes) -> tuple[bytes, CompressionMetrics]:
        """Compress data.
        
        Args:
            data: Data to compress
            
        Returns:
            (compressed_data, metrics)
        """
        if not self.should_compress(len(data)):
            return data, CompressionMetrics(original_size=len(data), compressed_size=len(data))
        
        start_time = time.time()
        
        if self.format == CompressionFormat.GZIP:
            compressed = gzip.compress(data)
        elif self.format == CompressionFormat.ZLIB:
            compressed = zlib.compress(data)
        else:
            compressed = data
        
        compression_time = (time.time() - start_time) * 1000
        
        original_size = len(data)
        compressed_size = len(compressed)
        ratio = compressed_size / original_size if original_size > 0 else 0.0
        
        metrics = CompressionMetrics(
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=ratio,
            compression_time_ms=compression_time
        )
        
        return compressed, metrics
    
    def decompress(self, data: bytes) -> tuple[bytes, CompressionMetrics]:
        """Decompress data.
        
        Args:
            data: Compressed data
            
        Returns:
            (decompressed_data, metrics)
        """
        if self.format == CompressionFormat.NONE:
            return data, CompressionMetrics()
        
        start_time = time.time()
        
        try:
            if self.format == CompressionFormat.GZIP:
                decompressed = gzip.decompress(data)
            elif self.format == CompressionFormat.ZLIB:
                decompressed = zlib.decompress(data)
            else:
                decompressed = data
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            return data, CompressionMetrics()
        
        decompression_time = (time.time() - start_time) * 1000
        
        metrics = CompressionMetrics(
            original_size=len(decompressed),
            compressed_size=len(data),
            decompression_time_ms=decompression_time
        )
        
        return decompressed, metrics


@dataclass
class BatchOperationMetrics:
    """Metrics for batch operations."""
    
    batch_size: int = 0
    total_items: int = 0
    success_count: int = 0
    failure_count: int = 0
    execution_time_ms: float = 0.0
    
    def success_rate(self) -> float:
        """Calculate success rate.
        
        Returns:
            Ratio of successful to total items
        """
        if self.total_items == 0:
            return 0.0
        return self.success_count / self.total_items


class AsyncBatchProcessor:
    """Processes cache operations asynchronously in batches."""
    
    def __init__(self, batch_size: int = 100, batch_timeout_seconds: float = 1.0):
        """Initialize batch processor.
        
        Args:
            batch_size: Maximum items per batch
            batch_timeout_seconds: Timeout for batch processing
        """
        self.batch_size = batch_size
        self.batch_timeout_seconds = batch_timeout_seconds
        self.pending_operations: deque = deque()
        self.metrics = BatchOperationMetrics()
        self._lock = asyncio.Lock()
    
    async def add_operation(self, operation: Callable[[], Coroutine]) -> None:
        """Add operation to batch queue.
        
        Args:
            operation: Async operation to execute
        """
        async with self._lock:
            self.pending_operations.append(operation)
    
    async def process_batch(self) -> BatchOperationMetrics:
        """Process pending batch operations.
        
        Returns:
            Metrics for batch execution
        """
        if not self.pending_operations:
            return BatchOperationMetrics()
        
        start_time = time.time()
        batch = []
        
        # Gather operations
        async with self._lock:
            while self.pending_operations and len(batch) < self.batch_size:
                batch.append(self.pending_operations.popleft())
        
        if not batch:
            return BatchOperationMetrics()
        
        # Execute batch
        results = await asyncio.gather(*[op() for op in batch], return_exceptions=True)
        
        execution_time = (time.time() - start_time) * 1000
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        
        self.metrics = BatchOperationMetrics(
            batch_size=self.batch_size,
            total_items=len(batch),
            success_count=success_count,
            failure_count=len(batch) - success_count,
            execution_time_ms=execution_time
        )
        
        return self.metrics
    
    def get_queue_size(self) -> int:
        """Get current queue size.
        
        Returns:
            Number of pending operations
        """
        return len(self.pending_operations)
    
    async def clear(self) -> None:
        """Clear pending operations."""
        async with self._lock:
            self.pending_operations.clear()


@dataclass
class PoolMetrics:
    """Metrics for connection pooling."""
    
    pool_size: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_checkouts: int = 0
    total_checkins: int = 0
    failed_checkouts: int = 0
    pool_exhaustion_count: int = 0
    
    def utilization_rate(self) -> float:
        """Calculate pool utilization.
        
        Returns:
            Ratio of active to total connections
        """
        if self.pool_size == 0:
            return 0.0
        return self.active_connections / self.pool_size


class ConnectionPool:
    """Manages connection pooling for efficient resource usage."""
    
    def __init__(self, connection_factory: Callable, max_size: int = 10, 
                 timeout_seconds: float = 30.0):
        """Initialize connection pool.
        
        Args:
            connection_factory: Callable that creates connections
            max_size: Maximum pool size
            timeout_seconds: Timeout for acquiring connection
        """
        self.connection_factory = connection_factory
        self.max_size = max_size
        self.timeout_seconds = timeout_seconds
        
        self.available: deque = deque()
        self.active: set = set()
        self.metrics = PoolMetrics(pool_size=max_size)
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize pool with connections.
        
        Should be called before use.
        """
        async with self._lock:
            for _ in range(self.max_size):
                try:
                    conn = self.connection_factory()
                    self.available.append(conn)
                except Exception as e:
                    logger.error(f"Failed to initialize connection: {e}")
    
    async def acquire(self) -> Optional[Any]:
        """Acquire a connection from pool.
        
        Returns:
            Connection or None if timeout
        """
        try:
            async with asyncio.timeout(self.timeout_seconds):
                while not self.available:
                    await asyncio.sleep(0.01)
                
                async with self._lock:
                    if self.available:
                        conn = self.available.popleft()
                        self.active.add(id(conn))
                        self.metrics.total_checkouts += 1
                        self.metrics.active_connections = len(self.active)
                        return conn
        except asyncio.TimeoutError:
            logger.warning("Connection pool acquisition timeout")
            self.metrics.failed_checkouts += 1
            self.metrics.pool_exhaustion_count += 1
        
        return None
    
    async def release(self, connection: Any) -> None:
        """Release connection back to pool.
        
        Args:
            connection: Connection to release
        """
        async with self._lock:
            conn_id = id(connection)
            if conn_id in self.active:
                self.active.remove(conn_id)
                self.available.append(connection)
                self.metrics.total_checkins += 1
                self.metrics.active_connections = len(self.active)
    
    def get_metrics(self) -> PoolMetrics:
        """Get pool metrics.
        
        Returns:
            Current metrics
        """
        self.metrics.idle_connections = len(self.available)
        return self.metrics
    
    async def close_all(self) -> None:
        """Close all connections in pool."""
        async with self._lock:
            while self.available:
                conn = self.available.popleft()
                if hasattr(conn, 'close'):
                    try:
                        conn.close()
                    except Exception as e:
                        logger.error(f"Error closing connection: {e}")


@dataclass
class PerformanceBenchmark:
    """Performance benchmark results."""
    
    operation_name: str
    iterations: int = 0
    total_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    throughput_ops_per_sec: float = 0.0
    
    def add_measurement(self, time_ms: float) -> None:
        """Add a measurement.
        
        Args:
            time_ms: Time in milliseconds
        """
        self.iterations += 1
        self.total_time_ms += time_ms
        self.min_time_ms = min(self.min_time_ms, time_ms)
        self.max_time_ms = max(self.max_time_ms, time_ms)
        self.avg_time_ms = self.total_time_ms / self.iterations
        self.throughput_ops_per_sec = 1000.0 / self.avg_time_ms if self.avg_time_ms > 0 else 0.0


class PerformanceMonitor:
    """Monitors and benchmarks cache performance."""
    
    def __init__(self):
        """Initialize performance monitor."""
        self.benchmarks: Dict[str, PerformanceBenchmark] = {}
    
    def start_measurement(self, operation_name: str) -> float:
        """Start timing a measurement.
        
        Args:
            operation_name: Name of operation
            
        Returns:
            Start timestamp
        """
        return time.time()
    
    def end_measurement(self, operation_name: str, start_time: float) -> float:
        """End timing a measurement.
        
        Args:
            operation_name: Name of operation
            start_time: Start timestamp
            
        Returns:
            Elapsed time in milliseconds
        """
        elapsed_ms = (time.time() - start_time) * 1000
        
        if operation_name not in self.benchmarks:
            self.benchmarks[operation_name] = PerformanceBenchmark(
                operation_name=operation_name
            )
        
        self.benchmarks[operation_name].add_measurement(elapsed_ms)
        return elapsed_ms
    
    def get_benchmark(self, operation_name: str) -> Optional[PerformanceBenchmark]:
        """Get benchmark for operation.
        
        Args:
            operation_name: Name of operation
            
        Returns:
            Benchmark or None
        """
        return self.benchmarks.get(operation_name)
    
    def get_all_benchmarks(self) -> Dict[str, PerformanceBenchmark]:
        """Get all benchmarks.
        
        Returns:
            Dictionary of all benchmarks
        """
        return dict(self.benchmarks)
    
    def clear(self) -> None:
        """Clear all benchmarks."""
        self.benchmarks.clear()


class PerformanceOptimizer:
    """Combines all performance optimization features."""
    
    def __init__(self, compression_format: CompressionFormat = CompressionFormat.GZIP,
                 batch_size: int = 100):
        """Initialize optimizer.
        
        Args:
            compression_format: Format for compression
            batch_size: Batch operation size
        """
        self.compressor = ResponseCompressor(format=compression_format)
        self.batch_processor = AsyncBatchProcessor(batch_size=batch_size)
        self.monitor = PerformanceMonitor()
        self.pool: Optional[ConnectionPool] = None
    
    def compress_response(self, data: bytes) -> tuple[bytes, CompressionMetrics]:
        """Compress a response.
        
        Args:
            data: Response data
            
        Returns:
            (compressed_data, metrics)
        """
        return self.compressor.compress(data)
    
    def decompress_response(self, data: bytes) -> tuple[bytes, CompressionMetrics]:
        """Decompress a response.
        
        Args:
            data: Compressed data
            
        Returns:
            (decompressed_data, metrics)
        """
        return self.compressor.decompress(data)
    
    def get_compression_stats(self) -> CompressionMetrics:
        """Get compression statistics.
        
        Returns:
            Overall compression metrics
        """
        return self.compressor.metrics
    
    async def add_batch_operation(self, operation: Callable[[], Coroutine]) -> None:
        """Add operation to batch queue.
        
        Args:
            operation: Async operation
        """
        await self.batch_processor.add_operation(operation)
    
    async def process_pending_batch(self) -> BatchOperationMetrics:
        """Process pending batch operations.
        
        Returns:
            Batch metrics
        """
        return await self.batch_processor.process_batch()
    
    def benchmark_operation(self, operation_name: str, operation: Callable) -> float:
        """Benchmark a synchronous operation.
        
        Args:
            operation_name: Name of operation
            operation: Callable operation
            
        Returns:
            Execution time in milliseconds
        """
        start = self.monitor.start_measurement(operation_name)
        operation()
        elapsed = self.monitor.end_measurement(operation_name, start)
        return elapsed
    
    def get_performance_stats(self) -> Dict[str, PerformanceBenchmark]:
        """Get all performance statistics.
        
        Returns:
            Dictionary of benchmarks
        """
        return self.monitor.get_all_benchmarks()
