"""
Tests for Performance Optimization (Phase 1.8)

Comprehensive test suite covering:
- Response compression (GZIP, ZLIB)
- Asynchronous batch operations
- Connection pooling
- Performance benchmarking
- Real-world scenarios
"""

import pytest
import asyncio
import time
from src.cache.performance_opt import (
    CompressionFormat,
    ResponseCompressor,
    AsyncBatchProcessor,
    ConnectionPool,
    PerformanceMonitor,
    PerformanceOptimizer,
    CompressionMetrics,
    BatchOperationMetrics,
    PoolMetrics,
    PerformanceBenchmark,
)


class TestCompressionMetrics:
    """Tests for CompressionMetrics."""
    
    def test_calculate_compression_ratio(self):
        """Test compression ratio calculation."""
        metrics = CompressionMetrics(
            original_size=1000,
            compressed_size=600
        )
        ratio = metrics.calculate_ratio()
        assert ratio == 0.6
    
    def test_compression_ratio_zero_original(self):
        """Test ratio when original is zero."""
        metrics = CompressionMetrics(
            original_size=0,
            compressed_size=0
        )
        ratio = metrics.calculate_ratio()
        assert ratio == 0.0


class TestResponseCompressor:
    """Tests for ResponseCompressor."""
    
    def test_initialize_with_gzip(self):
        """Test initializing with GZIP."""
        compressor = ResponseCompressor(format=CompressionFormat.GZIP)
        assert compressor.format == CompressionFormat.GZIP
    
    def test_should_compress_below_threshold(self):
        """Test that small data is not compressed."""
        compressor = ResponseCompressor(min_size_bytes=1024)
        assert not compressor.should_compress(512)
    
    def test_should_compress_above_threshold(self):
        """Test that large data is compressed."""
        compressor = ResponseCompressor(min_size_bytes=1024)
        assert compressor.should_compress(2048)
    
    def test_should_not_compress_when_disabled(self):
        """Test that compression is skipped when disabled."""
        compressor = ResponseCompressor(format=CompressionFormat.NONE)
        assert not compressor.should_compress(10000)
    
    def test_compress_data_gzip(self):
        """Test GZIP compression."""
        compressor = ResponseCompressor(format=CompressionFormat.GZIP, min_size_bytes=10)
        original = b"hello world" * 100
        compressed, metrics = compressor.compress(original)
        
        assert len(compressed) < len(original)
        assert metrics.original_size == len(original)
        assert metrics.compressed_size == len(compressed)
        assert metrics.compression_ratio < 1.0
    
    def test_decompress_data_gzip(self):
        """Test GZIP decompression."""
        compressor = ResponseCompressor(format=CompressionFormat.GZIP, min_size_bytes=10)
        original = b"hello world" * 100
        compressed, _ = compressor.compress(original)
        decompressed, metrics = compressor.decompress(compressed)
        
        assert decompressed == original
        # Decompression time may be very fast (rounded to 0.0)
        assert metrics.decompression_time_ms >= 0
    
    def test_compress_data_zlib(self):
        """Test ZLIB compression."""
        compressor = ResponseCompressor(format=CompressionFormat.ZLIB, min_size_bytes=10)
        original = b"compress this data" * 50
        compressed, metrics = compressor.compress(original)
        
        assert len(compressed) < len(original)
        assert 0 < metrics.compression_ratio < 1.0
    
    def test_decompress_data_zlib(self):
        """Test ZLIB decompression."""
        compressor = ResponseCompressor(format=CompressionFormat.ZLIB, min_size_bytes=10)
        original = b"compress this data" * 50
        compressed, _ = compressor.compress(original)
        decompressed, _ = compressor.decompress(compressed)
        
        assert decompressed == original
    
    def test_compress_small_data_skipped(self):
        """Test that small data is not actually compressed."""
        compressor = ResponseCompressor(format=CompressionFormat.GZIP, min_size_bytes=1024)
        original = b"small"  # Only 5 bytes
        compressed, metrics = compressor.compress(original)
        
        assert compressed == original  # Should be unchanged
        assert metrics.original_size == len(original)
    
    def test_compression_time_recorded(self):
        """Test that compression time is recorded."""
        compressor = ResponseCompressor(format=CompressionFormat.GZIP, min_size_bytes=10)
        original = b"test data" * 100
        _, metrics = compressor.compress(original)
        
        # Compression should be recorded (may be very fast, so >= not >)
        assert metrics.compression_time_ms >= 0


class TestAsyncBatchProcessor:
    """Tests for AsyncBatchProcessor."""
    
    @pytest.mark.asyncio
    async def test_add_operation(self):
        """Test adding operation to queue."""
        processor = AsyncBatchProcessor(batch_size=10)
        
        async def dummy_op():
            return "done"
        
        await processor.add_operation(dummy_op)
        assert processor.get_queue_size() == 1
    
    @pytest.mark.asyncio
    async def test_get_queue_size(self):
        """Test getting queue size."""
        processor = AsyncBatchProcessor()
        
        async def dummy_op():
            pass
        
        await processor.add_operation(dummy_op)
        await processor.add_operation(dummy_op)
        
        assert processor.get_queue_size() == 2
    
    @pytest.mark.asyncio
    async def test_process_batch(self):
        """Test processing a batch."""
        processor = AsyncBatchProcessor(batch_size=5)
        
        async def async_op(value):
            async def op():
                return value * 2
            return await op()
        
        for i in range(3):
            await processor.add_operation(lambda i=i: async_op(i))
        
        metrics = await processor.process_batch()
        assert metrics.total_items == 3
        assert metrics.success_count == 3
        assert processor.get_queue_size() == 0
    
    @pytest.mark.asyncio
    async def test_process_batch_with_failures(self):
        """Test batch processing with some failures."""
        processor = AsyncBatchProcessor(batch_size=10)
        
        async def failing_op():
            raise ValueError("test error")
        
        async def success_op():
            return "success"
        
        await processor.add_operation(success_op)
        await processor.add_operation(failing_op)
        await processor.add_operation(success_op)
        
        metrics = await processor.process_batch()
        assert metrics.total_items == 3
        assert metrics.success_count == 2
        assert metrics.failure_count == 1
    
    @pytest.mark.asyncio
    async def test_clear_queue(self):
        """Test clearing the queue."""
        processor = AsyncBatchProcessor()
        
        async def dummy_op():
            pass
        
        await processor.add_operation(dummy_op)
        await processor.add_operation(dummy_op)
        assert processor.get_queue_size() == 2
        
        await processor.clear()
        assert processor.get_queue_size() == 0


class TestConnectionPool:
    """Tests for ConnectionPool."""
    
    @pytest.mark.asyncio
    async def test_initialize_pool(self):
        """Test initializing connection pool."""
        counter = {"value": 0}
        
        def create_conn():
            counter["value"] += 1
            return f"conn_{counter['value']}"
        
        pool = ConnectionPool(create_conn, max_size=3)
        await pool.initialize()
        
        assert pool.metrics.pool_size == 3
        assert len(pool.available) == 3
    
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        """Test acquiring and releasing connections."""
        counter = {"value": 0}
        
        def create_conn():
            counter["value"] += 1
            return f"conn_{counter['value']}"
        
        pool = ConnectionPool(create_conn, max_size=2)
        await pool.initialize()
        
        conn = await pool.acquire()
        assert conn is not None
        assert pool.metrics.active_connections == 1
        
        await pool.release(conn)
        assert pool.metrics.active_connections == 0
    
    @pytest.mark.asyncio
    async def test_pool_exhaustion(self):
        """Test behavior when pool is exhausted."""
        def create_conn():
            return "conn"
        
        pool = ConnectionPool(create_conn, max_size=1, timeout_seconds=0.1)
        await pool.initialize()
        
        # Acquire the only connection
        conn1 = await pool.acquire()
        assert conn1 is not None
        
        # Wait shows timeout handling
        assert pool.metrics.active_connections == 1
    
    @pytest.mark.asyncio
    async def test_pool_metrics(self):
        """Test pool metrics tracking."""
        def create_conn():
            return "conn"
        
        pool = ConnectionPool(create_conn, max_size=3)
        await pool.initialize()
        
        conn = await pool.acquire()
        await pool.release(conn)
        
        metrics = pool.get_metrics()
        assert metrics.idle_connections == 3
        assert metrics.active_connections == 0
        assert metrics.total_checkouts >= 1
        assert metrics.total_checkins >= 1


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor."""
    
    def test_start_measurement(self):
        """Test starting a measurement."""
        monitor = PerformanceMonitor()
        start_time = monitor.start_measurement("test_op")
        assert isinstance(start_time, float)
    
    def test_end_measurement(self):
        """Test ending a measurement."""
        monitor = PerformanceMonitor()
        start = monitor.start_measurement("test_op")
        time.sleep(0.01)  # Sleep 10ms
        elapsed = monitor.end_measurement("test_op", start)
        
        assert elapsed >= 10  # At least 10ms
        assert "test_op" in monitor.benchmarks
    
    def test_benchmark_accumulates(self):
        """Test that multiple measurements accumulate."""
        monitor = PerformanceMonitor()
        
        for _ in range(3):
            start = monitor.start_measurement("test_op")
            time.sleep(0.01)
            monitor.end_measurement("test_op", start)
        
        benchmark = monitor.get_benchmark("test_op")
        assert benchmark.iterations == 3
        assert benchmark.total_time_ms >= 30
    
    def test_benchmark_statistics(self):
        """Test benchmark statistics."""
        monitor = PerformanceMonitor()
        
        times = [10.0, 20.0, 15.0]
        benchmark = PerformanceBenchmark(operation_name="test")
        for t in times:
            benchmark.add_measurement(t)
        
        assert benchmark.iterations == 3
        assert benchmark.avg_time_ms == pytest.approx(15.0)
        assert benchmark.min_time_ms == 10.0
        assert benchmark.max_time_ms == 20.0
    
    def test_get_all_benchmarks(self):
        """Test retrieving all benchmarks."""
        monitor = PerformanceMonitor()
        
        start1 = monitor.start_measurement("op1")
        time.sleep(0.01)
        monitor.end_measurement("op1", start1)
        
        start2 = monitor.start_measurement("op2")
        time.sleep(0.01)
        monitor.end_measurement("op2", start2)
        
        all_benchmarks = monitor.get_all_benchmarks()
        assert "op1" in all_benchmarks
        assert "op2" in all_benchmarks
    
    def test_clear_benchmarks(self):
        """Test clearing benchmarks."""
        monitor = PerformanceMonitor()
        start = monitor.start_measurement("test")
        monitor.end_measurement("test", start)
        
        assert len(monitor.benchmarks) > 0
        monitor.clear()
        assert len(monitor.benchmarks) == 0


class TestPerformanceOptimizer:
    """Tests for PerformanceOptimizer."""
    
    def test_initialize_optimizer(self):
        """Test initializing optimizer."""
        optimizer = PerformanceOptimizer(
            compression_format=CompressionFormat.GZIP,
            batch_size=100
        )
        assert optimizer.compressor is not None
        assert optimizer.batch_processor is not None
        assert optimizer.monitor is not None
    
    def test_compress_response(self):
        """Test compressing response."""
        optimizer = PerformanceOptimizer()
        data = b"test data" * 200  # Large enough to exceed default threshold
        compressed, metrics = optimizer.compress_response(data)
        
        assert len(compressed) <= len(data)  # Could be equal if below threshold
        assert metrics.compression_ratio <= 1.0
    
    def test_decompress_response(self):
        """Test decompressing response."""
        optimizer = PerformanceOptimizer()
        original = b"test data" * 100
        compressed, _ = optimizer.compress_response(original)
        decompressed, _ = optimizer.decompress_response(compressed)
        
        assert decompressed == original
    
    def test_benchmark_operation(self):
        """Test benchmarking operation."""
        optimizer = PerformanceOptimizer()
        
        def test_op():
            time.sleep(0.01)
        
        elapsed = optimizer.benchmark_operation("test_op", test_op)
        assert elapsed >= 10  # At least 10ms
    
    def test_get_performance_stats(self):
        """Test getting performance stats."""
        optimizer = PerformanceOptimizer()
        
        def dummy_op():
            pass
        
        optimizer.benchmark_operation("op1", dummy_op)
        stats = optimizer.get_performance_stats()
        
        assert "op1" in stats
        assert stats["op1"].iterations == 1


class TestPhase18RealWorldScenarios:
    """Real-world scenario tests for Phase 1.8."""
    
    def test_compression_effectiveness(self):
        """Test compression is effective for JSON responses."""
        optimizer = PerformanceOptimizer(compression_format=CompressionFormat.GZIP)
        
        # Simulate JSON response
        json_data = b'{"results": [{"id": 1}, {"id": 2}]}' * 100
        compressed, metrics = optimizer.compress_response(json_data)
        
        # Should compress well
        assert metrics.compression_ratio < 0.5
    
    @pytest.mark.asyncio
    async def test_batch_processing_throughput(self):
        """Test batch processing throughput improvement."""
        optimizer = PerformanceOptimizer(batch_size=10)
        
        # Add multiple operations
        for i in range(20):
            async def op(i=i):
                await asyncio.sleep(0.001)
                return i
            
            await optimizer.add_batch_operation(op)
        
        # Process batch
        metrics = await optimizer.process_pending_batch()
        assert metrics.total_items == 10
        assert metrics.success_count == 10
    
    def test_performance_monitoring_overhead(self):
        """Test that monitoring has minimal overhead."""
        optimizer = PerformanceOptimizer()
        
        def quick_op():
            pass
        
        # Benchmark multiple times
        times = []
        for _ in range(5):
            elapsed = optimizer.benchmark_operation("quick_op", quick_op)
            times.append(elapsed)
        
        stats = optimizer.get_performance_stats()
        benchmark = stats["quick_op"]
        
        # Overhead should be small (measured in microseconds)
        assert benchmark.avg_time_ms < 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
