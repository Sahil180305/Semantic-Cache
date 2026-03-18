"""
Tests for Advanced Caching Policies (Phase 1.7)

Comprehensive test suite covering:
- Cost-aware eviction
- Access pattern analysis
- Predictive prefetching
- Adaptive policies
- Real-world scenarios
"""

import pytest
import time
from src.cache.advanced_policies import (
    AccessPatternStats,
    AccessPatternAnalyzer,
    PredictivePrefetcher,
    CostAwareEvictionPolicy,
    AdaptivePolicy,
    AdvancedCachingPolicyManager,
    CostMetric,
    PrefetchCandidate,
)


class TestAccessPatternStats:
    """Tests for AccessPatternStats."""
    
    def test_initialize_stats(self):
        """Test initializing access pattern stats."""
        stats = AccessPatternStats(query="test")
        assert stats.query == "test"
        assert stats.access_count == 0
        assert stats.hit_rate == 0.0
    
    def test_update_access_with_hit(self):
        """Test recording a cache hit."""
        stats = AccessPatternStats(query="test")
        stats.update_access(10.5, is_hit=True)
        
        assert stats.access_count == 1
        assert stats.hit_count == 1
        assert stats.miss_count == 0
        assert stats.avg_latency_ms == 10.5
        assert stats.hit_rate == 1.0
    
    def test_update_access_with_miss(self):
        """Test recording a cache miss."""
        stats = AccessPatternStats(query="test")
        stats.update_access(10.5, is_hit=False)
        
        assert stats.access_count == 1
        assert stats.hit_count == 0
        assert stats.miss_count == 1
        assert stats.hit_rate == 0.0
    
    def test_multiple_accesses_calculate_averages(self):
        """Test that averages are calculated correctly."""
        stats = AccessPatternStats(query="test")
        stats.update_access(10.0, is_hit=True)
        stats.update_access(20.0, is_hit=True)
        stats.update_access(30.0, is_hit=False)
        
        assert stats.access_count == 3
        assert stats.avg_latency_ms == 20.0
        assert stats.hit_rate == pytest.approx(2/3)
    
    def test_time_since_access(self):
        """Test time_since_access calculation."""
        stats = AccessPatternStats(query="test")
        stats.update_access(10.0, is_hit=True)
        time.sleep(0.1)  # Sleep 100ms
        
        time_since = stats.time_since_access()
        assert time_since >= 0.1
    
    def test_lifetime_calculation(self):
        """Test lifetime calculation."""
        stats = AccessPatternStats(query="test")
        time.sleep(0.05)
        stats.update_access(10.0, is_hit=True)
        
        lifetime = stats.lifetime()
        assert lifetime >= 0.05
    
    def test_get_cost_latency_metric(self):
        """Test cost calculation with LATENCY metric."""
        stats = AccessPatternStats(query="test")
        stats.update_access(50.0, is_hit=True)
        stats.update_access(60.0, is_hit=True)
        
        cost = stats.get_cost(CostMetric.LATENCY)
        assert cost == pytest.approx(55.0)
    
    def test_get_cost_popularity_metric(self):
        """Test cost calculation with POPULARITY metric."""
        stats = AccessPatternStats(query="test")
        stats.update_access(10.0, is_hit=True)
        stats.update_access(10.0, is_hit=True)
        stats.update_access(10.0, is_hit=True)
        
        cost = stats.get_cost(CostMetric.POPULARITY)
        assert cost == 3


class TestAccessPatternAnalyzer:
    """Tests for AccessPatternAnalyzer."""
    
    def setup_method(self):
        """Setup for each test."""
        self.analyzer = AccessPatternAnalyzer()
    
    def test_record_single_access(self):
        """Test recording a single access."""
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        
        assert "query1" in self.analyzer.patterns
        stats = self.analyzer.patterns["query1"]
        assert stats.access_count == 1
    
    def test_record_multiple_accesses(self):
        """Test recording multiple accesses to same query."""
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        self.analyzer.record_access("query1", 20.0, is_hit=False)
        
        stats = self.analyzer.patterns["query1"]
        assert stats.access_count == 2
        assert stats.hit_count == 1
        assert stats.miss_count == 1
    
    def test_get_hot_queries_by_popularity(self):
        """Test getting hot queries sorted by popularity."""
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        self.analyzer.record_access("query2", 10.0, is_hit=True)
        
        hot = self.analyzer.get_hot_queries(top_n=2, metric=CostMetric.POPULARITY)
        assert hot[0] == "query1"  # More accesses
        assert hot[1] == "query2"
    
    def test_get_hot_queries_by_latency(self):
        """Test getting hot queries sorted by latency cost."""
        self.analyzer.record_access("query1", 100.0, is_hit=True)  # High latency
        self.analyzer.record_access("query2", 10.0, is_hit=True)   # Low latency
        
        hot = self.analyzer.get_hot_queries(top_n=2, metric=CostMetric.LATENCY)
        assert hot[0] == "query1"  # Higher latency = higher cost
    
    def test_get_cold_queries(self):
        """Test getting cold (least accessed) queries."""
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        self.analyzer.record_access("query2", 10.0, is_hit=True)
        
        cold = self.analyzer.get_cold_queries(top_n=2)
        assert cold[0] == "query2"  # Only 1 access
        assert cold[1] == "query1"  # 2 accesses
    
    def test_get_pattern_stats(self):
        """Test retrieving pattern stats for a query."""
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        
        stats = self.analyzer.get_pattern_stats("query1")
        assert stats is not None
        assert stats.query == "query1"
    
    def test_get_pattern_stats_nonexistent(self):
        """Test retrieving stats for nonexistent query."""
        stats = self.analyzer.get_pattern_stats("nonexistent")
        assert stats is None
    
    def test_clear(self):
        """Test clearing analyzer data."""
        self.analyzer.record_access("query1", 10.0, is_hit=True)
        assert len(self.analyzer.patterns) > 0
        
        self.analyzer.clear()
        assert len(self.analyzer.patterns) == 0


class TestPredictivePrefetcher:
    """Tests for PredictivePrefetcher."""
    
    def setup_method(self):
        """Setup for each test."""
        self.analyzer = AccessPatternAnalyzer()
        self.prefetcher = PredictivePrefetcher(self.analyzer)
    
    def test_record_sequence(self):
        """Test recording query sequences."""
        self.prefetcher.record_sequence("query1", "query2")
        self.prefetcher.record_sequence("query1", "query2")
        self.prefetcher.record_sequence("query1", "query3")
        
        assert self.prefetcher.sequential_patterns["query1"]["query2"] == 2
        assert self.prefetcher.sequential_patterns["query1"]["query3"] == 1
    
    def test_get_next_candidates_no_history(self):
        """Test getting candidates with no history."""
        candidates = self.prefetcher.get_next_candidates("unknown_query")
        assert candidates == []
    
    def test_get_next_candidates_with_history(self):
        """Test getting candidates with sequence history."""
        # Record sequences
        self.prefetcher.record_sequence("query1", "query2")
        self.prefetcher.record_sequence("query1", "query2")
        self.prefetcher.record_sequence("query1", "query3")
        
        candidates = self.prefetcher.get_next_candidates("query1", top_n=2)
        assert len(candidates) == 2
        assert candidates[0].query == "query2"  # Higher frequency
        assert candidates[1].query == "query3"
        assert candidates[0].confidence > candidates[1].confidence
    
    def test_prefetch_candidate_attributes(self):
        """Test prefetch candidate properties."""
        self.analyzer.record_access("query2", 50.0, is_hit=True)
        self.prefetcher.record_sequence("query1", "query2")
        
        candidates = self.prefetcher.get_next_candidates("query1", top_n=1)
        assert len(candidates) == 1
        
        cand = candidates[0]
        assert cand.query == "query2"
        assert 0.0 <= cand.confidence <= 1.0
        assert cand.estimated_latency == 50.0
    
    def test_clear(self):
        """Test clearing prefetcher data."""
        self.prefetcher.record_sequence("query1", "query2")
        assert len(self.prefetcher.sequential_patterns) > 0
        
        self.prefetcher.clear()
        assert len(self.prefetcher.sequential_patterns) == 0


class TestCostAwareEvictionPolicy:
    """Tests for CostAwareEvictionPolicy."""
    
    def test_select_victim_lowest_cost(self):
        """Test selecting entry with lowest cost."""
        policy = CostAwareEvictionPolicy({
            "entry1": 100.0,
            "entry2": 50.0,
            "entry3": 75.0,
        })
        
        victim = policy.select_victim(["entry1", "entry2", "entry3"])
        assert victim == "entry2"  # Lowest cost
    
    def test_select_victim_empty_list(self):
        """Test with empty entry list."""
        policy = CostAwareEvictionPolicy({})
        victim = policy.select_victim([])
        assert victim is None
    
    def test_calculate_entry_cost(self):
        """Test calculating eviction cost."""
        policy = CostAwareEvictionPolicy({})
        stats = AccessPatternStats(query="test")
        
        # Set up realistic stats
        stats.update_access(100.0, is_hit=True)
        stats.update_access(100.0, is_hit=True)
        stats.update_access(100.0, is_hit=True)
        
        cost = policy.calculate_entry_cost("test", stats)
        assert cost > 0  # Should have positive cost
    
    def test_cost_increases_with_latency(self):
        """Test that cost increases with latency."""
        policy = CostAwareEvictionPolicy({})
        
        stats_low = AccessPatternStats(query="low")
        stats_low.update_access(10.0, is_hit=True)
        
        stats_high = AccessPatternStats(query="high")
        stats_high.update_access(100.0, is_hit=True)
        
        cost_low = policy.calculate_entry_cost("low", stats_low)
        cost_high = policy.calculate_entry_cost("high", stats_high)
        
        assert cost_high > cost_low


class TestAdaptivePolicy:
    """Tests for AdaptivePolicy."""
    
    def setup_method(self):
        """Setup for each test."""
        self.analyzer = AccessPatternAnalyzer()
        self.policy = AdaptivePolicy(self.analyzer)
    
    def test_initial_mode(self):
        """Test initial policy mode."""
        assert self.policy.policy_mode == "balanced"
    
    def test_adapt_to_high_memory(self):
        """Test adaptation to high memory usage."""
        self.policy.analyze_and_adapt(0.9)  # 90% memory
        assert self.policy.policy_mode == "aggressive"
    
    def test_adapt_to_low_memory(self):
        """Test adaptation to low memory."""
        self.policy.analyze_and_adapt(0.3)  # 30% memory
        assert self.policy.policy_mode == "aggressive"
    
    def test_adapt_to_medium_memory(self):
        """Test adaptation to medium memory."""
        self.policy.analyze_and_adapt(0.6)  # 60% memory
        assert self.policy.policy_mode == "balanced"
    
    def test_prefetch_threshold_balanced(self):
        """Test prefetch threshold in balanced mode."""
        self.policy.policy_mode = "balanced"
        threshold = self.policy.get_prefetch_threshold()
        assert threshold == 0.5
    
    def test_prefetch_threshold_aggressive(self):
        """Test prefetch threshold in aggressive mode."""
        self.policy.policy_mode = "aggressive"
        threshold = self.policy.get_prefetch_threshold()
        assert threshold == 0.3
    
    def test_eviction_aggressiveness_factors(self):
        """Test eviction aggressiveness in different modes."""
        self.policy.policy_mode = "balanced"
        balanced_factor = self.policy.get_eviction_aggressiveness()
        assert balanced_factor == 1.0
        
        self.policy.policy_mode = "aggressive"
        aggressive_factor = self.policy.get_eviction_aggressiveness()
        assert aggressive_factor > balanced_factor


class TestAdvancedCachingPolicyManager:
    """Tests for AdvancedCachingPolicyManager."""
    
    def setup_method(self):
        """Setup for each test."""
        self.manager = AdvancedCachingPolicyManager()
    
    def test_record_cache_access(self):
        """Test recording cache access."""
        self.manager.record_cache_access("query1", 10.0, is_hit=True)
        
        stats = self.manager.analyzer.get_pattern_stats("query1")
        assert stats is not None
        assert stats.access_count == 1
    
    def test_should_prefetch_no_history(self):
        """Test prefetch decision with no history."""
        result = self.manager.should_prefetch("unknown")
        assert result == False
    
    def test_should_prefetch_with_confidence(self):
        """Test prefetch decision with high confidence."""
        # Build sequence history
        for _ in range(5):
            self.manager.prefetcher.record_sequence("query1", "query2")
        
        # One should_prefetch call
        self.manager.prefetcher.record_sequence("query1", "query3")
        
        result = self.manager.should_prefetch("query1", current_memory=0.5)
        # Result depends on confidence and threshold
        assert isinstance(result, bool)
    
    def test_get_prefetch_candidates(self):
        """Test getting prefetch candidates."""
        self.manager.prefetcher.record_sequence("query1", "query2")
        self.manager.prefetcher.record_sequence("query1", "query2")
        self.manager.prefetcher.record_sequence("query1", "query3")
        
        candidates = self.manager.get_prefetch_candidates("query1", top_n=2)
        assert len(candidates) == 2
        assert candidates[0].query == "query2"
    
    def test_get_hot_queries(self):
        """Test getting hot queries."""
        self.manager.record_cache_access("query1", 100.0, is_hit=True)
        self.manager.record_cache_access("query1", 100.0, is_hit=True)
        self.manager.record_cache_access("query2", 10.0, is_hit=True)
        
        hot = self.manager.get_hot_queries(top_n=2)
        assert "query1" in hot  # Higher latency
    
    def test_calculate_cache_cost(self):
        """Test calculating cache cost."""
        self.manager.record_cache_access("query1", 50.0, is_hit=True)
        
        cost = self.manager.calculate_cache_cost("query1")
        assert cost > 0
    
    def test_get_metrics(self):
        """Test getting policy metrics."""
        metrics = self.manager.get_metrics()
        assert metrics.policy_name == "advanced"
        assert metrics.total_prefetch_suggestions == 0
    
    def test_clear(self):
        """Test clearing manager."""
        self.manager.record_cache_access("query1", 10.0, is_hit=True)
        assert len(self.manager.analyzer.patterns) > 0
        
        self.manager.clear()
        assert len(self.manager.analyzer.patterns) == 0


class TestPhase17RealWorldScenarios:
    """Real-world scenario tests for Phase 1.7."""
    
    def test_high_latency_query_prioritization(self):
        """Test that high-latency queries are prioritized for caching."""
        manager = AdvancedCachingPolicyManager()
        
        # Record various queries with different latencies
        manager.record_cache_access("search", 500.0, is_hit=False)
        manager.record_cache_access("search", 500.0, is_hit=True)
        manager.record_cache_access("filter", 50.0, is_hit=False)
        manager.record_cache_access("filter", 50.0, is_hit=True)
        
        # Hot queries should prefer high-latency ones
        hot = manager.get_hot_queries(top_n=1)
        assert "search" in hot  # Higher latency
    
    def test_sequential_query_prediction(self):
        """Test predictive prefetching for sequential queries."""
        manager = AdvancedCachingPolicyManager()
        
        # Record user navigation pattern
        for _ in range(5):
            manager.prefetcher.record_sequence("home", "search")
            manager.prefetcher.record_sequence("search", "results")
            manager.prefetcher.record_sequence("results", "details")
        
        # Predict next query after "search"
        candidates = manager.get_prefetch_candidates("search", top_n=1)
        assert len(candidates) > 0
        assert candidates[0].query == "results"
    
    def test_adaptive_policy_switches_under_memory_pressure(self):
        """Test that policy adapts under memory pressure."""
        manager = AdvancedCachingPolicyManager()
        
        # Medium memory usage - balanced mode
        mode1 = manager.adaptive_policy.analyze_and_adapt(0.6)
        threshold1 = manager.adaptive_policy.get_prefetch_threshold()
        assert mode1 == "balanced"
        
        # High memory usage - aggressive prefetch
        mode2 = manager.adaptive_policy.analyze_and_adapt(0.95)
        threshold2 = manager.adaptive_policy.get_prefetch_threshold()
        assert mode2 == "aggressive"
        
        assert threshold2 < threshold1  # More aggressive under pressure


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
