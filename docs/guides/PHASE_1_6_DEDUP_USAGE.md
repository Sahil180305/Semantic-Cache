# Phase 1.6: Query Deduplication - Usage Guide

## Overview

Phase 1.6 implements query deduplication and similarity detection to reduce redundant cache lookups and identify similar query patterns.

## Quick Start

```python
from src.cache.query_dedup import (
    QueryDeduplicationEngine,
    DeduplicationStrategy,
    PrefixMatchingEngine
)

# Initialize deduplication engine
engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.NORMALIZED,
    similarity_threshold=0.85
)

# Register queries
canonical, is_duplicate = engine.register_query("What is machine learning?")
canonical, is_duplicate = engine.register_query("what is machine learning")  # Duplicate!

print(f"Canonical: {canonical}")
print(f"Is duplicate: {is_duplicate}")  # True

# Get statistics
stats = engine.get_stats()
print(f"Unique queries: {stats['unique_queries']}")
print(f"Duplicates detected: {stats['total_deduplicated']}")
```

## Deduplication Strategies

### 1. EXACT - Exact String Match

Only identical queries considered duplicates.

```python
engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.EXACT)

canonical, is_dup = engine.register_query("Hello World")
canonical, is_dup = engine.register_query("Hello World")  # Duplicate
canonical, is_dup = engine.register_query("hello world")  # NOT duplicate (case sensitive)
```

**Use Case:** When exact match required (SQL queries, code)

### 2. NORMALIZED - Case/Punctuation Insensitive

Ignores case, punctuation, and extra whitespace.

```python
engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)

canonical, is_dup = engine.register_query("Hello World!")
canonical, is_dup = engine.register_query("hello world?")  # Duplicate
canonical, is_dup = engine.register_query("HELLO   WORLD")  # Duplicate
```

**Use Case:** Most common, natural language queries

### 3. SEMANTIC - Fuzzy Similarity Matching

Uses token overlap and character similarity with threshold.

```python
engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.SEMANTIC,
    similarity_threshold=0.80
)

canonical, is_dup = engine.register_query("machine learning models")
canonical, is_dup = engine.register_query("machine learning systems")  # Duplicate (0.85 similar)
canonical, is_dup = engine.register_query("deep learning basics")  # NOT dup (0.70 similar)
```

**Use Case:** Finding similar queries, pattern matching

### 4. PREFIX - Prefix-Based Grouping

Groups queries by common prefix.

```python
engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.PREFIX)

canonical, is_dup = engine.register_query("machine learning")
canonical, is_dup = engine.register_query("machine learning models")  # Same prefix
canonical, is_dup = engine.register_query("deep learning")  # Different prefix
```

**Use Case:** Query grouping, related query discovery

## Query Normalization

### Basic Normalization

```python
from src.cache.query_dedup import QueryNormalizer

normalizer = QueryNormalizer()

# Case insensitive
assert normalizer.normalize("HELLO") == "hello"

# Remove punctuation
assert normalizer.normalize("Hello, World!") == "hello world"

# Clean whitespace
assert normalizer.normalize("Hello    World") == "hello world"
```

### Token Extraction

```python
# Extract meaningful tokens (removes stop words, short words)
normalized, tokens = normalizer.normalize_with_tokens("What is machine learning?")

# Results:
# normalized: "what is machine learning"
# tokens: ["machine", "learning"]  # "what" and "is" removed as stop words
```

## Prefix Matching

### Grouping Queries by Prefix

```python
prefix_engine = PrefixMatchingEngine(min_prefix_length=5)

# Register queries
prefix_engine.register_prefix("machine learning basics")
prefix_engine.register_prefix("machine learning tutorial")
prefix_engine.register_prefix("machine learning fundamentals")

# Find all queries with same prefix
group = prefix_engine.find_by_prefix("machi")
# Returns all 3 queries
```

### Use Cases

```python
# Example 1: Auto-complete suggestions
def get_related_queries(user_input: str):
    prefix_engine = PrefixMatchingEngine()
    prefix = user_input[:5]
    return prefix_engine.find_by_prefix(prefix)

# Example 2: Query categorization
def categorize_queries(queries):
    prefix_engine = PrefixMatchingEngine()
    categories = {}
    
    for query in queries:
        prefix = query[:5]
        prefix_engine.register_prefix(query)
        
        if prefix not in categories:
            categories[prefix] = []
        categories[prefix].append(query)
    
    return categories
```

## Similarity Metrics

### Token Overlap

Measures shared tokens between queries:

```python
from src.cache.query_dedup import QuerySimilarityMatcher

matcher = QuerySimilarityMatcher()
metrics = matcher.compare_queries(
    "machine learning systems",
    "machine learning models"
)

# Results:
# token_overlap: 0.67  # 2 out of 3 tokens match
```

### Character Similarity

Uses sequence matching (Levenshtein-like):

```python
metrics = matcher.compare_queries(
    "machine learning",
    "machine learnings"
)

# Results:
# char_similarity: 0.94  # Very similar strings
```

### Finding Similar Queries

```python
candidates = [
    "machine learning",
    "machine learnings",
    "deep learning",
    "reinforcement learning"
]

matcher = QuerySimilarityMatcher()
similar = matcher.find_similar(
    "machine learning models",
    candidates,
    threshold=0.70  # 70% confidence
)

# Returns candidates with confidence scores
for candidate, metrics in similar:
    print(f"{candidate}: {metrics.char_similarity:.2%}")
```

## Advanced Usage

### Multi-Strategy Deduplication

```python
# Use different strategies for different query types
strategies = {
    "sql": DeduplicationStrategy.EXACT,
    "natural": DeduplicationStrategy.NORMALIZED,
    "semantic": DeduplicationStrategy.SEMANTIC,
}

def deduplicate(query: str, query_type: str):
    engine = QueryDeduplicationEngine(
        strategy=strategies[query_type]
    )
    return engine.register_query(query)
```

### Configurable Thresholds

```python
# Strict matching (high threshold)
strict_engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.SEMANTIC,
    similarity_threshold=0.95
)

# Lenient matching (low threshold)
lenient_engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.SEMANTIC,
    similarity_threshold=0.50
)
```

### Batch Deduplication

```python
engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)

queries = [
    "What is machine learning?",
    "what is machine learning",
    "Machine Learning?",
    "calculate sum of 1 + 1",
    "sum 1 plus 1"
]

canonical_queries = {}
for query in queries:
    canonical, is_dup = engine.register_query(query)
    if not is_dup:
        canonical_queries[canonical] = []

# Process only unique queries
print(f"Unique queries: {len(canonical_queries)}")
```

## Integration with Cache

### Pattern 1: Deduplicate at Cache Entry

```python
def cache_with_dedup(key: str, embedding, result):
    # Check for similar existing keys
    engine = QueryDeduplicationEngine(
        strategy=DeduplicationStrategy.NORMALIZED
    )
    
    canonical, is_dup = engine.register_query(key)
    
    if is_dup:
        # Use canonical form
        cache.put(canonical, embedding, result)
    else:
        cache.put(key, embedding, result)
```

### Pattern 2: Automatic Query Grouping

```python
def get_with_similar(query: str):
    engine = QueryDeduplicationEngine(
        strategy=DeduplicationStrategy.SEMANTIC,
        similarity_threshold=0.85
    )
    
    canonical, is_dup = engine.register_query(query)
    
    # Try exact match first
    result = cache.get(canonical)
    
    if result is None:
        # Try similar queries
        matcher = QuerySimilarityMatcher()
        similar = matcher.find_similar(query, cache.keys(), threshold=0.80)
        
        if similar:
            result = cache.get(similar[0][0])
    
    return result
```

### Pattern 3: Prefix-Based Caching

```python
def find_cached_by_prefix(query: str):
    prefix_engine = PrefixMatchingEngine()
    
    # Get related queries with same prefix
    related = prefix_engine.find_by_prefix(query[:5])
    
    # Try to use cached result from related queries
    for related_query in related:
        result = cache.get(related_query)
        if result is not None:
            return result
    
    return None
```

## Metrics & Monitoring

```python
engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)

# Register some queries
for i in range(100):
    query = f"What is {'machine learning' if i % 2 == 0 else 'deep learning'}?"
    engine.register_query(query)

# Get statistics
stats = engine.get_stats()

print(f"Strategy: {stats['strategy']}")
print(f"Total deduplicated: {stats['total_deduplicated']}")
print(f"Unique queries: {stats['unique_queries']}")
print(f"Reduction: {(1 - stats['unique_queries']/100)*100:.1f}%")
```

## Troubleshooting

### Too Many Duplicates Detected

**Solution:** Lower similarity threshold or use EXACT strategy

```python
# Check what's being marked as duplicate
engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)
canonical, is_dup = engine.register_query(test_query)
print(f"Marked as duplicate: {is_dup}")
```

### Too Few Duplicates Detected

**Solution:** Higher similarity threshold or use SEMANTIC strategy

```python
engine = QueryDeduplicationEngine(
    strategy=DeduplicationStrategy.SEMANTIC,
    similarity_threshold=0.70  # Lower threshold
)
```

## Testing

```bash
# Run deduplication tests
pytest tests/unit/cache/test_phase_1_6_dedup.py -v

# Test normalization
pytest tests/unit/cache/test_phase_1_6_dedup.py::TestQueryNormalizer -v

# Test similarity
pytest tests/unit/cache/test_phase_1_6_dedup.py::TestQuerySimilarityMatcher -v

# Test prefix matching
pytest tests/unit/cache/test_phase_1_6_dedup.py::TestPrefixMatchingEngine -v
```

## API Reference

```python
class QueryDeduplicationEngine:
    def register_query(self, query: str) -> Tuple[str, bool]
    def get_stats(self) -> Dict[str, any]
    def clear(self) -> None

class QuerySimilarityMatcher:
    def compare_queries(self, query1: str, query2: str) -> SimilarityMetrics
    def find_similar(self, query: str, candidates: List[str], threshold: float) -> List[Tuple[str, SimilarityMetrics]]

class PrefixMatchingEngine:
    def register_prefix(self, query: str) -> str
    def find_by_prefix(self, prefix: str) -> List[str]
    def clear(self) -> None
```

## Next Steps
- Proceed to [Phase 1.7 Advanced Policies](./PHASE_1_7_POLICIES_USAGE.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
