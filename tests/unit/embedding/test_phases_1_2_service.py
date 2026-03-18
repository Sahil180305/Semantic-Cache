"""
Phase 1.2: Embedding Service Tests

Comprehensive tests for:
- Embedding provider abstraction
- Concrete provider implementations (SentenceTransformer, OpenAI, Cohere)
- Embedding service with caching, batching, and retries
- Metrics and cost tracking
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import time

from src.embedding.base import (
    EmbeddingProvider,
    EmbeddingProviderType,
    EmbeddingRecord,
    BatchEmbeddingRequest,
    ProviderConfig,
    EmbeddingProviderFactory,
)
from src.embedding.providers import (
    SentenceTransformerProvider,
    OpenAIProvider,
    CohereProvider,
)
from src.embedding.service import (
    EmbeddingService,
    EmbeddingCache,
    RetryConfig,
    EmbeddingMetrics,
)
from src.core.exceptions import EmbeddingError


# ============================================================================
# Test: Embedding Record Validation
# ============================================================================

class TestEmbeddingRecord:
    """Test EmbeddingRecord dataclass."""
    
    def test_valid_embedding_record(self):
        """Test creating a valid embedding record."""
        record = EmbeddingRecord(
            text="Hello world",
            embedding=[0.1, 0.2, 0.3],
            dimension=3,
            model="test-model",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=2,
            generation_time_ms=10.5,
            timestamp=datetime.utcnow(),
        )
        
        assert record.text == "Hello world"
        assert len(record.embedding) == 3
        assert record.dimension == 3
        assert record.tokens_used == 2
    
    def test_embedding_dimension_mismatch(self):
        """Test that dimension mismatch raises error."""
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            EmbeddingRecord(
                text="Hello world",
                embedding=[0.1, 0.2],  # 2 elements
                dimension=3,  # But dimension is 3
                model="test-model",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=2,
                generation_time_ms=10.5,
                timestamp=datetime.utcnow(),
            )
    
    def test_embedding_text_hash(self):
        """Test text hash generation."""
        record = EmbeddingRecord(
            text="Hello world",
            embedding=[0.1, 0.2],
            dimension=2,
            model="test-model",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=2,
            generation_time_ms=10.5,
            timestamp=datetime.utcnow(),
        )
        
        # Same text should generate same hash
        hash1 = record.text_hash
        record2 = EmbeddingRecord(
            text="Hello world",
            embedding=[0.3, 0.4],
            dimension=2,
            model="test-model",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=2,
            generation_time_ms=10.5,
            timestamp=datetime.utcnow(),
        )
        hash2 = record2.text_hash
        
        assert hash1 == hash2
    
    def test_embedding_with_invalid_values(self):
        """Test that invalid embedding values are rejected."""
        with pytest.raises(ValueError, match="All embedding values must be numeric"):
            EmbeddingRecord(
                text="Hello world",
                embedding=[0.1, "invalid", 0.3],
                dimension=3,
                model="test-model",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=2,
                generation_time_ms=10.5,
                timestamp=datetime.utcnow(),
            )


# ============================================================================
# Test: Batch Embedding Request
# ============================================================================

class TestBatchEmbeddingRequest:
    """Test BatchEmbeddingRequest."""
    
    def test_valid_batch_request(self):
        """Test creating valid batch request."""
        request = BatchEmbeddingRequest(
            texts=["Hello", "World", "Test"],
            model="test-model",
            normalize=True,
        )
        
        assert request.batch_size == 3
        assert request.normalize is True
    
    def test_empty_batch_request(self):
        """Test that empty batch raises error."""
        with pytest.raises(ValueError, match="Batch must contain at least one text"):
            BatchEmbeddingRequest(
                texts=[],
                model="test-model",
            )
    
    def test_non_string_texts(self):
        """Test that non-string texts raise error."""
        with pytest.raises(ValueError, match="All texts must be strings"):
            BatchEmbeddingRequest(
                texts=["Hello", 123, "World"],
                model="test-model",
            )


# ============================================================================
# Test: Embedding Cache
# ============================================================================

class TestEmbeddingCache:
    """Test EmbeddingCache."""
    
    def test_cache_get_miss(self):
        """Test cache miss."""
        cache = EmbeddingCache(max_size=10)
        result = cache.get("Hello world")
        assert result is None
    
    def test_cache_set_and_get(self):
        """Test cache set and retrieve."""
        cache = EmbeddingCache(max_size=10)
        
        record = EmbeddingRecord(
            text="Hello world",
            embedding=[0.1, 0.2],
            dimension=2,
            model="test",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=2,
            generation_time_ms=5.0,
            timestamp=datetime.utcnow(),
        )
        
        cache.set("Hello world", record)
        cached = cache.get("Hello world")
        
        assert cached is not None
        assert cached.embedding == record.embedding
    
    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration."""
        cache = EmbeddingCache(max_size=10, ttl_seconds=1)
        
        record = EmbeddingRecord(
            text="Hello",
            embedding=[0.1],
            dimension=1,
            model="test",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=1,
            generation_time_ms=5.0,
            timestamp=datetime.utcnow(),
        )
        
        cache.set("Hello", record)
        assert cache.get("Hello") is not None
        
        # Wait for TTL to expire
        time.sleep(1.1)
        assert cache.get("Hello") is None
    
    def test_cache_max_size_eviction(self):
        """Test cache eviction when max size reached."""
        cache = EmbeddingCache(max_size=2)
        
        for i in range(3):
            record = EmbeddingRecord(
                text=f"Text {i}",
                embedding=[float(i)],
                dimension=1,
                model="test",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=1,
                generation_time_ms=5.0,
                timestamp=datetime.utcnow(),
            )
            cache.set(f"Text {i}", record)
        
        # First entry should be evicted
        assert cache.get("Text 0") is None
        # Last two should be present
        assert cache.get("Text 1") is not None
        assert cache.get("Text 2") is not None
    
    def test_cache_stats(self):
        """Test cache statistics."""
        cache = EmbeddingCache(max_size=10)
        
        record = EmbeddingRecord(
            text="Hello",
            embedding=[0.1],
            dimension=1,
            model="test",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=1,
            generation_time_ms=5.0,
            timestamp=datetime.utcnow(),
        )
        
        cache.set("Hello", record)
        stats = cache.get_stats()
        
        assert stats["cached_entries"] == 1
        assert stats["max_size"] == 10
        assert stats["usage_percent"] == 10.0


# ============================================================================
# Test: Retry Configuration
# ============================================================================

class TestRetryConfig:
    """Test RetryConfig."""
    
    def test_retry_delay_calculation(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(
            initial_delay_ms=100.0,
            max_delay_ms=10000.0,
            backoff_factor=2.0,
        )
        
        delay_0 = config.get_delay_ms(0)
        delay_1 = config.get_delay_ms(1)
        delay_2 = config.get_delay_ms(2)
        
        assert delay_0 == 100.0
        assert delay_1 == 200.0
        assert delay_2 == 400.0
    
    def test_retry_max_delay(self):
        """Test that delay is capped at max_delay_ms."""
        config = RetryConfig(
            initial_delay_ms=100.0,
            max_delay_ms=500.0,
            backoff_factor=2.0,
        )
        
        delay = config.get_delay_ms(10)  # Would be 100 * 2^10 = 102,400
        assert delay == 500.0  # Capped


# ============================================================================
# Test: Embedding Metrics
# ============================================================================

class TestEmbeddingMetrics:
    """Test EmbeddingMetrics."""
    
    def test_metrics_initialization(self):
        """Test metrics are initialized correctly."""
        metrics = EmbeddingMetrics()
        
        assert metrics.total_requests == 0
        assert metrics.total_tokens == 0
        assert metrics.total_cost == 0.0
    
    def test_metrics_record_request(self):
        """Test recording metrics."""
        metrics = EmbeddingMetrics()
        
        metrics.record_request(tokens=100, cost=0.001, time_ms=50.0, is_cache_hit=False)
        metrics.record_request(tokens=50, cost=0.0, time_ms=5.0, is_cache_hit=True)
        
        stats = metrics.get_stats()
        
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 150
        assert stats["total_cost"] == pytest.approx(0.001)
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["hit_rate"] == pytest.approx(0.5)
    
    def test_metrics_error_tracking(self):
        """Test error tracking in metrics."""
        metrics = EmbeddingMetrics()
        
        metrics.record_request(tokens=0, cost=0.0, time_ms=0.0, is_cache_hit=False, error="API_ERROR")
        metrics.record_request(tokens=0, cost=0.0, time_ms=0.0, is_cache_hit=False, error="API_ERROR")
        metrics.record_request(tokens=0, cost=0.0, time_ms=0.0, is_cache_hit=False, error="TIMEOUT")
        
        stats = metrics.get_stats()
        
        assert stats["errors"]["API_ERROR"] == 2
        assert stats["errors"]["TIMEOUT"] == 1


# ============================================================================
# Test: Provider Factory
# ============================================================================

class TestEmbeddingProviderFactory:
    """Test EmbeddingProviderFactory."""
    
    def test_factory_create_sentence_transformer(self):
        """Test creating SentenceTransformer provider."""
        provider = EmbeddingProviderFactory.create(
            EmbeddingProviderType.SENTENCE_TRANSFORMER,
            "all-MiniLM-L6-v2"
        )
        
        assert isinstance(provider, SentenceTransformerProvider)
        assert provider.model_name == "all-MiniLM-L6-v2"
    
    def test_factory_create_openai(self):
        """Test creating OpenAI provider."""
        provider = EmbeddingProviderFactory.create(
            EmbeddingProviderType.OPENAI,
            "text-embedding-3-small"
        )
        
        assert isinstance(provider, OpenAIProvider)
        assert provider.model_name == "text-embedding-3-small"
    
    def test_factory_create_cohere(self):
        """Test creating Cohere provider."""
        provider = EmbeddingProviderFactory.create(
            EmbeddingProviderType.COHERE,
            "embed-english-v3.0"
        )
        
        assert isinstance(provider, CohereProvider)
        assert provider.model_name == "embed-english-v3.0"
    
    def test_factory_unknown_provider(self):
        """Test that unknown provider raises error."""
        with pytest.raises(ValueError, match="is not a valid EmbeddingProviderType"):
            EmbeddingProviderFactory.create(
                EmbeddingProviderType("unknown"),
                "model"
            )
    
    def test_factory_get_registered_providers(self):
        """Test getting registered providers."""
        providers = EmbeddingProviderFactory.get_registered_providers()
        
        assert EmbeddingProviderType.SENTENCE_TRANSFORMER in providers
        assert EmbeddingProviderType.OPENAI in providers
        assert EmbeddingProviderType.COHERE in providers


# ============================================================================
# Test: Sentence Transformer Provider
# ============================================================================

class TestSentenceTransformerProvider:
    """Test SentenceTransformerProvider."""
    
    @pytest.mark.asyncio
    async def test_provider_initialization(self):
        """Test initializing SentenceTransformer provider."""
        provider = SentenceTransformerProvider(model_name="all-MiniLM-L6-v2")
        
        # We can't actually initialize without the library, but we can test the structure
        assert provider.model_name == "all-MiniLM-L6-v2"
        assert provider._is_initialized is False
    
    def test_normalize_embedding(self):
        """Test embedding normalization."""
        provider = SentenceTransformerProvider()
        
        # Test vector normalization (L2 norm)
        embedding = [3.0, 4.0]
        normalized = provider.normalize_embedding(embedding)
        
        # L2 norm of [3.0, 4.0] is sqrt(9 + 16) = 5
        assert normalized == pytest.approx([0.6, 0.8])
    
    def test_normalize_zero_vector(self):
        """Test normalizing zero vector."""
        provider = SentenceTransformerProvider()
        
        embedding = [0.0, 0.0]
        normalized = provider.normalize_embedding(embedding)
        
        # Zero vector should remain zero
        assert normalized == [0.0, 0.0]


# ============================================================================
# Test: Embedding Service (Mocked Provider)
# ============================================================================

class TestEmbeddingService:
    """Test EmbeddingService with mocked provider."""
    
    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test embedding service initialization."""
        service = EmbeddingService(
            provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            model_name="all-MiniLM-L6-v2"
        )
        
        assert service._is_initialized is False
        assert isinstance(service.cache, EmbeddingCache)
        assert isinstance(service.metrics, EmbeddingMetrics)
    
    @pytest.mark.asyncio
    async def test_service_embed_text_cached(self):
        """Test that second call returns cached result."""
        service = EmbeddingService(
            provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            model_name="test"
        )
        
        # Mock the provider
        record = EmbeddingRecord(
            text="Hello",
            embedding=[0.1, 0.2],
            dimension=2,
            model="test",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=1,
            generation_time_ms=1.0,
            timestamp=datetime.utcnow(),
        )
        
        service.provider = AsyncMock()
        service.provider.embed_text = AsyncMock(return_value=record)
        service.provider.embedding_dimension = 2
        service.provider.get_cost_estimate = Mock(return_value=0.001)
        service._is_initialized = True
        
        # First call - should not use cache
        result1 = await service.embed_text("Hello")
        assert result1 is record
        assert service.provider.embed_text.call_count == 1
        
        # Second call - should use cache
        result2 = await service.embed_text("Hello")
        assert result2 is result1
        assert service.provider.embed_text.call_count == 1  # Not called again
        
        # Verify metrics
        stats = service.metrics.get_stats()
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
    
    @pytest.mark.asyncio
    async def test_service_batch_embedding(self):
        """Test batch embedding with caching."""
        service = EmbeddingService(
            provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            model_name="test"
        )
        
        # Create mock records
        records = [
            EmbeddingRecord(
                text=f"Text {i}",
                embedding=[float(i)] * 2,
                dimension=2,
                model="test",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=1,
                generation_time_ms=1.0,
                timestamp=datetime.utcnow(),
            )
            for i in range(3)
        ]
        
        service.provider = AsyncMock()
        service.provider.embed_batch = AsyncMock(return_value=records)
        service.provider.embedding_dimension = 2
        service.provider.get_cost_estimate = Mock(return_value=0.001)
        service._is_initialized = True
        
        # Embed batch
        results = await service.embed_batch(["Text 0", "Text 1", "Text 2"])
        
        assert len(results) == 3
        assert service.provider.embed_batch.call_count == 1
        
        # All should be cached now
        metrics = service.metrics.get_stats()
        assert metrics["total_requests"] == 1
    
    @pytest.mark.asyncio
    async def test_service_batch_with_cache_hits(self):
        """Test batch embedding with some cached items."""
        service = EmbeddingService(
            provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            model_name="test"
        )
        
        # Pre-cache one item
        cached_record = EmbeddingRecord(
            text="Cached",
            embedding=[0.1],
            dimension=1,
            model="test",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=1,
            generation_time_ms=1.0,
            timestamp=datetime.utcnow(),
        )
        service.cache.set("Cached", cached_record)
        
        # Create mock records for new items
        new_records = [
            EmbeddingRecord(
                text="New 1",
                embedding=[0.2],
                dimension=1,
                model="test",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=1,
                generation_time_ms=1.0,
                timestamp=datetime.utcnow(),
            ),
            EmbeddingRecord(
                text="New 2",
                embedding=[0.3],
                dimension=1,
                model="test",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=1,
                generation_time_ms=1.0,
                timestamp=datetime.utcnow(),
            )
        ]
        
        service.provider = AsyncMock()
        service.provider.embed_batch = AsyncMock(return_value=new_records)
        service.provider.embedding_dimension = 1
        service.provider.get_cost_estimate = Mock(return_value=0.001)
        service._is_initialized = True
        
        # Embed batch with one cached and two new
        results = await service.embed_batch(["Cached", "New 1", "New 2"])
        
        assert len(results) == 3
        assert results[0] is cached_record
        # Only new items should be embedded
        assert service.provider.embed_batch.call_count == 1
        call_args = service.provider.embed_batch.call_args
        assert call_args[0][0].batch_size == 2  # Only 2 new texts
    
    @pytest.mark.asyncio
    async def test_service_clear_cache(self):
        """Test clearing cache."""
        service = EmbeddingService(
            provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            model_name="test"
        )
        
        # Add item to cache
        record = EmbeddingRecord(
            text="Hello",
            embedding=[0.1],
            dimension=1,
            model="test",
            provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            tokens_used=1,
            generation_time_ms=1.0,
            timestamp=datetime.utcnow(),
        )
        service.cache.set("Hello", record)
        
        assert service.cache.get("Hello") is not None
        
        # Clear cache
        await service.clear_cache()
        
        assert service.cache.get("Hello") is None


# ============================================================================
# Test: Integration Tests
# ============================================================================

class TestEmbeddingIntegration:
    """Integration tests for embedding module."""
    
    def test_embedding_provider_type_enum(self):
        """Test EmbeddingProviderType enum."""
        assert EmbeddingProviderType.SENTENCE_TRANSFORMER == "sentence_transformer"
        assert EmbeddingProviderType.OPENAI == "openai"
        assert EmbeddingProviderType.COHERE == "cohere"
    
    def test_provider_config(self):
        """Test ProviderConfig."""
        config = ProviderConfig(
            api_key="sk-123456",
            timeout_seconds=30,
            custom_param="value"
        )
        
        config_dict = config.to_dict()
        assert config_dict["api_key"] == "sk-123456"
        assert config_dict["timeout_seconds"] == 30
        assert config_dict["custom_param"] == "value"
    
    @pytest.mark.asyncio
    async def test_full_service_workflow(self):
        """Test complete service workflow."""
        service = EmbeddingService(
            provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
            model_name="test",
            cache_config={"max_size": 1000, "ttl_seconds": 3600}
        )
        
        # Mock provider
        service.provider = AsyncMock()
        service.provider.initialize = AsyncMock()
        service.provider.embed_text = AsyncMock(
            return_value=EmbeddingRecord(
                text="Test",
                embedding=[0.5],
                dimension=1,
                model="test",
                provider=EmbeddingProviderType.SENTENCE_TRANSFORMER,
                tokens_used=1,
                generation_time_ms=10.0,
                timestamp=datetime.utcnow(),
            )
        )
        service.provider.embedding_dimension = 1
        service.provider.get_cost_estimate = Mock(return_value=0.001)
        service.provider.health_check = AsyncMock(return_value=True)
        
        # Initialize
        await service.initialize()
        assert service._is_initialized
        
        # Embed text
        record = await service.embed_text("Test")
        assert record.embedding == [0.5]
        
        # Health check
        is_healthy = await service.health_check()
        assert is_healthy
        
        # Get metrics
        metrics = service.get_metrics()
        assert "embedding_service" in metrics
        assert "cache" in metrics
        assert "provider" in metrics
