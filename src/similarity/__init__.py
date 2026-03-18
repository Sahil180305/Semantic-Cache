"""
Similarity Search Module

Provides semantic similarity search with:
- Multiple similarity metrics (cosine, euclidean, inner product, manhattan, chebyshev)
- Domain-adaptive thresholds
- HNSW in-memory indexing for fast approximate nearest neighbor search
- Query deduplication
- Result ranking and scoring
- Comprehensive metrics and monitoring

Usage:
    from src.similarity.service import SimilaritySearchService
    from src.similarity.base import SimilarityMetric, DomainType
    
    service = SimilaritySearchService(metric=SimilarityMetric.COSINE, dimension=384)
    
    # Add embeddings to index
    service.add_to_index("query_1", [0.1, 0.2, ...], metadata={...})
    
    # Search for similar embeddings
    request = SimilaritySearchRequest(
        query_embedding=[0.15, 0.18, ...],
        query_id="q1",
        domain=DomainType.GENERAL,
        top_k=10
    )
    result = service.search(request)
    
    for match in result.matches:
        print(f"{match.candidate_id}: {match.similarity:.3f}")
"""

from src.similarity.base import (
    SimilarityMetric,
    SimilarityAlgorithm,
    SimilarityScore,
    SimilaritySearchRequest,
    SimilaritySearchResult,
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

__all__ = [
    "SimilarityMetric",
    "SimilarityAlgorithm",
    "SimilarityScore",
    "SimilaritySearchRequest",
    "SimilaritySearchResult",
    "DomainType",
    "DomainThresholdConfig",
    "SimilarityAlgorithmFactory",
    "CosineSimilarity",
    "EuclideanSimilarity",
    "InnerProductSimilarity",
    "ManhattanSimilarity",
    "ChebyshevSimilarity",
    "HNSWIndex",
    "SimilaritySearchService",
    "QueryDeduplicator",
    "SimilaritySearchMetrics",
]
