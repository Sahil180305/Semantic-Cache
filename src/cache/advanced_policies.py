"""
Advanced Caching Policies (Phase 1.7)

Implements intelligent caching policies including:
- Cost-aware eviction based on latency/response time
- Access pattern analysis
- Predictive prefetching
- Adaptive policies
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional, Callable
from collections import defaultdict


logger = logging.getLogger(__name__)


class CostMetric(Enum):
    """Cost metrics for caching decisions."""
    LATENCY = "latency"  # Response time cost
    COMPUTATION = "computation"  # CPU cost
    MEMORY = "memory"  # Memory footprint
    POPULARITY = "popularity"  # Access frequency
    RECENCY = "recency"  # How recently accessed


@dataclass
class AccessPatternStats:
    """Statistics about query access patterns."""
    
    query: str
    access_count: int = 0
    total_latency_ms: float = 0.0
    hit_count: int = 0
    miss_count: int = 0
    first_access_time: float = field(default_factory=time.time)
    last_access_time: float = field(default_factory=time.time)
    avg_latency_ms: float = 0.0
    hit_rate: float = 0.0
    
    def update_access(self, latency_ms: float, is_hit: bool = True) -> None:
        """Update access statistics.
        
        Args:
            latency_ms: Latency in milliseconds
            is_hit: Whether this was a cache hit
        """
        self.access_count += 1
        self.total_latency_ms += latency_ms
        self.last_access_time = time.time()
        
        if is_hit:
            self.hit_count += 1
        else:
            self.miss_count += 1
        
        # Recalculate averages
        self.avg_latency_ms = self.total_latency_ms / self.access_count
        total = self.hit_count + self.miss_count
        self.hit_rate = self.hit_count / total if total > 0 else 0.0
    
    def time_since_access(self) -> float:
        """Get seconds since last access.
        
        Returns:
            Seconds since last access
        """
        return time.time() - self.last_access_time
    
    def lifetime(self) -> float:
        """Get total lifetime in seconds.
        
        Returns:
            Seconds since first access
        """
        return time.time() - self.first_access_time
    
    def get_cost(self, metric: CostMetric) -> float:
        """Calculate cost for this query based on metric.
        
        Args:
            metric: Cost metric to use
            
        Returns:
            Cost value (higher = more valuable to cache)
        """
        if metric == CostMetric.LATENCY:
            # High latency = high cost = worth caching
            return self.avg_latency_ms
        elif metric == CostMetric.POPULARITY:
            # High frequency = worth caching
            return self.access_count
        elif metric == CostMetric.RECENCY:
            # Recently accessed = score inversely
            return 1.0 / (1.0 + self.time_since_access())
        else:
            return 0.0


class AccessPatternAnalyzer:
    """Analyzes query access patterns for intelligent caching."""
    
    def __init__(self):
        """Initialize pattern analyzer."""
        self.patterns: Dict[str, AccessPatternStats] = {}
        self.access_sequences: List[Tuple[str, float]] = []  # (query, timestamp)
    
    def record_access(self, query: str, latency_ms: float, is_hit: bool = True) -> None:
        """Record a query access.
        
        Args:
            query: Query text
            latency_ms: Response latency in milliseconds
            is_hit: Whether this was a cache hit
        """
        if query not in self.patterns:
            self.patterns[query] = AccessPatternStats(query=query)
        
        self.patterns[query].update_access(latency_ms, is_hit)
        self.access_sequences.append((query, time.time()))
    
    def get_hot_queries(self, top_n: int = 10, metric: CostMetric = CostMetric.POPULARITY) -> List[str]:
        """Get hottest (most valuable) queries.
        
        Args:
            top_n: Number of top queries to return
            metric: Cost metric to use for ranking
            
        Returns:
            List of hot queries sorted by cost
        """
        if not self.patterns:
            return []
        
        # Score all patterns
        scored = [
            (query, stats.get_cost(metric))
            for query, stats in self.patterns.items()
        ]
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [query for query, _ in scored[:top_n]]
    
    def get_cold_queries(self, top_n: int = 10) -> List[str]:
        """Get coldest (least valuable) queries.
        
        Args:
            top_n: Number of cold queries to return
            
        Returns:
            List of cold queries sorted by access count (ascending)
        """
        if not self.patterns:
            return []
        
        sorted_queries = sorted(
            self.patterns.items(),
            key=lambda x: x[1].access_count
        )
        
        return [query for query, _ in sorted_queries[:top_n]]
    
    def get_pattern_stats(self, query: str) -> Optional[AccessPatternStats]:
        """Get statistics for a query.
        
        Args:
            query: Query text
            
        Returns:
            AccessPatternStats or None if not found
        """
        return self.patterns.get(query)
    
    def get_all_stats(self) -> Dict[str, AccessPatternStats]:
        """Get all pattern statistics.
        
        Returns:
            Dictionary of all patterns
        """
        return dict(self.patterns)
    
    def clear(self) -> None:
        """Clear all tracking data."""
        self.patterns.clear()
        self.access_sequences.clear()


@dataclass
class PrefetchCandidate:
    """Candidate for prefetching."""
    
    query: str
    confidence: float  # 0.0 to 1.0
    estimated_latency: float
    reason: str


class PredictivePrefetcher:
    """Predicts and prefetches likely future queries."""
    
    def __init__(self, analyzer: AccessPatternAnalyzer, window_size: int = 5):
        """Initialize prefetcher.
        
        Args:
            analyzer: AccessPatternAnalyzer to use
            window_size: Size of access history window
        """
        self.analyzer = analyzer
        self.window_size = window_size
        self.sequential_patterns: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    def record_sequence(self, prev_query: Optional[str], current_query: str) -> None:
        """Record a sequence of queries for pattern learning.
        
        Args:
            prev_query: Previous query (or None if first)
            current_query: Current query
        """
        if prev_query:
            self.sequential_patterns[prev_query][current_query] += 1
    
    def get_next_candidates(self, current_query: str, top_n: int = 5) -> List[PrefetchCandidate]:
        """Get predicted next queries.
        
        Args:
            current_query: Current query just executed
            top_n: Number of candidates to return
            
        Returns:
            List of prefetch candidates with confidence
        """
        if current_query not in self.sequential_patterns:
            return []
        
        next_queries = self.sequential_patterns[current_query]
        total = sum(next_queries.values())
        
        candidates = []
        for query, count in next_queries.items():
            confidence = count / total  # Probability
            stats = self.analyzer.get_pattern_stats(query)
            estimated_latency = stats.avg_latency_ms if stats else 0.0
            
            candidate = PrefetchCandidate(
                query=query,
                confidence=confidence,
                estimated_latency=estimated_latency,
                reason=f"Sequential pattern ({count} times)"
            )
            candidates.append(candidate)
        
        # Sort by confidence descending
        candidates.sort(key=lambda x: x.confidence, reverse=True)
        return candidates[:top_n]
    
    def clear(self) -> None:
        """Clear pattern data."""
        self.sequential_patterns.clear()


class CostAwareEvictionPolicy:
    """Eviction policy based on cache cost/benefit analysis."""
    
    def __init__(self, metrics: Dict[str, float]):
        """Initialize policy.
        
        Args:
            metrics: Dictionary of entry_key -> cost_score
        """
        self.metrics = metrics
    
    def select_victim(self, entries: List[str]) -> Optional[str]:
        """Select entry to evict based on cost.
        
        Evicts the entry with lowest cost (least valuable to keep).
        
        Args:
            entries: List of entry keys to choose from
            
        Returns:
            Entry key to evict, or None if no good candidates
        """
        if not entries:
            return None
        
        # Find entry with minimum cost
        min_cost_entry = None
        min_cost = float('inf')
        
        for entry in entries:
            cost = self.metrics.get(entry, 0.0)
            if cost < min_cost:
                min_cost = cost
                min_cost_entry = entry
        
        return min_cost_entry
    
    def calculate_entry_cost(self, query: str, stats: AccessPatternStats) -> float:
        """Calculate eviction cost for an entry.
        
        Higher cost = higher priority to keep.
        
        Args:
            query: Query text
            stats: Access statistics
            
        Returns:
            Cost score
        """
        # Combine multiple factors
        factors = {
            'latency': stats.avg_latency_ms,        # High latency = high value
            'frequency': stats.access_count,        # Frequent = high value
            'recency': 1.0 / (1.0 + stats.time_since_access()),  # Recently used = high value
            'hit_rate': stats.hit_rate * 100,      # High hit rate = high value
        }
        
        # Weighted combination
        weights = {'latency': 0.4, 'frequency': 0.3, 'recency': 0.2, 'hit_rate': 0.1}
        
        cost = sum(factors[key] * weights[key] for key in factors)
        return cost


class AdaptivePolicy:
    """Dynamically adapts caching policy based on system state."""
    
    def __init__(self, analyzer: AccessPatternAnalyzer):
        """Initialize adaptive policy.
        
        Args:
            analyzer: AccessPatternAnalyzer to monitor
        """
        self.analyzer = analyzer
        self.memory_threshold = 0.8  # Switch behavior at 80% memory
        self.policy_mode = "balanced"  # "balanced", "aggressive", "conservative"
    
    def analyze_and_adapt(self, current_memory_usage: float) -> str:
        """Analyze system state and adapt policy.
        
        Args:
            current_memory_usage: Current memory usage ratio (0.0-1.0)
            
        Returns:
            New policy mode
        """
        if current_memory_usage > self.memory_threshold:
            self.policy_mode = "aggressive"
        elif current_memory_usage < 0.5:
            self.policy_mode = "aggressive"  # More aggressive prefetch
        else:
            self.policy_mode = "balanced"
        
        return self.policy_mode
    
    def get_prefetch_threshold(self) -> float:
        """Get confidence threshold for prefetching.
        
        Returns:
            Confidence threshold (0.0-1.0)
        """
        thresholds = {
            "balanced": 0.5,
            "aggressive": 0.3,
            "conservative": 0.7,
        }
        return thresholds.get(self.policy_mode, 0.5)
    
    def get_eviction_aggressiveness(self) -> float:
        """Get eviction aggressiveness factor.
        
        Returns:
            Aggressiveness (1.0 = normal, >1.0 = more aggressive)
        """
        factors = {
            "balanced": 1.0,
            "aggressive": 1.5,
            "conservative": 0.5,
        }
        return factors.get(self.policy_mode, 1.0)


@dataclass
class PolicyMetrics:
    """Metrics for policy effectiveness."""
    
    policy_name: str
    total_prefetch_suggestions: int = 0
    successful_prefetches: int = 0
    failed_prefetches: int = 0
    cost_based_evictions: int = 0
    cost_reduction_percent: float = 0.0  # % improvement vs simple LRU
    
    def prefetch_accuracy(self) -> float:
        """Calculate prefetch accuracy.
        
        Returns:
            Ratio of successful to total prefetches
        """
        total = self.total_prefetch_suggestions
        if total == 0:
            return 0.0
        return self.successful_prefetches / total


class AdvancedCachingPolicyManager:
    """Manages all advanced caching policies."""
    
    def __init__(self):
        """Initialize policy manager."""
        self.analyzer = AccessPatternAnalyzer()
        self.prefetcher = PredictivePrefetcher(self.analyzer)
        self.adaptive_policy = AdaptivePolicy(self.analyzer)
        self.metrics = PolicyMetrics(policy_name="advanced")
    
    def record_cache_access(self, query: str, latency_ms: float, is_hit: bool) -> None:
        """Record cache access for analysis.
        
        Args:
            query: Query text
            latency_ms: Access latency in milliseconds
            is_hit: Whether it was a cache hit
        """
        self.analyzer.record_access(query, latency_ms, is_hit)
    
    def should_prefetch(self, query: str, current_memory: float = 0.5) -> bool:
        """Determine if prefetching should occur.
        
        Args:
            query: Current query
            current_memory: Current memory usage (0.0-1.0)
            
        Returns:
            Whether prefetching is recommended
        """
        self.adaptive_policy.analyze_and_adapt(current_memory)
        threshold = self.adaptive_policy.get_prefetch_threshold()
        
        candidates = self.prefetcher.get_next_candidates(query, top_n=1)
        if candidates and candidates[0].confidence >= threshold:
            return True
        
        return False
    
    def get_prefetch_candidates(self, query: str, top_n: int = 5) -> List[PrefetchCandidate]:
        """Get queries to prefetch next.
        
        Args:
            query: Current query
            top_n: Number of candidates
            
        Returns:
            List of prefetch candidates
        """
        self.metrics.total_prefetch_suggestions += 1
        return self.prefetcher.get_next_candidates(query, top_n)
    
    def get_hot_queries(self, top_n: int = 10) -> List[str]:
        """Get most valuable queries to keep cached.
        
        Args:
            top_n: Number of results
            
        Returns:
            List of hot queries
        """
        return self.analyzer.get_hot_queries(top_n, CostMetric.LATENCY)
    
    def calculate_cache_cost(self, query: str) -> float:
        """Calculate eviction cost for a query.
        
        Args:
            query: Query text
            
        Returns:
            Cost score
        """
        stats = self.analyzer.get_pattern_stats(query)
        if not stats:
            return 0.0
        
        policy = CostAwareEvictionPolicy({})
        return policy.calculate_entry_cost(query, stats)
    
    def get_metrics(self) -> PolicyMetrics:
        """Get policy metrics.
        
        Returns:
            Current metrics
        """
        return self.metrics
    
    def clear(self) -> None:
        """Clear all data."""
        self.analyzer.clear()
        self.prefetcher.clear()
        self.metrics = PolicyMetrics(policy_name="advanced")
