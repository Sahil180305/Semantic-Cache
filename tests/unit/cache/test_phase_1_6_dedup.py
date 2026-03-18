"""
Tests for Query Deduplication and Prefix Matching (Phase 1.6)

Comprehensive test suite covering:
- Query normalization
- Duplicate detection (exact, normalized, semantic)
- Prefix matching
- Deduplication metrics
- Real-world scenarios
"""

import pytest
from src.cache.query_dedup import (
    DeduplicationStrategy,
    QueryDeduplicationEngine,
    QueryNormalizer,
    QueryHasher,
    QuerySimilarityMatcher,
    SimilarityMetrics,
    PrefixMatchingEngine,
    DuplicateGroupMetrics,
)


class TestQueryNormalizer:
    """Tests for QueryNormalizer."""
    
    def setup_method(self):
        """Setup for each test."""
        self.normalizer = QueryNormalizer()
    
    def test_normalize_case_insensitive(self):
        """Test that normalization is case-insensitive."""
        assert self.normalizer.normalize("HELLO") == "hello"
        assert self.normalizer.normalize("HeLLo WoRLD") == "hello world"
    
    def test_normalize_whitespace(self):
        """Test that extra whitespace is removed."""
        assert self.normalizer.normalize("hello   world") == "hello world"
        assert self.normalizer.normalize("  hello  ") == "hello"
    
    def test_normalize_punctuation(self):
        """Test that punctuation is removed."""
        assert "?" not in self.normalizer.normalize("What is this?")
        assert "." not in self.normalizer.normalize("Hello world.")
        assert "!" not in self.normalizer.normalize("Amazing!")
    
    def test_normalize_with_tokens_removes_stopwords(self):
        """Test that stop words are removed from tokens."""
        normalized, tokens = self.normalizer.normalize_with_tokens("What is the answer?")
        assert "what" not in tokens  # stop word
        assert "is" not in tokens    # stop word
        assert "the" not in tokens   # stop word
        assert "answer" in tokens    # content word
    
    def test_normalize_with_tokens_filters_short_tokens(self):
        """Test that short tokens (len <= 2) are filtered."""
        normalized, tokens = self.normalizer.normalize_with_tokens("a b cd efgh")
        assert "a" not in tokens     # too short
        assert "b" not in tokens     # too short
        assert "cd" not in tokens    # too short (exactly 2)
        assert "efgh" in tokens      # long enough
    
    def test_normalize_same_after_normalization(self):
        """Test that normalized queries are identical."""
        q1 = "What is MACHINE Learning?"
        q2 = "what is machine learning?"
        assert self.normalizer.normalize(q1) == self.normalizer.normalize(q2)


class TestQueryHasher:
    """Tests for QueryHasher."""
    
    def setup_method(self):
        """Setup for each test."""
        self.hasher = QueryHasher()
        self.normalizer = QueryNormalizer()
    
    def test_hash_exact_consistency(self):
        """Test that exact hash is consistent."""
        query = "What is machine learning?"
        hash1 = self.hasher.hash_exact(query)
        hash2 = self.hasher.hash_exact(query)
        assert hash1 == hash2
    
    def test_hash_exact_different_for_different_queries(self):
        """Test that different queries produce different hashes."""
        hash1 = self.hasher.hash_exact("machine learning")
        hash2 = self.hasher.hash_exact("deep learning")
        assert hash1 != hash2
    
    def test_hash_exact_case_sensitive(self):
        """Test that exact hash is case-sensitive."""
        hash1 = self.hasher.hash_exact("Hello")
        hash2 = self.hasher.hash_exact("hello")
        assert hash1 != hash2
    
    def test_hash_normalized_case_insensitive(self):
        """Test that normalized hash is case-insensitive."""
        hash1 = self.hasher.hash_normalized("Hello World", self.normalizer)
        hash2 = self.hasher.hash_normalized("hello world", self.normalizer)
        assert hash1 == hash2
    
    def test_hash_normalized_ignores_punctuation(self):
        """Test that normalized hash ignores punctuation."""
        hash1 = self.hasher.hash_normalized("Hello, world!", self.normalizer)
        hash2 = self.hasher.hash_normalized("Hello world", self.normalizer)
        assert hash1 == hash2
    
    def test_hash_prefix_consistency(self):
        """Test that prefix hash is consistent."""
        hash1 = self.hasher.hash_prefix("machine learning", prefix_length=10)
        hash2 = self.hasher.hash_prefix("machine learning", prefix_length=10)
        assert hash1 == hash2
    
    def test_hash_prefix_different_lengths(self):
        """Test that different prefix lengths produce different hashes."""
        hash1 = self.hasher.hash_prefix("machine learning", prefix_length=3)
        hash2 = self.hasher.hash_prefix("machine learning", prefix_length=5)
        # They should be different if prefix lengths differ
        # hash1 hashes "mac" and hash2 hashes "machi"
        assert hash1 != hash2


class TestQuerySimilarityMatcher:
    """Tests for QuerySimilarityMatcher."""
    
    def setup_method(self):
        """Setup for each test."""
        self.matcher = QuerySimilarityMatcher()
    
    def test_exact_match_detection(self):
        """Test that exact matches are detected."""
        metrics = self.matcher.compare_queries("hello world", "hello world")
        assert metrics.exact_match
    
    def test_normalized_match_detection(self):
        """Test that normalized matches are detected."""
        metrics = self.matcher.compare_queries("Hello World", "hello world")
        assert not metrics.exact_match  # Not exact
        assert metrics.normalized_match  # But normalized
    
    def test_char_similarity_high_for_similar(self):
        """Test that character similarity is high for similar queries."""
        metrics = self.matcher.compare_queries("machine learning", "machine learnings")
        assert metrics.char_similarity > 0.8
    
    def test_char_similarity_low_for_different(self):
        """Test that character similarity is low for different queries."""
        metrics = self.matcher.compare_queries("machine learning", "dog cat bird")
        assert metrics.char_similarity < 0.3
    
    def test_token_overlap_calculation(self):
        """Test that token overlap is correctly calculated."""
        metrics = self.matcher.compare_queries(
            "machine learning models",
            "machine learning systems"
        )
        # Should have high overlap (machine, learning in common)
        assert metrics.token_overlap > 0.4
    
    def test_find_similar_from_candidates(self):
        """Test finding similar queries from candidates."""
        query = "machine learning"
        candidates = [
            "machine learning",  # exact
            "machine learnings",  # very similar
            "deep learning",     # different
            "cat dog bird",      # very different
        ]
        
        similar = self.matcher.find_similar(query, candidates, threshold=0.7)
        # Should find at least the exact and very similar
        assert len(similar) >= 2
        assert similar[0][0] == "machine learning"  # exact should be first
    
    def test_find_similar_respects_threshold(self):
        """Test that threshold is respected."""
        query = "hello world"
        candidates = ["hello world", "hello world!", "goodbye world"]
        
        # High threshold - should only find exact and near identical
        similar_high = self.matcher.find_similar(query, candidates, threshold=0.98)
        # "hello world!" normalizes to "hello world" so it matches
        assert len(similar_high) >= 1
        
        # Low threshold - should find more
        similar_low = self.matcher.find_similar(query, candidates, threshold=0.5)
        assert len(similar_low) >= 2
    
    def test_similarity_metrics_is_duplicate(self):
        """Test SimilarityMetrics.is_duplicate()."""
        # Exact match
        metrics = SimilarityMetrics(exact_match=True)
        assert metrics.is_duplicate(threshold=0.9)
        
        # Normalized match
        metrics = SimilarityMetrics(normalized_match=True)
        assert metrics.is_duplicate(threshold=0.9)
        
        # High similarity
        metrics = SimilarityMetrics(char_similarity=0.95)
        assert metrics.is_duplicate(threshold=0.85)
        
        # Low similarity
        metrics = SimilarityMetrics(char_similarity=0.5)
        assert not metrics.is_duplicate(threshold=0.85)


class TestQueryDeduplicationEngine:
    """Tests for QueryDeduplicationEngine."""
    
    def test_exact_strategy_detects_exact_duplicates(self):
        """Test EXACT strategy detects exact duplicates."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.EXACT)
        
        query1, dup1 = engine.register_query("hello world")
        assert query1 == "hello world"
        assert not dup1
        
        query2, dup2 = engine.register_query("hello world")
        assert query2 == "hello world"
        assert dup2  # Should be detected as duplicate
    
    def test_exact_strategy_ignores_case_differences(self):
        """Test EXACT strategy is case-sensitive."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.EXACT)
        
        query1, dup1 = engine.register_query("Hello World")
        query2, dup2 = engine.register_query("hello world")
        
        assert not dup1
        assert not dup2  # Different case, so not a duplicate in EXACT mode
    
    def test_normalized_strategy_detects_case_insensitive(self):
        """Test NORMALIZED strategy detects case-insensitive duplicates."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)
        
        query1, dup1 = engine.register_query("Hello World")
        assert not dup1
        
        query2, dup2 = engine.register_query("hello world")
        assert dup2  # Should be detected due to normalization
        assert query2 == "Hello World"  # Returns first canonical version
    
    def test_normalized_strategy_ignores_punctuation(self):
        """Test NORMALIZED strategy ignores punctuation."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)
        
        query1, dup1 = engine.register_query("What is machine learning?")
        query2, dup2 = engine.register_query("What is machine learning")
        
        assert not dup1
        assert dup2
    
    def test_semantic_strategy_detects_similar(self):
        """Test SEMANTIC strategy detects similar queries."""
        engine = QueryDeduplicationEngine(
            strategy=DeduplicationStrategy.SEMANTIC,
            similarity_threshold=0.65  # Lower threshold for token overlap
        )
        
        query1, dup1 = engine.register_query("machine learning models")
        assert not dup1
        
        query2, dup2 = engine.register_query("machine learning systems")
        assert dup2  # Should detect similarity
    
    def test_get_stats(self):
        """Test statistics gathering."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)
        
        engine.register_query("query 1")
        engine.register_query("query 1")  # duplicate
        engine.register_query("query 2")
        
        stats = engine.get_stats()
        assert stats["total_deduplicated"] == 1
        assert stats["unique_queries"] == 2
        assert stats["strategy"] == "normalized"
    
    def test_clear(self):
        """Test clearing deduplication data."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.EXACT)
        
        engine.register_query("hello")
        assert len(engine.exact_hashes) > 0
        
        engine.clear()
        assert len(engine.exact_hashes) == 0
        assert engine.total_dedup_detected == 0


class TestPrefixMatchingEngine:
    """Tests for PrefixMatchingEngine."""
    
    def setup_method(self):
        """Setup for each test."""
        self.engine = PrefixMatchingEngine(min_prefix_length=5)
    
    def test_register_prefix_creates_prefix(self):
        """Test that register_prefix creates a prefix."""
        prefix = self.engine.register_prefix("machine learning")
        assert prefix == "machi"  # 5 char prefix
    
    def test_register_prefix_matches_existing(self):
        """Test that similar queries share prefixes."""
        prefix1 = self.engine.register_prefix("machine learning")
        prefix2 = self.engine.register_prefix("machines and learning")
        
        assert prefix1 == "machi"
        assert prefix2 == "machi"
    
    def test_find_by_prefix_returns_queries(self):
        """Test finding queries by prefix."""
        self.engine.register_prefix("machine learning")
        self.engine.register_prefix("machines and learning")
        
        queries = self.engine.find_by_prefix("machi")
        assert len(queries) == 2
        assert "machine learning" in queries
        assert "machines and learning" in queries
    
    def test_find_by_prefix_nonexistent(self):
        """Test finding nonexistent prefix."""
        queries = self.engine.find_by_prefix("xyz")
        assert queries == []
    
    def test_short_queries_no_prefix(self):
        """Test that short queries don't create prefixes."""
        prefix = self.engine.register_prefix("abc")  # Only 3 chars
        assert prefix == ""
    
    def test_clear(self):
        """Test clearing prefix data."""
        self.engine.register_prefix("machine learning")
        assert len(self.engine.prefix_to_queries) > 0
        
        self.engine.clear()
        assert len(self.engine.prefix_to_queries) == 0


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_dedup_with_prefix_matching(self):
        """Test deduplication integrated with prefix matching."""
        dedup_engine = QueryDeduplicationEngine(
            strategy=DeduplicationStrategy.NORMALIZED,
            similarity_threshold=0.85
        )
        prefix_engine = PrefixMatchingEngine(min_prefix_length=5)
        
        # Register some queries
        queries = [
            "what is machine learning?",
            "what is machine learning",
            "describe machine learning",
            "how to learn deep learning",
        ]
        
        for query in queries:
            dedup_engine.register_query(query)
            prefix_engine.register_prefix(query)
        
        # Should have deduped first two
        stats = dedup_engine.get_stats()
        assert stats["total_deduplicated"] >= 1
        
        # Should have prefix groups
        prefix_groups = prefix_engine.prefix_to_queries
        assert len(prefix_groups) >= 1
    
    def test_multi_level_deduplication(self):
        """Test deduplication at multiple levels."""
        engine = QueryDeduplicationEngine(
            strategy=DeduplicationStrategy.NORMALIZED
        )
        
        # Multiple variations of same query
        queries = [
            "Machine Learning?",
            "machine learning",
            "MACHINE LEARNING!",
        ]
        
        duplicates = 0
        for query in queries:
            _, is_dup = engine.register_query(query)
            if is_dup:
                duplicates += 1
        
        # Should detect at least 2 duplicates
        assert duplicates >= 2
    
    def test_real_world_search_queries(self):
        """Test deduplication on real-world search queries."""
        engine = QueryDeduplicationEngine(
            strategy=DeduplicationStrategy.NORMALIZED,
            similarity_threshold=0.85
        )
        
        search_queries = [
            "best python libraries for data science",
            "best python libraries for data science?",
            "what are the best python libraries for data science",
            "python machine learning libraries",  # different
            "java libraries for data analysis",   # very different
        ]
        
        duplicates = 0
        for query in search_queries:
            _, is_dup = engine.register_query(query)
            if is_dup:
                duplicates += 1
        
        # Should detect at least 1 duplicate (first two normalize to same)
        assert duplicates >= 1


class TestPhase16Metrics:
    """Tests for Phase 1.6 specific requirements."""
    
    def test_query_dedup_reduces_cache_lookups(self):
        """Test that deduplication reduces cache lookups."""
        engine = QueryDeduplicationEngine(strategy=DeduplicationStrategy.NORMALIZED)
        
        # Same query in different cases
        test_queries = [
            "What is machine learning?",
            "what is machine learning",
            "WHAT IS MACHINE LEARNING!",
        ]
        
        unique_queries = set()
        for query in test_queries:
            canonical, _ = engine.register_query(query)
            unique_queries.add(canonical)
        
        # Should reduce 3 queries to 1 canonical
        assert len(unique_queries) == 1
    
    def test_prefix_matching_enables_predictive_caching(self):
        """Test that prefix matching enables pattern discovery."""
        prefix_engine = PrefixMatchingEngine(min_prefix_length=5)
        
        # Related queries with same prefix
        queries = [
            "machine learning basics",
            "machine learning tutorial",
            "machine learning fundamentals",
        ]
        
        for query in queries:
            prefix_engine.register_prefix(query)
        
        machi_group = prefix_engine.find_by_prefix("machi")
        assert len(machi_group) == 3
    
    def test_similarity_threshold_configuration(self):
        """Test that similarity threshold can be configured."""
        engine_strict = QueryDeduplicationEngine(
            strategy=DeduplicationStrategy.SEMANTIC,
            similarity_threshold=0.99  # Very strict
        )
        
        engine_loose = QueryDeduplicationEngine(
            strategy=DeduplicationStrategy.SEMANTIC,
            similarity_threshold=0.50  # Very loose
        )
        
        query1 = "machine learning"
        query2 = "machine learnings"
        
        # Strict should find fewer duplicates
        _, dup_strict = engine_strict.register_query(query1)
        _, dup_strict2 = engine_strict.register_query(query2)
        strict_dups = [dup_strict, dup_strict2].count(True)
        
        # Loose should find more
        _, dup_loose = engine_loose.register_query(query1)
        _, dup_loose2 = engine_loose.register_query(query2)
        loose_dups = [dup_loose, dup_loose2].count(True)
        
        assert loose_dups >= strict_dups


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
