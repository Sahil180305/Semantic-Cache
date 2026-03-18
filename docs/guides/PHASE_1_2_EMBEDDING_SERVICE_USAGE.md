# Phase 1.2: Embedding Service Usage Guide

## Overview

Phase 1.2 implements a flexible, high-performance embedding service with support for multiple providers (local and API-based). The service includes:

- **Multi-Provider Support**: Sentence Transformers (local), OpenAI, Cohere, HuggingFace Inference
- **Intelligent Caching**: Automatic deduplication and TTL-based expiration
- **Batch Processing**: Efficient parallel embedding generation
- **Retry Logic**: Exponential backoff for transient failures
- **Cost Tracking**: Automatic cost calculation and metrics
- **Comprehensive Metrics**: Request tracking, cache statistics, error monitoring

## Quick Start

### 1. Local Embeddings (No API Key Required)

```python
import asyncio
from src.embedding.service import EmbeddingService
from src.embedding.base import EmbeddingProviderType

async def main():
    # Create service with local embeddings
    service = EmbeddingService(
        provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
        model_name="all-MiniLM-L6-v2"
    )
    
    # Initialize (downloads model on first run)
    await service.initialize()
    
    # Embed a single text
    record = await service.embed_text("Hello, world!")
    print(f"Embedding dimension: {record.dimension}")
    print(f"Generation time: {record.generation_time_ms}ms")
    print(f"Embedding: {record.embedding[:3]}...")  # First 3 values

asyncio.run(main())
```

### 2. OpenAI Embeddings

```python
import os
from src.embedding.service import EmbeddingService
from src.embedding.base import EmbeddingProviderType, ProviderConfig

async def main():
    # Create service with OpenAI
    service = EmbeddingService(
        provider_type=EmbeddingProviderType.OPENAI,
        model_name="text-embedding-3-small",
        config=ProviderConfig(api_key=os.getenv("OPENAI_API_KEY"))
    )
    
    # Initialize
    await service.initialize()
    
    # Embed text
    record = await service.embed_text("What is semantic caching?")
    print(f"Cost: ${service.provider.get_cost_estimate(record.tokens_used):.6f}")

asyncio.run(main())
```

### 3. Batch Processing

```python
async def main():
    service = EmbeddingService(
        provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
        model_name="all-MiniLM-L6-v2"
    )
    await service.initialize()
    
    # Embed multiple texts efficiently
    texts = [
        "Machine learning is...",
        "Deep learning is...",
        "Neural networks are...",
    ]
    records = await service.embed_batch(texts)
    
    print(f"Embedded {len(records)} texts")
    print(f"Average generation time: {sum(r.generation_time_ms for r in records) / len(records):.2f}ms")

asyncio.run(main())
```

## Core Classes

### EmbeddingService

Main service class for embedding generation.

**Constructor Parameters:**
- `provider_type`: Type of embedding provider (EmbeddingProviderType enum)
- `model_name`: Model identifier (e.g., "all-MiniLM-L6-v2")
- `config`: Optional ProviderConfig with provider-specific settings
- `cache_config`: Dict with cache settings:
  - `max_size`: Maximum cached embeddings (default: 100,000)
  - `ttl_seconds`: Cache TTL in seconds (default: None = no expiration)
- `retry_config`: RetryConfig for automatic retries

**Key Methods:**

```python
# Initialize the service (must be called before use)
await service.initialize()

# Embed a single text (uses cache automatically)
record = await service.embed_text("Query text")

# Embed multiple texts (batch processing with cache)
records = await service.embed_batch(["Text 1", "Text 2", "Text 3"])

# Check service health
is_healthy = await service.health_check()

# Get service metrics
metrics = service.get_metrics()

# Clear cache
await service.clear_cache()
```

### EmbeddingRecord

Represents a single embedding result.

**Attributes:**
- `text`: Original input text
- `embedding`: List of floats (the dense vector)
- `dimension`: Vector dimension
- `model`: Model identifier
- `provider`: Provider type
- `tokens_used`: Token count (for cost calculation)
- `generation_time_ms`: Time to generate
- `timestamp`: When generated
- `metadata`: Optional additional info

**Methods:**
```python
# Get SHA256 hash of original text (useful for deduplication)
text_hash = record.text_hash
```

### EmbeddingCache

In-memory cache for embeddings with TTL and size limits.

```python
cache = EmbeddingCache(max_size=100000, ttl_seconds=3600)

# Get cached embedding
cached = cache.get("Some text")

# Cache new embedding
cache.set("Some text", embedding_record)

# Get statistics
stats = cache.get_stats()
print(f"Cached entries: {stats['cached_entries']}")
print(f"Usage: {stats['usage_percent']}%")

# Clear all
cache.cache.clear()
```

### RetryConfig

Configuration for automatic retry logic with exponential backoff.

```python
retry_config = RetryConfig(
    max_retries=3,
    initial_delay_ms=100.0,
    max_delay_ms=5000.0,
    backoff_factor=2.0,
    retryable_errors=["API_ERROR", "RATE_LIMITED", "TIMEOUT"]
)
```

**Delay Calculation:** `delay = initial_delay * (backoff_factor ^ attempt)`
- Attempt 0: 100ms
- Attempt 1: 200ms
- Attempt 2: 400ms
- (capped at max_delay_ms)

### EmbeddingMetrics

Tracks embedding generation metrics.

```python
metrics = service.metrics

# Get comprehensive statistics
stats = metrics.get_stats()
print(f"Total requests: {stats['total_requests']}")
print(f"Cache hit rate: {stats['hit_rate']:.2%}")
print(f"Average time: {stats['avg_time_ms']:.2f}ms")
print(f"Total cost: ${stats['total_cost']:.6f}")
print(f"Errors: {stats['errors']}")
```

## Provider Types

### 1. SentenceTransformerProvider (Local)

No API key required. Runs embeddings locally on your machine/GPU.

**Supported Models:**
- `all-MiniLM-L6-v2` (384 dims) - **Recommended** for most use cases (fast, good quality)
- `all-mpnet-base-v2` (768 dims) - Higher quality but slower
- `paraphrase-MiniLM-L6-v2` (384 dims) - Optimized for paraphrase detection

**Advantages:**
- No API costs
- No rate limiting
- Privacy (data stays local)
- Fast iteration during development

**Requirements:**
```bash
pip install sentence-transformers torch
```

**Example:**
```python
service = EmbeddingService(
    provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
    model_name="all-MiniLM-L6-v2"
)
await service.initialize()
record = await service.embed_text("Text to embed")
```

### 2. OpenAIProvider (API)

Uses OpenAI's embedding models via API.

**Supported Models:**
- `text-embedding-3-small` (1536 dims) - Most cost-effective
- `text-embedding-3-large` (3072 dims) - Higher quality

**Pricing:** ~$0.02-0.13 per 1M tokens

**Setup:**
```bash
pip install openai
export OPENAI_API_KEY="sk-..."
```

**Example:**
```python
service = EmbeddingService(
    provider_type=EmbeddingProviderType.OPENAI,
    model_name="text-embedding-3-small",
    config=ProviderConfig(api_key=os.getenv("OPENAI_API_KEY"))
)
await service.initialize()
record = await service.embed_text("Text to embed")
cost = service.provider.get_cost_estimate(record.tokens_used)
print(f"Cost: ${cost:.6f}")
```

### 3. CohereProvider (API)

Uses Cohere's embedding models via API.

**Supported Models:**
- `embed-english-v3.0` (1024 dims)
- `embed-english-light-v3.0` (384 dims)

**Setup:**
```bash
pip install cohere
export COHERE_API_KEY="..."
```

**Example:**
```python
service = EmbeddingService(
    provider_type=EmbeddingProviderType.COHERE,
    model_name="embed-english-v3.0",
    config=ProviderConfig(api_key=os.getenv("COHERE_API_KEY"))
)
await service.initialize()
records = await service.embed_batch(["Text 1", "Text 2"])
```

## Advanced Usage

### Custom Cache Configuration

```python
service = EmbeddingService(
    provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
    model_name="all-MiniLM-L6-v2",
    cache_config={
        "max_size": 50000,  # Smaller cache for memory-constrained environments
        "ttl_seconds": 1800  # 30-minute TTL
    }
)
```

### Custom Retry Configuration

```python
from src.embedding.service import RetryConfig

retry_config = RetryConfig(
    max_retries=5,
    initial_delay_ms=50.0,
    max_delay_ms=10000.0,
    backoff_factor=1.5
)

service = EmbeddingService(
    provider_type=EmbeddingProviderType.OPENAI,
    model_name="text-embedding-3-small",
    retry_config=retry_config
)
```

### Monitoring and Metrics

```python
service = EmbeddingService(...)
await service.initialize()

# Embed some texts
await service.embed_text("First query")
await service.embed_text("Second query")
await service.embed_text("First query")  # Cache hit

# Get comprehensive metrics
metrics = service.get_metrics()

print("=== Embedding Service Metrics ===")
print(f"Total requests: {metrics['embedding_service']['total_requests']}")
print(f"Cache hits: {metrics['embedding_service']['cache_hits']}")
print(f"Hit rate: {metrics['embedding_service']['hit_rate']:.2%}")
print(f"Total tokens: {metrics['embedding_service']['total_tokens']}")
print(f"Total cost: ${metrics['embedding_service']['total_cost']:.6f}")
print(f"Avg time: {metrics['embedding_service']['avg_time_ms']:.2f}ms")

print("\n=== Cache Statistics ===")
print(f"Cached entries: {metrics['cache']['cached_entries']}")
print(f"Max size: {metrics['cache']['max_size']}")
print(f"Usage: {metrics['cache']['usage_percent']:.1f}%")

print("\n=== Provider Info ===")
print(f"Type: {metrics['provider']['type']}")
print(f"Model: {metrics['provider']['model']}")
print(f"Dimension: {metrics['provider']['dimension']}")
```

### Handling Errors

```python
from src.core.exceptions import EmbeddingError

service = EmbeddingService(...)

try:
    await service.initialize()
    record = await service.embed_text("Text")
except EmbeddingError as e:
    print(f"Error code: {e.error_code}")
    print(f"Message: {e.message}")
    print(f"Details: {e.details}")
```

## Testing

Run Phase 1.2 tests:

```bash
# Run all embedding tests
python -m pytest tests/unit/embedding/test_phases_1_2_service.py -v

# Run specific test class
python -m pytest tests/unit/embedding/test_phases_1_2_service.py::TestEmbeddingService -v

# Run with coverage
python -m pytest tests/unit/embedding/test_phases_1_2_service.py --cov=src/embedding
```

## Performance Characteristics

### SentenceTransformer (Local)
- **Latency**: 1-5ms per text (CPU), <1ms (GPU)
- **Throughput**: 100+ texts/sec (single threaded)
- **Memory**: ~500MB per model
- **Cost**: $0

### OpenAI
- **Latency**: 100-500ms per request
- **Throughput**: 50 requests/sec (batched)
- **Memory**: Minimal (API-based)
- **Cost**: $0.02 per 1M tokens (text-embedding-3-small)

### Cohere
- **Latency**: 100-500ms per request
- **Throughput**: 50+ requests/sec (batched)
- **Memory**: Minimal (API-based)
- **Cost**: Varies by plan

## Next Steps

Phase 1.3 will implement:
- Similarity search algorithms (cosine, euclidean, inner product)
- Domain-adaptive thresholds
- L1 cache (in-memory HNSW index)
- Query deduplication

## File Structure

```
src/embedding/
├── __init__.py              # Module exports
├── base.py                  # Abstract interfaces (400+ lines)
├── providers.py             # Concrete implementations (500+ lines)
└── service.py               # Orchestrator service (500+ lines)

tests/unit/embedding/
├── __init__.py
└── test_phases_1_2_service.py  # 33 comprehensive tests
```

## Summary

- **Total Phase 1.2 Code**: ~1,400 lines
- **Test Coverage**: 33 test cases (100% pass rate)
- **Provider Support**: 3 main providers + factory pattern for extensibility
- **Features**: Caching, batching, retries, metrics, cost tracking
- **Ready for Integration**: Phase 1.3 (Similarity Search) can use service
