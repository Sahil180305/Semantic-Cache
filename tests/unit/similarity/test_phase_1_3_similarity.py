"""
Phase 1.3: Similarity Search Tests

Comprehensive tests for:
- Similarity metrics (cosine, euclidean, inner product, manhattan, chebyshev)
- HNSW indexing and approximate nearest neighbor search
- Similarity search service with caching and metrics
- Query deduplication
- Domain-adaptive thresholds

NOTE: SimilaritySearchService now uses UnifiedIndexManager as the single source of truth.
Tests that need indexing must provide an UnifiedIndexManager instance.
"""

import pytest
import math
from typing import List
from unittest.mock import Mock, MagicMock

from src.similarity.base import (
    SimilarityMetric,
    SimilarityScore,
    SimilaritySearchRequest,
    DomainType,
    DomainThresholdConfig,
    SimilarityAlgorithmFactory,
    CosineSimilarity,
    EuclideanSimilarity,
    InnerProductSimilarity,
    ManhattanSimilarity,
    ChebyshevSimilarity,
)
from src.similarity.index import HNSWIndex
from src.similarity.service import (
    SimilaritySearchService,
    QueryDeduplicator,
    SimilaritySearchMetrics,
)
from src.cache.index_manager import UnifiedIndexManager, IndexConfig
from src.core.exceptions import SimilarityError


# ============================================================================
# Fixtures for UnifiedIndexManager
# ============================================================================

@pytest.fixture
def index_manager():
    """Create a fresh UnifiedIndexManager for testing."""
    # Reset singleton for clean tests
    UnifiedIndexManager.reset_instance()
    config = IndexConfig(dimension=3)
    manager = UnifiedIndexManager.get_instance(config)
    yield manager
    # Cleanup
    UnifiedIndexManager.reset_instance()


@pytest.fixture
def index_manager_2d():
    """Create a fresh UnifiedIndexManager with 2D embeddings."""
    UnifiedIndexManager.reset_instance()
    config = IndexConfig(dimension=2)
    manager = UnifiedIndexManager.get_instance(config)
    yield manager
    UnifiedIndexManager.reset_instance()


# ============================================================================
# Test: Cosine Similarity
# ============================================================================

class TestCosineSimilarity:
    """Test cosine similarity metric."""
    
    def test_identical_vectors(self):
        """Test similarity of identical vectors."""
        metric = CosineSimilarity()
        vec = [1.0, 0.0, 0.0]
        similarity = metric.compute_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)
    
    def test_orthogonal_vectors(self):
        """Test similarity of orthogonal vectors."""
        metric = CosineSimilarity()
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        similarity = metric.compute_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0)
    
    def test_opposite_vectors(self):
        """Test similarity of opposite vectors."""
        metric = CosineSimilarity()
        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        similarity = metric.compute_similarity(vec1, vec2)
        assert similarity == pytest.approx(-1.0)
    
    def test_batch_similarity(self):
        """Test batch similarity computation."""
        metric = CosineSimilarity()
        query = [1.0, 0.0, 0.0]
        candidates = [
            [1.0, 0.0, 0.0],  # 1.0
            [0.707, 0.707, 0.0],  # 0.707
            [0.0, 1.0, 0.0],  # 0.0
        ]
        
        similarities = metric.compute_batch_similarity(query, candidates)
        
        assert len(similarities) == 3
        assert similarities[0] == pytest.approx(1.0)
        assert similarities[1] == pytest.approx(0.707, abs=0.01)
        assert similarities[2] == pytest.approx(0.0)
    
    def test_metric_type(self):
        """Test metric type property."""
        metric = CosineSimilarity()
        assert metric.metric_type == SimilarityMetric.COSINE


# ============================================================================
# Test: Euclidean Similarity
# ============================================================================

class TestEuclideanSimilarity:
    """Test euclidean similarity metric."""
    
    def test_identical_vectors(self):
        """Test euclidean similarity of identical vectors."""
        metric = EuclideanSimilarity()
        vec = [1.0, 2.0, 3.0]
        similarity = metric.compute_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)
    
    def test_distance_based_similarity(self):
        """Test euclidean converts distance to similarity."""
        metric = EuclideanSimilarity()
        vec1 = [0.0, 0.0]
        vec2 = [1.0, 0.0]  # Distance = 1
        similarity = metric.compute_similarity(vec1, vec2)
        # Similarity = 1 / (1 + distance) = 1 / 2 = 0.5
        assert similarity == pytest.approx(0.5)


# ============================================================================
# Test: Inner Product Similarity
# ============================================================================

class TestInnerProductSimilarity:
    """Test inner product similarity metric."""
    
    def test_inner_product_computation(self):
        """Test inner product calculation."""
        metric = InnerProductSimilarity()
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [4.0, 5.0, 6.0]
        similarity = metric.compute_similarity(vec1, vec2)
        # Expected: 1*4 + 2*5 + 3*6 = 4 + 10 + 18 = 32
        assert similarity == pytest.approx(32.0)
    
    def test_metric_type(self):
        """Test metric type."""
        metric = InnerProductSimilarity()
        assert metric.metric_type == SimilarityMetric.INNER_PRODUCT


# ============================================================================
# Test: Manhattan Similarity
# ============================================================================

class TestManhattanSimilarity:
    """Test Manhattan distance metric."""
    
    def test_manhattan_similarity(self):
        """Test Manhattan distance converts to similarity."""
        metric = ManhattanSimilarity()
        vec1 = [0.0, 0.0]
        vec2 = [1.0, 1.0]  # Distance = 2
        similarity = metric.compute_similarity(vec1, vec2)
        # Similarity = 1 / (1 + 2) = 0.333...
        assert similarity == pytest.approx(1.0 / 3.0)


# ============================================================================
# Test: Similarity Algorithm Factory
# ============================================================================

class TestSimilarityAlgorithmFactory:
    """Test factory pattern for similarity algorithms."""
    
    def test_get_cosine_algorithm(self):
        """Test getting cosine similarity algorithm."""
        algo = SimilarityAlgorithmFactory.get_algorithm(SimilarityMetric.COSINE)
        assert isinstance(algo, CosineSimilarity)
    
    def test_get_euclidean_algorithm(self):
        """Test getting euclidean algorithm."""
        algo = SimilarityAlgorithmFactory.get_algorithm(SimilarityMetric.EUCLIDEAN)
        assert isinstance(algo, EuclideanSimilarity)
    
    def test_unknown_metric_raises_error(self):
        """Test that unknown metric raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid SimilarityMetric"):
            SimilarityAlgorithmFactory.get_algorithm(SimilarityMetric("unknown"))


# ============================================================================
# Test: Domain Threshold Configuration
# ============================================================================

class TestDomainThresholdConfig:
    """Test domain-specific threshold configuration."""
    
    def test_default_thresholds(self):
        """Test default thresholds for each domain."""
        config = DomainThresholdConfig()
        
        assert config.get_threshold(DomainType.MEDICAL) == 0.95
        assert config.get_threshold(DomainType.LEGAL) == 0.92
        assert config.get_threshold(DomainType.ECOMMERCE) == 0.80
        assert config.get_threshold(DomainType.GENERAL) == 0.85
    
    def test_custom_thresholds(self):
        """Test setting custom thresholds."""
        config = DomainThresholdConfig(
            overrides={DomainType.MEDICAL: 0.98}
        )
        
        assert config.get_threshold(DomainType.MEDICAL) == 0.98
        assert config.get_threshold(DomainType.LEGAL) == 0.92  # Unchanged
    
    def test_threshold_validation(self):
        """Test that invalid thresholds are rejected."""
        config = DomainThresholdConfig()
        
        with pytest.raises(ValueError, match="between 0 and 1"):
            config.set_threshold(DomainType.MEDICAL, 1.5)
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = DomainThresholdConfig()
        config_dict = config.to_dict()
        
        assert config_dict["medical"] == 0.95
        assert len(config_dict) == 5  # 5 domain types


# ============================================================================
# Test: Query Deduplicator
# ============================================================================

class TestQueryDeduplicator:
    """Test query deduplication."""
    
    def test_duplicate_detection(self):
        """Test detecting duplicate queries."""
        dedup = QueryDeduplicator()
        
        query = "What is machine learning?"
        assert not dedup.is_duplicate(query)
        
        dedup.add_query(query)
        assert dedup.is_duplicate(query)
    
    def test_different_queries(self):
        """Test that different queries are not duplicates."""
        dedup = QueryDeduplicator()
        
        dedup.add_query("Query 1")
        assert not dedup.is_duplicate("Query 2")
    
    def test_dedup_stats(self):
        """Test deduplication statistics."""
        dedup = QueryDeduplicator()
        
        dedup.add_query("Test query")
        _ = dedup.is_duplicate("Test query")
        _ = dedup.is_duplicate("Other query")
        
        stats = dedup.get_stats()
        assert stats["total_checks"] == 2
        assert stats["duplicates_found"] == 1
        assert stats["dedup_rate"] == pytest.approx(0.5)
    
    def test_cache_size_limit(self):
        """Test deduplicator respects cache size limit."""
        dedup = QueryDeduplicator(cache_size=5)
        
        # Add more queries than cache size
        for i in range(10):
            dedup.add_query(f"Query {i}")
        
        # Cache should not exceed max size
        assert len(dedup.query_cache) <= 5


# ============================================================================
# Test: Similarity Search Metrics
# ============================================================================

class TestSimilaritySearchMetrics:
    """Test metrics tracking."""
    
    def test_metrics_initialization(self):
        """Test metrics are initialized correctly."""
        metrics = SimilaritySearchMetrics()
        
        assert metrics.total_searches == 0
        assert metrics.total_candidates_searched == 0
    
    def test_record_search(self):
        """Test recording search metrics."""
        metrics = SimilaritySearchMetrics()
        
        metrics.record_search(
            num_candidates=100,
            num_matches=5,
            search_time_ms=10.5,
            metric=SimilarityMetric.COSINE,
            domain=DomainType.GENERAL,
        )
        
        stats = metrics.get_stats()
        assert stats["total_searches"] == 1
        assert stats["total_candidates"] == 100
        assert stats["total_matches"] == 5
    
    def test_deduplication_tracking(self):
        """Test tracking deduplicated queries."""
        metrics = SimilaritySearchMetrics()
        
        metrics.record_search(
            num_candidates=100,
            num_matches=3,
            search_time_ms=5.0,
            metric=SimilarityMetric.COSINE,
            domain=DomainType.GENERAL,
            is_deduplicated=True,
        )
        
        stats = metrics.get_stats()
        assert stats["queries_deduped"] == 1


# ============================================================================
# Test: HNSW Index
# ============================================================================

class TestHNSWIndex:
    """Test HNSW approximate nearest neighbor indexing."""
    
    def test_index_creation(self):
        """Test creating and inserting into HNSW index."""
        cosine = CosineSimilarity()
        index = HNSWIndex(dimension=3, similarity_algorithm=cosine)
        
        embedding = [0.1, 0.2, 0.3]
        index.insert("item1", embedding, metadata={"name": "Item 1"})
        
        assert "item1" in index.data
        assert index.data["item1"] == embedding
    
    def test_duplicate_insert_raises_error(self):
        """Test that inserting duplicate ID raises error."""
        cosine = CosineSimilarity()
        index = HNSWIndex(dimension=3, similarity_algorithm=cosine)
        
        embedding = [0.1, 0.2, 0.3]
        index.insert("item1", embedding)
        
        with pytest.raises(ValueError, match="already exists"):
            index.insert("item1", embedding)
    
    def test_dimension_validation(self):
        """Test that dimension mismatch raises error."""
        cosine = CosineSimilarity()
        index = HNSWIndex(dimension=3, similarity_algorithm=cosine)
        
        with pytest.raises(ValueError, match="dimension mismatch"):
            index.insert("item1", [0.1, 0.2])  # Only 2 dims
    
    def test_nearest_neighbor_search(self):
        """Test searching for nearest neighbors."""
        cosine = CosineSimilarity()
        index = HNSWIndex(dimension=3, similarity_algorithm=cosine)
        
        # Insert items
        index.insert("item1", [1.0, 0.0, 0.0])
        index.insert("item2", [0.9, 0.1, 0.0])
        index.insert("item3", [0.0, 1.0, 0.0])
        
        # Search for nearest to item1
        query = [1.0, 0.0, 0.0]
        results = index.search(query, k=2)
        
        assert len(results) == 2
        # item1 should be most similar
        assert results[0][0] == "item1"
        assert results[0][1] == pytest.approx(1.0)
    
    def test_index_stats(self):
        """Test index statistics."""
        cosine = CosineSimilarity()
        index = HNSWIndex(dimension=3, similarity_algorithm=cosine)
        
        # Add items
        for i in range(10):
            index.insert(f"item{i}", [float(i)/10, 0.0, 0.0])
        
        stats = index.get_stats()
        assert stats["total_items"] == 10
        assert stats["entry_point"] is not None


# ============================================================================
# Test: Similarity Search Service
# ============================================================================

class TestSimilaritySearchService:
    """Test high-level similarity search service (facade pattern)."""
    
    def test_service_initialization(self, index_manager):
        """Test creating similarity search service with index manager."""
        service = SimilaritySearchService(
            metric=SimilarityMetric.COSINE,
            dimension=3,
            index_manager=index_manager,
        )
        
        assert service.metric == SimilarityMetric.COSINE
        assert service.dimension == 3
        assert service.is_ready
    
    def test_service_without_index_manager(self):
        """Test service is not ready without index manager."""
        service = SimilaritySearchService(
            metric=SimilarityMetric.COSINE,
            dimension=3,
        )
        
        assert not service.is_ready
    
    def test_set_index_manager(self, index_manager):
        """Test setting index manager after initialization."""
        service = SimilaritySearchService(dimension=3)
        assert not service.is_ready
        
        service.set_index_manager(index_manager)
        assert service.is_ready
    
    def test_add_to_index(self, index_manager):
        """Test adding items to search index via UnifiedIndexManager."""
        service = SimilaritySearchService(dimension=3, index_manager=index_manager)
        
        service.add_to_index("query1", [0.1, 0.2, 0.3], metadata={"text": "test"}, query_text="test")
        service.add_to_index("query2", [0.15, 0.25, 0.35], query_text="test2")
        
        assert index_manager.size() == 2
        assert index_manager.contains("query1")
        assert index_manager.contains("query2")
    
    def test_add_to_index_without_manager(self):
        """Test add_to_index fails without index manager."""
        service = SimilaritySearchService(dimension=3)
        
        with pytest.raises(SimilarityError, match="INDEX_NOT_CONFIGURED"):
            service.add_to_index("query1", [0.1, 0.2, 0.3])
    
    def test_dimension_validation(self, index_manager):
        """Test dimension validation in add_to_index."""
        service = SimilaritySearchService(dimension=3, index_manager=index_manager)
        
        with pytest.raises(SimilarityError, match="DIMENSION_MISMATCH"):
            service.add_to_index("query1", [0.1, 0.2])  # Only 2 dims
    
    def test_similarity_search(self, index_manager):
        """Test performing similarity search."""
        service = SimilaritySearchService(
            metric=SimilarityMetric.COSINE,
            dimension=3,
            index_manager=index_manager,
        )
        
        # Index items
        service.add_to_index("item1", [1.0, 0.0, 0.0], query_text="item1")
        service.add_to_index("item2", [0.9, 0.1, 0.0], query_text="item2")
        service.add_to_index("item3", [0.0, 1.0, 0.0], query_text="item3")
        
        # Search
        request = SimilaritySearchRequest(
            query_embedding=[1.0, 0.0, 0.0],
            query_id="q1",
            domain=DomainType.GENERAL,
            top_k=2,
        )
        
        result = service.search(request)
        
        assert result.query_id == "q1"
        assert len(result.matches) <= 2
        if result.matches:
            assert result.matches[0].rank == 1
    
    def test_search_without_manager(self):
        """Test search fails without index manager."""
        service = SimilaritySearchService(dimension=3)
        
        request = SimilaritySearchRequest(
            query_embedding=[1.0, 0.0, 0.0],
            query_id="q1",
        )
        
        with pytest.raises(SimilarityError, match="INDEX_NOT_CONFIGURED"):
            service.search(request)
    
    def test_domain_threshold_application(self, index_manager_2d):
        """Test that domain-specific thresholds are applied."""
        service = SimilaritySearchService(
            metric=SimilarityMetric.COSINE,
            dimension=2,
            index_manager=index_manager_2d,
        )
        
        service.add_to_index("item1", [1.0, 0.0], query_text="item1")
        service.add_to_index("item2", [0.85, 0.1], query_text="item2")  # Lower similarity
        
        # Medical domain requires 0.95
        request = SimilaritySearchRequest(
            query_embedding=[1.0, 0.0],
            query_id="q1",
            domain=DomainType.MEDICAL,
            top_k=10,
        )
        
        result = service.search(request)
        
        # Verify threshold was applied
        assert result.threshold == 0.95
    
    def test_batch_search(self, index_manager_2d):
        """Test batch similarity search."""
        service = SimilaritySearchService(dimension=2, index_manager=index_manager_2d)
        
        # Index items
        for i in range(5):
            service.add_to_index(f"item{i}", [float(i)/5, float(i)/5], query_text=f"item{i}")
        
        # Batch search
        requests = [
            SimilaritySearchRequest(
                query_embedding=[0.5, 0.5],
                query_id=f"q{i}",
            )
            for i in range(3)
        ]
        
        results = service.batch_search(requests)
        
        assert len(results) == 3
    
    def test_query_deduplication(self, index_manager_2d):
        """Test query deduplication in service."""
        service = SimilaritySearchService(
            dimension=2,
            enable_deduplication=True,
            index_manager=index_manager_2d,
        )
        
        service.add_to_index("item1", [0.5, 0.5], query_text="item1")
        
        request = SimilaritySearchRequest(
            query_embedding=[0.5, 0.5],
            query_id="q1",
            query_text="Test query",
        )
        
        # First search should not be deduped
        result1 = service.search(request)
        assert not result1.is_cached
        
        # Register same text for deduplication
        service.deduplicator.add_query("Test query")
        
        # Second search with same text is deduped
        request.query_id = "q2"
        result2 = service.search(request)
        # Deduplication should be flagged in metrics
    
    def test_clear_index(self, index_manager_2d):
        """Test clearing the index."""
        service = SimilaritySearchService(dimension=2, index_manager=index_manager_2d)
        
        service.add_to_index("item1", [0.5, 0.5], query_text="item1")
        service.add_to_index("item2", [0.6, 0.6], query_text="item2")
        
        assert index_manager_2d.size() == 2
        
        service.clear_index()
        
        assert index_manager_2d.size() == 0
    
    def test_get_metrics(self, index_manager_2d):
        """Test retrieving service metrics."""
        service = SimilaritySearchService(dimension=2, index_manager=index_manager_2d)
        
        service.add_to_index("item1", [0.5, 0.5], query_text="item1")
        
        request = SimilaritySearchRequest(
            query_embedding=[0.5, 0.5],
            query_id="q1",
        )
        service.search(request)
        
        metrics = service.get_metrics()
        
        assert "search_metrics" in metrics
        assert "index" in metrics
        assert "index_manager_connected" in metrics
        assert metrics["index_manager_connected"] is True
        assert metrics["search_metrics"]["total_searches"] == 1
    
    def test_contains(self, index_manager):
        """Test checking if item exists."""
        service = SimilaritySearchService(dimension=3, index_manager=index_manager)
        
        assert not service.contains("item1")
        
        service.add_to_index("item1", [0.5, 0.5, 0.5], query_text="item1")
        
        assert service.contains("item1")
        assert not service.contains("item2")
    
    def test_delete_from_index(self, index_manager):
        """Test deleting item from index."""
        service = SimilaritySearchService(dimension=3, index_manager=index_manager)
        
        service.add_to_index("item1", [0.5, 0.5, 0.5], query_text="item1")
        assert service.contains("item1")
        
        result = service.delete_from_index("item1")
        assert result is True
        assert not service.contains("item1")
        
        # Delete non-existent
        result = service.delete_from_index("item999")
        assert result is False


# ============================================================================
# Test: Integration
# ============================================================================

class TestSimilarityIntegration:
    """Integration tests for similarity search with UnifiedIndexManager."""
    
    def test_end_to_end_search(self):
        """Test complete end-to-end similarity search workflow."""
        # Reset and create index manager
        UnifiedIndexManager.reset_instance()
        index_manager = UnifiedIndexManager.get_instance(IndexConfig(dimension=4))
        
        # Create service
        service = SimilaritySearchService(
            metric=SimilarityMetric.COSINE,
            dimension=4,
            enable_deduplication=True,
            index_manager=index_manager,
        )
        
        # Index documents with embeddings
        documents = [
            ("doc1", [1.0, 0.0, 0.0, 0.0], {"text": "Machine learning basics"}),
            ("doc2", [0.95, 0.05, 0.0, 0.0], {"text": "Deep learning introduction"}),
            ("doc3", [0.0, 1.0, 0.0, 0.0], {"text": "Web development"}),
            ("doc4", [0.0, 0.0, 1.0, 0.0], {"text": "Database design"}),
        ]
        
        for doc_id, embedding, metadata in documents:
            service.add_to_index(doc_id, embedding, metadata, query_text=metadata["text"])
        
        # Search for machine learning docs
        request = SimilaritySearchRequest(
            query_embedding=[0.98, 0.02, 0.0, 0.0],
            query_id="search1",
            query_text="What is machine learning?",
            domain=DomainType.GENERAL,
            top_k=2,
        )
        
        result = service.search(request)
        
        # Verify results
        assert len(result.matches) > 0
        assert result.matches[0].candidate_id in ["doc1", "doc2"]
        
        # Get metrics
        metrics = service.get_metrics()
        assert metrics["search_metrics"]["total_searches"] == 1
        
        # Cleanup
        UnifiedIndexManager.reset_instance()
    
    def test_multiple_metrics(self):
        """Test using different similarity metrics."""
        metrics_to_test = [
            SimilarityMetric.COSINE,
            SimilarityMetric.EUCLIDEAN,
            SimilarityMetric.INNER_PRODUCT,
        ]
        
        for metric in metrics_to_test:
            # Reset for each metric test
            UnifiedIndexManager.reset_instance()
            index_manager = UnifiedIndexManager.get_instance(IndexConfig(dimension=2))
            
            service = SimilaritySearchService(metric=metric, dimension=2, index_manager=index_manager)
            service.add_to_index("item1", [0.5, 0.5], query_text="item1")
            service.add_to_index("item2", [0.6, 0.6], query_text="item2")
            
            request = SimilaritySearchRequest(
                query_embedding=[0.5, 0.5],
                query_id="q1",
                metric=metric,
            )
            
            result = service.search(request)
            assert result.matches  # Should have at least one match
        
        # Cleanup
        UnifiedIndexManager.reset_instance()
