# Phase 1.3: Similarity Search - Usage Guide

## Overview

Phase 1.3 implements semantic similarity search with HNSW indexing, supporting 5 similarity metrics and domain-specific thresholds for intelligent query comparison.

## Quick Start

```python
from src.search.similarity import SimilaritySearch, SimilarityMetric, DomainType
from src.cache.embeddings import EmbeddingService

# Initialize embedding service
embedding_service = EmbeddingService(model="sentence-transformers/all-MiniLM-L6-v2")

# Initialize similarity search
search = SimilaritySearch(metric=SimilarityMetric.COSINE)

# Index embeddings
query = "What is machine learning?"
embedding = embedding_service.embed_query(query)
search.add_embedding(embedding, query_id="q_1", metadata={"domain": "general"})

# Search for similar queries
results = search.search(embedding, top_k=5)
for result in results:
    print(f"Query ID: {result.query_id}, Score: {result.similarity}")
```

## Similarity Metrics

### 1. Cosine Similarity (Default)
Best for high-dimensional embeddings. Measures angle between vectors.

```python
from src.search.similarity import SimilarityMetric, SimilaritySearch

search = SimilaritySearch(metric=SimilarityMetric.COSINE)
results = search.search(embedding, top_k=10)
# Higher cosine similarity = more similar queries
```

**Use Cases:**
- Text embeddings (most common)
- Document similarity
- General semantic search

### 2. Euclidean Distance
Measures straight-line distance. Lower is more similar.

```python
search = SimilaritySearch(metric=SimilarityMetric.EUCLIDEAN)
results = search.search(embedding, top_k=10)
# Lower euclidean distance = more similar
```

**Use Cases:**
- Feature vectors
- Numerical data
- Computer vision embeddings

### 3. Manhattan Distance
City-block distance. Fast but less accurate than Euclidean.

```python
search = SimilaritySearch(metric=SimilarityMetric.MANHATTAN)
results = search.search(embedding, top_k=10)
```

**Use Cases:**
- Sparse embeddings
- Fast approximate matching
- High-dimensional spaces

### 4. Hamming Distance
For binary vectors. Counts differing bits.

```python
search = SimilaritySearch(metric=SimilarityMetric.HAMMING)
results = search.search(embedding, top_k=10)
```

**Use Cases:**
- Hashed embeddings
- Binary feature vectors
- Fingerprint comparison

### 5. Jaccard Similarity
Set-based similarity. Measures intersection over union.

```python
search = SimilaritySearch(metric=SimilarityMetric.JACCARD)
results = search.search(embedding, top_k=10)
```

**Use Cases:**
- Categorical data
- Set comparison
- Tag-based matching

## Domain-Specific Thresholds

Automatically adjust similarity thresholds based on domain:

```python
from src.search.similarity import DomainType

# Get domain-specific threshold
threshold = SimilaritySearch.get_domain_threshold(DomainType.MEDICAL)
# Returns 0.95 (more strict for medical accuracy)

threshold = SimilaritySearch.get_domain_threshold(DomainType.ECOMMERCE)
# Returns 0.80 (more lenient for commercial relevance)

# Use with search
similar_results = search.search(
    embedding,
    top_k=10,
    threshold=SimilaritySearch.get_domain_threshold(DomainType.GENERAL)
)
```

**Domain Thresholds:**
- MEDICAL: 0.95 (very strict)
- LEGAL: 0.90 (strict)
- TECHNICAL: 0.85 (moderate)
- GENERAL: 0.75 (lenient)
- ECOMMERCE: 0.80 (commercial)

## HNSW Indexing

Approximate Nearest Neighbor Search for fast retrieval:

```python
from src.search.similarity import SimilaritySearch

# Initialize with HNSW parameters
search = SimilaritySearch(
    metric=SimilarityMetric.COSINE,
    use_hnsw=True,
    hnsw_max_m=16,
    hnsw_ef_construction=200,
    hnsw_ef=50
)

# Add many embeddings efficiently
for i in range(10000):
    embedding = embedding_service.embed_query(f"Query {i}")
    search.add_embedding(embedding, query_id=f"q_{i}")

# Fast approximate search
results = search.search(embedding, top_k=10)
# Returns top 10 similar items in ~10-50ms even with 10k+ embeddings
```

**HNSW Parameters:**
- `max_m`: Maximum connections per node (higher = more accurate, slower)
- `ef_construction`: Size of dynamic list (higher = more accurate, slower build)
- `ef`: Size of dynamic list at query time (higher accuracy, slower search)

## Advanced Usage

### Batch Search

```python
# Search for multiple queries efficiently
queries = ["machine learning", "deep learning", "embeddings"]
embeddings = embedding_service.embed_batch(queries)
batch_results = search.search_batch(embeddings, top_k=5)
```

### Filtering Results

```python
# Get results above threshold
results = search.search(embedding, top_k=10, threshold=0.80)
similar = [r for r in results if r.similarity >= 0.80]

# Filter by metadata
results_by_domain = search.search_with_metadata(
    embedding,
    top_k=10,
    metadata_filter={"domain": "technical"}
)
```

### Index Statistics

```python
# Get indexing information
stats = search.get_stats()
print(f"Total embeddings: {stats.total_embeddings}")
print(f"Index built: {stats.index_built}")
print(f"Dimensions: {stats.dimensions}")
```

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Add embedding | 0.1-1ms | O(log n) with HNSW |
| Search | 10-50ms | 10k embeddings, k=10 |
| Batch add (100) | 20-100ms | Vectorized |
| Batch search (10) | 100-500ms | Parallelized |

## Common Patterns

### Pattern 1: String Similarity Search

```python
# Find similar queries in cache
def find_similar_queries(user_query: str, top_k: int = 5):
    embedding = embedding_service.embed_query(user_query)
    results = search.search(embedding, top_k=top_k, threshold=0.80)
    return results

# Use in cache
results = find_similar_queries("What is ML?")
if results:
    # Try cached response from most similar query
    use_cached_response(results[0].query_id)
```

### Pattern 2: Domain-Aware Search

```python
# Different thresholds for different domains
def search_with_domain(embedding, domain: str, top_k: int = 5):
    threshold = SimilaritySearch.get_domain_threshold(domain)
    return search.search(embedding, top_k=top_k, threshold=threshold)
```

### Pattern 3: Multi-Metric Ensemble

```python
# Use multiple metrics for robust matching
metrics = [SimilarityMetric.COSINE, SimilarityMetric.EUCLIDEAN]
ensemble_results = []

for metric in metrics:
    searcher = SimilaritySearch(metric=metric)
    results = searcher.search(embedding, top_k=5)
    ensemble_results.extend(results)

# Rank by average score
ranked = rank_by_average_score(ensemble_results)
```

## Testing & Validation

```python
# Test similarity metrics
from tests.unit.search.test_similarity import TestSimilarityMetrics

# Run similarity tests
pytest tests/unit/search/test_similarity_metrics.py -v

# Test HNSW indexing
pytest tests/unit/search/test_hnsw_indexing.py -v

# Test domain thresholds
pytest tests/unit/search/test_domain_thresholds.py -v
```

## API Reference

### SimilaritySearch

```python
class SimilaritySearch:
    def __init__(
        self,
        metric: SimilarityMetric = SimilarityMetric.COSINE,
        use_hnsw: bool = True,
        hnsw_max_m: int = 16,
        hnsw_ef_construction: int = 200,
        hnsw_ef: int = 50
    )
    
    def add_embedding(
        self,
        embedding: np.ndarray,
        query_id: str,
        metadata: Optional[Dict] = None
    ) -> None
    
    def search(
        self,
        embedding: np.ndarray,
        top_k: int = 10,
        threshold: float = 0.0
    ) -> List[SimilarityResult]
    
    def search_batch(
        self,
        embeddings: np.ndarray,
        top_k: int = 10
    ) -> List[List[SimilarityResult]]
```

## Troubleshooting

### Issue: Low similarity scores
**Solution:** Check domain threshold is appropriate

### Issue: Search too slow
**Solution:** Adjust HNSW parameters (lower ef_construction) or reduce top_k

### Issue: Memory usage high
**Solution:** Use pagination or reduce number of indexed embeddings

## Next Steps
- Proceed to [Phase 1.4 L1 Cache](./PHASE_1_4_L1_CACHE_USAGE.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
