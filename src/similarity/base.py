"""
Similarity Search Abstraction Layer

Defines interfaces for:
- Similarity metrics (cosine, euclidean, inner product, manhattan, etc.)
- Similarity search algorithms
- Index management
- Domain-adaptive threshold configuration
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
import math


class SimilarityMetric(str, Enum):
    """Supported similarity metrics."""
    COSINE = "cosine"              # Most common for embeddings, range [-1, 1]
    EUCLIDEAN = "euclidean"        # L2 distance, lower is more similar
    INNER_PRODUCT = "inner_product" # Dot product, range [-inf, inf]
    MANHATTAN = "manhattan"        # L1 distance
    CHEBYSHEV = "chebyshev"        # L-infinity distance


class DomainType(str, Enum):
    """Supported domain types with predefined thresholds."""
    MEDICAL = "medical"            # Requires high precision, threshold 0.95
    LEGAL = "legal"                # Requires high precision, threshold 0.92
    FINANCIAL = "financial"        # Balanced precision/recall, threshold 0.90
    ECOMMERCE = "ecommerce"        # Lenient matching, threshold 0.80
    GENERAL = "general"            # Default, threshold 0.85


@dataclass
class SimilarityScore:
    """Represents a similarity search result."""
    
    query_id: str
    candidate_id: str
    similarity: float  # Similarity score (0-1 for cosine, varies for others)
    metric: SimilarityMetric
    is_match: bool  # Whether score exceeds threshold
    threshold_used: float
    rank: int  # Rank among results (1-based)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SimilaritySearchRequest:
    """Request for similarity search."""
    
    query_embedding: List[float]  # Query vector
    query_id: str  # Unique identifier for query
    query_text: Optional[str] = None  # Optional original text
    metric: SimilarityMetric = SimilarityMetric.COSINE
    threshold: Optional[float] = None  # If None, use domain default
    domain: DomainType = DomainType.GENERAL
    top_k: int = 10  # Return top-k results
    min_score: float = 0.0  # Minimum score threshold
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SimilaritySearchResult:
    """Result of similarity search."""
    
    query_id: str
    matches: List[SimilarityScore]  # Ranked matches
    total_candidates: int  # Total candidates searched
    search_time_ms: float
    metric: SimilarityMetric
    threshold: float
    is_cached: bool = False


class SimilarityAlgorithm(ABC):
    """Abstract base class for similarity metrics."""
    
    @property
    @abstractmethod
    def metric_type(self) -> SimilarityMetric:
        """Return the metric type."""
        pass
    
    @abstractmethod
    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score
        """
        pass
    
    @abstractmethod
    def compute_batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """
        Compute similarity between query and multiple candidates.
        
        Args:
            query: Query vector
            candidates: List of candidate vectors
            
        Returns:
            List of similarity scores in same order as candidates
        """
        pass
    
    @staticmethod
    def _validate_vectors(v1: List[float], v2: List[float]) -> None:
        """Validate that vectors are valid."""
        if len(v1) != len(v2):
            raise ValueError(f"Vector dimension mismatch: {len(v1)} vs {len(v2)}")
        
        if not v1 or not v2:
            raise ValueError("Vectors cannot be empty")


class CosineSimilarity(SimilarityAlgorithm):
    """
    Cosine similarity metric.
    
    Computes: (v1 · v2) / (||v1|| * ||v2||)
    Range: [-1, 1] where 1 = identical, 0 = orthogonal, -1 = opposite
    
    Good for: Embeddings, normalized vectors
    """
    
    @property
    def metric_type(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE
    
    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity."""
        self._validate_vectors(vec1, vec2)
        
        # Compute dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # Compute norms
        norm1 = math.sqrt(sum(a ** 2 for a in vec1))
        norm2 = math.sqrt(sum(b ** 2 for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def compute_batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """Compute cosine similarity with batch of candidates."""
        if not candidates:
            return []
        
        # Precompute query norm
        query_norm = math.sqrt(sum(x ** 2 for x in query))
        
        if query_norm == 0:
            return [0.0] * len(candidates)
        
        similarities = []
        for candidate in candidates:
            if not candidate or len(candidate) != len(query):
                similarities.append(0.0)
                continue
            
            dot_product = sum(a * b for a, b in zip(query, candidate))
            candidate_norm = math.sqrt(sum(b ** 2 for b in candidate))
            
            if candidate_norm == 0:
                similarities.append(0.0)
            else:
                similarities.append(dot_product / (query_norm * candidate_norm))
        
        return similarities


class EuclideanSimilarity(SimilarityAlgorithm):
    """
    Euclidean distance metric (converted to similarity).
    
    Computes: sqrt(sum((v1[i] - v2[i])^2))
    Then converts to similarity: 1 / (1 + distance)
    Range: (0, 1] where 1 = identical
    
    Good for: When absolute distance matters
    """
    
    @property
    def metric_type(self) -> SimilarityMetric:
        return SimilarityMetric.EUCLIDEAN
    
    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute Euclidean similarity."""
        self._validate_vectors(vec1, vec2)
        
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2)))
        return 1.0 / (1.0 + distance)
    
    def compute_batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """Compute Euclidean similarity with batch."""
        if not candidates:
            return []
        
        similarities = []
        for candidate in candidates:
            similarity = self.compute_similarity(query, candidate)
            similarities.append(similarity)
        
        return similarities


class InnerProductSimilarity(SimilarityAlgorithm):
    """
    Inner product similarity (dot product).
    
    Computes: v1 · v2
    Range: [-inf, inf]
    
    Good for: When magnitude conveys meaning, dense embeddings
    """
    
    @property
    def metric_type(self) -> SimilarityMetric:
        return SimilarityMetric.INNER_PRODUCT
    
    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute inner product similarity."""
        self._validate_vectors(vec1, vec2)
        return sum(a * b for a, b in zip(vec1, vec2))
    
    def compute_batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """Compute inner product with batch."""
        if not candidates:
            return []
        
        return [
            sum(a * b for a, b in zip(query, candidate))
            for candidate in candidates
        ]


class ManhattanSimilarity(SimilarityAlgorithm):
    """
    Manhattan distance metric (converted to similarity).
    
    Computes: sum(|v1[i] - v2[i]|)
    Then converts to similarity: 1 / (1 + distance)
    Range: (0, 1]
    
    Good for: Grid-like data, feature differences
    """
    
    @property
    def metric_type(self) -> SimilarityMetric:
        return SimilarityMetric.MANHATTAN
    
    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute Manhattan similarity."""
        self._validate_vectors(vec1, vec2)
        
        distance = sum(abs(a - b) for a, b in zip(vec1, vec2))
        return 1.0 / (1.0 + distance)
    
    def compute_batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """Compute Manhattan similarity with batch."""
        if not candidates:
            return []
        
        similarities = []
        for candidate in candidates:
            similarity = self.compute_similarity(query, candidate)
            similarities.append(similarity)
        
        return similarities


class ChebyshevSimilarity(SimilarityAlgorithm):
    """
    Chebyshev distance metric (converted to similarity).
    
    Computes: max(|v1[i] - v2[i]|) for all i
    Then converts to similarity: 1 / (1 + distance)
    Range: (0, 1]
    
    Good for: Minimax optimization
    """
    
    @property
    def metric_type(self) -> SimilarityMetric:
        return SimilarityMetric.CHEBYSHEV
    
    def compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute Chebyshev similarity."""
        self._validate_vectors(vec1, vec2)
        
        distance = max(abs(a - b) for a, b in zip(vec1, vec2))
        return 1.0 / (1.0 + distance)
    
    def compute_batch_similarity(
        self,
        query: List[float],
        candidates: List[List[float]]
    ) -> List[float]:
        """Compute Chebyshev similarity with batch."""
        if not candidates:
            return []
        
        similarities = []
        for candidate in candidates:
            similarity = self.compute_similarity(query, candidate)
            similarities.append(similarity)
        
        return similarities


class SimilarityAlgorithmFactory:
    """Factory for creating similarity algorithms."""
    
    _algorithms: Dict[SimilarityMetric, SimilarityAlgorithm] = {
        SimilarityMetric.COSINE: CosineSimilarity(),
        SimilarityMetric.EUCLIDEAN: EuclideanSimilarity(),
        SimilarityMetric.INNER_PRODUCT: InnerProductSimilarity(),
        SimilarityMetric.MANHATTAN: ManhattanSimilarity(),
        SimilarityMetric.CHEBYSHEV: ChebyshevSimilarity(),
    }
    
    @classmethod
    def get_algorithm(cls, metric: SimilarityMetric) -> SimilarityAlgorithm:
        """Get algorithm for metric type."""
        if metric not in cls._algorithms:
            raise ValueError(f"Unknown similarity metric: {metric}")
        
        return cls._algorithms[metric]
    
    @classmethod
    def register_algorithm(cls, metric: SimilarityMetric, algorithm: SimilarityAlgorithm):
        """Register custom similarity algorithm."""
        cls._algorithms[metric] = algorithm


class DomainThresholdConfig:
    """Domain-specific similarity thresholds."""
    
    # Default thresholds per domain
    DEFAULT_THRESHOLDS = {
        DomainType.MEDICAL: 0.95,      # Strict: medical accuracy critical
        DomainType.LEGAL: 0.92,        # Strict: legal precision important
        DomainType.FINANCIAL: 0.90,    # Balanced
        DomainType.ECOMMERCE: 0.80,    # Lenient: product matching flexible
        DomainType.GENERAL: 0.85,      # Default general purpose
    }
    
    def __init__(self, overrides: Optional[Dict[DomainType, float]] = None):
        """
        Initialize domain threshold config.
        
        Args:
            overrides: Optional domain-specific threshold overrides
        """
        self.thresholds = self.DEFAULT_THRESHOLDS.copy()
        if overrides:
            self.thresholds.update(overrides)
    
    def get_threshold(self, domain: DomainType) -> float:
        """Get threshold for domain."""
        return self.thresholds.get(domain, self.DEFAULT_THRESHOLDS[DomainType.GENERAL])
    
    def set_threshold(self, domain: DomainType, threshold: float) -> None:
        """Set threshold for domain."""
        if not 0 <= threshold <= 1:
            raise ValueError(f"Threshold must be between 0 and 1, got {threshold}")
        
        self.thresholds[domain] = threshold
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {domain.value: threshold for domain, threshold in self.thresholds.items()}
