# Phase 1.7: Advanced Caching Policies - Usage Guide

## Overview

Phase 1.7 provides intelligent, adaptive caching policies that learn access patterns and optimize cache behavior based on system load and memory constraints.

## Quick Start

```python
from src.cache.advanced_policies import (
    AdvancedCachingPolicyManager,
    CostAwareEvictionPolicy,
    AdaptivePolicy,
    AccessPatternAnalyzer
)

# Initialize with adaptive policy
manager = AdvancedCachingPolicyManager(
    max_memory=1000,
    learning_enabled=True
)

# Put items with cost information
manager.put(
    key="expensive_query_1",
    value="result 1",
    cost=50.0  # Expensive to compute
)

manager.put(
    key="cheap_query_1",
    value="result 2",
    cost=1.0  # Cheap to compute
)

# Get - may trigger adaptive behavior
result = manager.get("expensive_query_1")

# View learned patterns
patterns = manager.get_access_patterns()
print(f"Learned patterns: {len(patterns)}")
```

## Access Pattern Analysis

### Measuring Query Behavior

```python
from src.cache.advanced_policies import AccessPatternAnalyzer

analyzer = AccessPatternAnalyzer()

# Record access
analyzer.record_access("query_1", latency_ms=50, cost=100)
analyzer.record_access("query_1", latency_ms=48, cost=100)
analyzer.record_access("query_1", latency_ms=52, cost=100)

# Get patterns
pattern = analyzer.get_pattern("query_1")

print(f"Frequency: {pattern.access_frequency}")  # How often accessed
print(f"Latency: {pattern.avg_latency_ms}")  # Typical latency
print(f"Recency: {pattern.last_access_timestamp}")  # When last accessed
print(f"Cost: {pattern.avg_cost}")  # Average computation cost
```

### Pattern Types

```python
# High-frequency, high-latency (prioritize keeping)
hot_expensive = {
    "access_frequency": 10,  # 10 accesses
    "avg_latency_ms": 500,   # 500ms average
    "avg_cost": 100          # Expensive
}

# Low-frequency, low-latency (can evict)
cold_cheap = {
    "access_frequency": 1,   # 1 access
    "avg_latency_ms": 10,    # 10ms average
    "avg_cost": 1            # Cheap
}

# Decision: Keep hot_expensive, evict cold_cheap
```

## Cost-Aware Eviction

### Policy Overview

Evicts items based on computation cost, not just access patterns.

```python
from src.cache.advanced_policies import CostAwareEvictionPolicy

policy = CostAwareEvictionPolicy(max_items=100)

# Register items with costs (higher = more expensive to recompute)
policy.put("query_1", {"cost": 100})  # Expensive
policy.put("query_2", {"cost": 10})   # Medium
policy.put("query_3", {"cost": 1})    # Cheap

# When eviction needed, removes cheap items first
evicted = policy.evict_one()
print(f"Evicted: {evicted}")  # "query_3" (cheapest to recompute)
```

### Cost Calculation

```python
def calculate_cost(query: str) -> float:
    """Calculate recomputation cost for a query"""
    # Option 1: Direct cost
    if "embedding_generation" in query:
        return 100.0  # Expensive
    
    # Option 2: Time-based cost
    if "complex_join" in query:
        return 50.0   # Takes longer
    
    # Option 3: Resource-based cost
    if "llm_call" in query:
        return 200.0  # LLM inference
    
    return 1.0  # Default cheap

# Use in caching
policy.put("expensive_embedding_query", {"cost": calculate_cost(query)})
```

### Cost Priority

```python
# Items prioritized for retention
HIGH_PRIORITY = 200.0    # LLM inference
MEDIUM_PRIORITY = 50.0   # Embeddings, complex queries
LOW_PRIORITY = 1.0       # Simple lookups

policy = CostAwareEvictionPolicy(max_items=1000)

# Under memory pressure, cheap items evicted first
for cost in [HIGH_PRIORITY, MEDIUM_PRIORITY, LOW_PRIORITY, LOW_PRIORITY]:
    policy.put(f"query_{cost}", {"cost": cost})
    
# When memory needed, LOW_PRIORITY items evicted first
```

## Adaptive Policy

### Automatic Behavior Adaptation

```python
from src.cache.advanced_policies import AdaptivePolicy

adaptive = AdaptivePolicy(
    learning_window=1000,  # Learn from 1000 operations
    min_threshold=0.5      # Minimum confidence
)

# Initialize with workload patterns
for i in range(1000):
    # Simulate recurring pattern: queries 1-5 accessed frequently
    query_id = (i % 5) + 1
    adaptive.record_access(f"query_{query_id}")

# Policy adapts based on patterns
# Frequently accessed items retained despite cost
result = adaptive.get("query_1")
```

### Automatic Threshold Adjustment

```python
# Policy learns optimal eviction threshold
adaptive = AdaptivePolicy()

# Under low memory pressure
adaptive.update_memory_pressure(0.2)  # 20% full
# -> Lenient eviction, keep more items

# Under high memory pressure
adaptive.update_memory_pressure(0.9)  # 90% full
# -> Aggressive eviction, keep only essential items

current_threshold = adaptive.get_eviction_threshold()
print(f"Current threshold: {current_threshold:.2f}")
```

## Advanced Caching Policy Manager

### Orchestrating Multiple Policies

```python
from src.cache.advanced_policies import AdvancedCachingPolicyManager

manager = AdvancedCachingPolicyManager(
    max_memory=10000,
    learning_enabled=True,
    cost_aware=True,
    adaptive=True
)

# Manage items with rich metadata
manager.put(
    key="query_1",
    value="result_1",
    cost=100,              # Computation cost
    metadata={"type": "embedding"}
)

# Get with pattern learning
result = manager.get("query_1")

# Query-driven optimization
patterns = manager.get_access_patterns()
most_valuable = manager.get_most_valuable_items(top_k=10)
```

### Cost-Aware Storage

```python
# Store items that are expensive to recompute
expensive_items = [
    ("embedding_query_1", result_1, 100),
    ("embedding_query_2", result_2, 100),
    ("ml_inference_1", result_3, 150),
]

for key, value, cost in expensive_items:
    manager.put(key, value, cost=cost)

# Store cheap items with low priority
cheap_items = [
    ("lookup_1", result_4, 1),
    ("lookup_2", result_5, 1),
]

for key, value, cost in cheap_items:
    manager.put(key, value, cost=cost, priority="low")
```

## Predictive Prefetching

### Sequential Pattern Learning

```python
from src.cache.advanced_policies import PredictivePrefetcher

prefetcher = PredictivePrefetcher(
    window_size=5,  # Look at 5 recent accesses
    confidence_threshold=0.7
)

# Record access sequence
access_sequence = [
    "query_1", "query_2", "query_3",
    "query_1", "query_2", "query_3",
    "query_1", "query_2",
    # Pattern recognized!
]

for query in access_sequence:
    prefetcher.record_access(query)

# Predict next access
next_queries = prefetcher.predict_next(top_k=3)
print(f"Predicted next: {next_queries}")  # ["query_3", "query_1", ...]
```

### Using Predictions

```python
def smart_prefetch(manager, current_query: str):
    """Prefetch likely subsequent queries"""
    prefetcher = PredictivePrefetcher()
    
    # Record access
    prefetcher.record_access(current_query)
    
    # Predict and prefetch
    next_predictions = prefetcher.predict_next(top_k=3)
    
    for predicted_query in next_predictions:
        # Async prefetch for likely next queries
        asyncio.create_task(
            prefetch_query_async(predicted_query)
        )
```

### Pattern Recognition Examples

```python
# Pattern 1: User session flow
# User searches -> clicks result -> reads details -> searches again
pattern_1 = ["search", "click", "read", "search"]

# Pattern 2: Recommendation pipeline
# Get user -> Get history -> Get recommendations -> Cache results
pattern_2 = ["get_user", "get_history", "get_recs", "cache"]

# Pattern 3: Multi-step analysis
# Load data -> Process -> Analyze -> Report
pattern_3 = ["load_data", "process", "analyze", "report"]

prefetcher = PredictivePrefetcher()
for pattern in [pattern_1, pattern_2, pattern_3]:
    for query in pattern:
        prefetcher.record_access(query)
```

## Integration Patterns

### Pattern 1: Smart Cache Manager

```python
class SmartCache:
    def __init__(self):
        self.manager = AdvancedCachingPolicyManager(
            max_memory=10000,
            learning_enabled=True,
            cost_aware=True
        )
        self.analyzer = AccessPatternAnalyzer()
    
    def get_or_compute(self, key: str, compute_fn, cost: float):
        # Check cache
        result = self.manager.get(key)
        
        if result is not None:
            self.analyzer.record_access(key, latency_ms=0, cost=cost)
            return result
        
        # Compute and cache with cost info
        start = time.time()
        result = compute_fn()
        latency = (time.time() - start) * 1000
        
        self.manager.put(key, result, cost=cost)
        self.analyzer.record_access(key, latency_ms=latency, cost=cost)
        
        return result
```

### Pattern 2: Memory-Aware Caching

```python
def adaptive_cache_size(memory_available: float):
    """Adjust cache size based on available memory"""
    if memory_available > 1000:
        return 10000  # Generous cache
    elif memory_available > 500:
        return 5000   # Medium cache
    else:
        return 1000   # Conservative cache

# Use with manager
available_memory = get_system_memory()
manager = AdvancedCachingPolicyManager(
    max_memory=adaptive_cache_size(available_memory),
    adaptive=True  # Enable automatic adjustment
)
```

### Pattern 3: Cost-Benefit Analysis

```python
def should_cache(query: str, cost: float, frequency: int) -> bool:
    """
    Decide whether to cache based on cost-benefit
    
    Benefit = cost * frequency
    Storage overhead < benefit?
    """
    storage_overhead = len(query) * 10  # Estimate
    total_benefit = cost * frequency
    
    return total_benefit > storage_overhead * 2  # 2x factor for safety

# Use in caching
pattern = analyzer.get_pattern("query_1")
cost = calculate_cost("query_1")

if should_cache("query_1", cost, pattern.access_frequency):
    manager.put("query_1", result, cost=cost)
```

## Monitoring & Metrics

```python
# Get detailed analytics
manager = AdvancedCachingPolicyManager(max_memory=10000)

# Simulate workload
for i in range(1000):
    manager.put(f"query_{i%100}", f"result_{i}", cost=float(i%50))
    manager.get(f"query_{i%100}")

# Analyze patterns
patterns = manager.get_access_patterns()
print(f"Learned {len(patterns)} patterns")

# Most valuable items
valuable = manager.get_most_valuable_items(top_k=10)
for item, score in valuable:
    print(f"{item}: {score:.2f}")

# Memory usage
usage = manager.get_memory_usage()
print(f"Memory: {usage['used']}/{usage['max']} bytes")
```

## Configuration Guide

### For High-Latency Queries

```python
# LLM inference, complex ML models
manager = AdvancedCachingPolicyManager(
    max_memory=50000,
    learning_enabled=True,
    cost_aware=True,
    adaptive=True
)

# Prioritize expensive operations
policy = CostAwareEvictionPolicy(max_items=1000)
```

### For Mixed Workloads

```python
# Production systems with varied queries
manager = AdvancedCachingPolicyManager(
    max_memory=10000,
    learning_enabled=True,
    cost_aware=True,
    adaptive=True
)

# Learn patterns and adapt threshold
patterns = manager.get_access_patterns()
manager.optimize_for_workload(patterns)
```

### For Real-Time Systems

```python
# Predictive prefetching for low latency
prefetcher = PredictivePrefetcher(
    window_size=10,
    confidence_threshold=0.8
)

manager = AdvancedCachingPolicyManager(
    max_memory=5000,
    learning_enabled=True,
    adaptive=True,
    prefetcher=prefetcher
)
```

## Testing & Validation

```bash
# Run advanced policy tests
pytest tests/unit/cache/test_phase_1_7_policies.py -v

# Test access pattern analysis
pytest tests/unit/cache/test_phase_1_7_policies.py::TestAccessPatternAnalyzer -v

# Test cost-aware eviction
pytest tests/unit/cache/test_phase_1_7_policies.py::TestCostAwareEvictionPolicy -v

# Test adaptive policy
pytest tests/unit/cache/test_phase_1_7_policies.py::TestAdaptivePolicy -v

# Test manager integration
pytest tests/unit/cache/test_phase_1_7_policies.py::TestAdvancedCachingPolicyManager -v
```

## API Reference

```python
class AccessPatternAnalyzer:
    def record_access(self, key: str, latency_ms: float, cost: float) -> None
    def get_pattern(self, key: str) -> AccessPattern

class CostAwareEvictionPolicy:
    def put(self, key: str, value: Any, cost: float) -> None
    def get(self, key: str) -> Any
    def evict_one(self) -> str

class PredictivePrefetcher:
    def record_access(self, query: str) -> None
    def predict_next(self, top_k: int = 3) -> List[str]

class AdvancedCachingPolicyManager:
    def put(self, key: str, value: Any, cost: float) -> None
    def get(self, key: str) -> Any
    def get_access_patterns(self) -> Dict[str, AccessPattern]
    def get_most_valuable_items(self, top_k: int) -> List[Tuple[str, float]]
```

## Next Steps
- Proceed to [Phase 1.8 Performance Optimization](./PHASE_1_8_PERFORMANCE_USAGE.md)
- See [Architecture Guide](../architecture/PHASE_1_ARCHITECTURE.md)
