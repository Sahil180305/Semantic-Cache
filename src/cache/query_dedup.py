"""
Query Deduplication and Similarity Detection

Detects duplicate queries, near-duplicates, and similar query patterns.
Uses string similarity metrics and fuzzy matching for intelligent query grouping.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set


logger = logging.getLogger(__name__)


class DeduplicationStrategy(Enum):
    """Query deduplication strategies."""
    EXACT = "exact"  # Exact text match only
    NORMALIZED = "normalized"  # Normalized text match (case-insensitive, stripped)
    SEMANTIC = "semantic"  # Fuzzy matching with similarity threshold
    PREFIX = "prefix"  # Prefix matching for query variants


@dataclass
class SimilarityMetrics:
    """Metrics for query similarity comparison."""
    
    exact_match: bool = False
    normalized_match: bool = False
    semantic_similarity: float = 0.0  # 0.0 to 1.0
    char_similarity: float = 0.0  # SequenceMatcher ratio
    token_overlap: float = 0.0  # Token set overlap ratio
    
    def is_duplicate(self, threshold: float = 0.85) -> bool:
        """Check if query is considered a duplicate.
        
        Args:
            threshold: Similarity threshold (0.0-1.0)
            
        Returns:
            True if duplicate, False otherwise
        """
        if self.exact_match or self.normalized_match:
            return True
        
        # Use best similarity metric
        best_similarity = max(
            self.semantic_similarity,
            self.char_similarity,
            self.token_overlap
        )
        
        return best_similarity >= threshold


class QueryNormalizer:
    """Normalizes queries for deduplication."""
    
    def __init__(self):
        """Initialize normalizer."""
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been',
            'what', 'where', 'when', 'why', 'how', 'please', 'thanks', 'thank'
        }
    
    def normalize(self, query: str) -> str:
        """Normalize query for comparison.
        
        Args:
            query: Raw query text
            
        Returns:
            Normalized query
        """
        # Lowercase
        normalized = query.lower().strip()
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        
        # Remove punctuation
        import string
        normalized = normalized.translate(str.maketrans('', '', string.punctuation))
        
        return normalized
    
    def normalize_with_tokens(self, query: str) -> Tuple[str, List[str]]:
        """Normalize query and return tokens.
        
        Args:
            query: Raw query text
            
        Returns:
            (normalized_query, list_of_tokens)
        """
        normalized = self.normalize(query)
        tokens = [t for t in normalized.split() if t not in self.stop_words and len(t) > 2]
        return normalized, tokens


class QueryHasher:
    """Generates consistent hashes for queries."""
    
    def hash_exact(self, query: str) -> str:
        """Generate hash for exact matching.
        
        Args:
            query: Query text
            
        Returns:
            SHA256 hash
        """
        return hashlib.sha256(query.encode()).hexdigest()
    
    def hash_normalized(self, query: str, normalizer: QueryNormalizer) -> str:
        """Generate hash for normalized matching.
        
        Args:
            query: Query text
            normalizer: Query normalizer
            
        Returns:
            SHA256 hash of normalized query
        """
        normalized = normalizer.normalize(query)
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def hash_prefix(self, query: str, prefix_length: int = 10) -> str:
        """Generate hash based on query prefix.
        
        Args:
            query: Query text
            prefix_length: Length of prefix to hash
            
        Returns:
            SHA256 hash of prefix
        """
        prefix = query[:prefix_length].lower()
        return hashlib.sha256(prefix.encode()).hexdigest()


class QuerySimilarityMatcher:
    """Matches similar queries using multiple similarity metrics."""
    
    def __init__(self, char_threshold: float = 0.85, token_threshold: float = 0.7):
        """Initialize matcher.
        
        Args:
            char_threshold: Character similarity threshold
            token_threshold: Token overlap threshold
        """
        self.char_threshold = char_threshold
        self.token_threshold = token_threshold
        self.normalizer = QueryNormalizer()
    
    def compare_queries(self, query1: str, query2: str) -> SimilarityMetrics:
        """Compare two queries for similarity.
        
        Args:
            query1: First query
            query2: Second query
            
        Returns:
            Similarity metrics
        """
        metrics = SimilarityMetrics()
        
        # Exact match
        metrics.exact_match = query1 == query2
        
        # Normalized match
        norm1 = self.normalizer.normalize(query1)
        norm2 = self.normalizer.normalize(query2)
        metrics.normalized_match = norm1 == norm2
        
        # Character similarity (SequenceMatcher)
        matcher = SequenceMatcher(None, norm1, norm2)
        metrics.char_similarity = matcher.ratio()
        
        # Token overlap
        _, tokens1 = self.normalizer.normalize_with_tokens(query1)
        _, tokens2 = self.normalizer.normalize_with_tokens(query2)
        
        if tokens1 and tokens2:
            set1 = set(tokens1)
            set2 = set(tokens2)
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            metrics.token_overlap = intersection / union if union > 0 else 0.0
        
        return metrics
    
    def find_similar(self, query: str, candidates: List[str], 
                    threshold: float = 0.85) -> List[Tuple[str, SimilarityMetrics]]:
        """Find similar queries from candidates.
        
        Args:
            query: Query to match
            candidates: List of candidate queries
            threshold: Similarity threshold
            
        Returns:
            List of (candidate, metrics) for similar queries
        """
        results = []
        
        for candidate in candidates:
            metrics = self.compare_queries(query, candidate)
            
            if metrics.is_duplicate(threshold):
                results.append((candidate, metrics))
        
        # Sort by best similarity
        results.sort(
            key=lambda x: max(
                x[1].semantic_similarity,
                x[1].char_similarity,
                x[1].token_overlap
            ),
            reverse=True
        )
        
        return results


@dataclass
class DuplicateGroupMetrics:
    """Metrics for duplicate query groups."""
    
    group_id: str
    canonical_query: str
    duplicate_count: int = 0
    total_occurrences: int = 0
    cache_hits_saved: int = 0  # Cache hits saved by dedup
    created_at: float = field(default_factory=lambda: __import__('time').time())
    
    def efficiency_ratio(self) -> float:
        """Calculate deduplication efficiency.
        
        Returns:
            Ratio of saved hits to total occurrences
        """
        if self.total_occurrences == 0:
            return 0.0
        return self.cache_hits_saved / self.total_occurrences


class QueryDeduplicationEngine:
    """Manages query deduplication and duplicate detection."""
    
    def __init__(self, strategy: DeduplicationStrategy = DeduplicationStrategy.NORMALIZED,
                 similarity_threshold: float = 0.85):
        """Initialize deduplication engine.
        
        Args:
            strategy: Deduplication strategy to use
            similarity_threshold: Threshold for semantic similarity
        """
        self.strategy = strategy
        self.similarity_threshold = similarity_threshold
        
        self.normalizer = QueryNormalizer()
        self.hasher = QueryHasher()
        self.matcher = QuerySimilarityMatcher()
        
        # Tracking
        self.exact_hashes: Dict[str, str] = {}  # hash -> canonical_query
        self.normalized_hashes: Dict[str, str] = {}  # hash -> canonical_query
        self.duplicate_groups: Dict[str, DuplicateGroupMetrics] = {}
        self.query_to_group: Dict[str, str] = {}  # query -> group_id
        
        self.total_dedup_detected = 0
    
    def register_query(self, query: str) -> Tuple[str, bool]:
        """Register a query and check for duplicates.
        
        Args:
            query: Query text
            
        Returns:
            (canonical_query, is_duplicate)
        """
        if self.strategy == DeduplicationStrategy.EXACT:
            return self._register_exact(query)
        elif self.strategy == DeduplicationStrategy.NORMALIZED:
            return self._register_normalized(query)
        elif self.strategy == DeduplicationStrategy.SEMANTIC:
            return self._register_semantic(query)
        else:
            return query, False
    
    def _register_exact(self, query: str) -> Tuple[str, bool]:
        """Register with exact matching.
        
        Args:
            query: Query text
            
        Returns:
            (canonical_query, is_duplicate)
        """
        query_hash = self.hasher.hash_exact(query)
        
        if query_hash in self.exact_hashes:
            canonical = self.exact_hashes[query_hash]
            self.total_dedup_detected += 1
            return canonical, True
        
        # New query
        self.exact_hashes[query_hash] = query
        return query, False
    
    def _register_normalized(self, query: str) -> Tuple[str, bool]:
        """Register with normalized matching.
        
        Args:
            query: Query text
            
        Returns:
            (canonical_query, is_duplicate)
        """
        query_hash = self.hasher.hash_normalized(query, self.normalizer)
        
        if query_hash in self.normalized_hashes:
            canonical = self.normalized_hashes[query_hash]
            self.total_dedup_detected += 1
            return canonical, True
        
        # New query - track in both hashes
        self.normalized_hashes[query_hash] = query
        query_exact_hash = self.hasher.hash_exact(query)
        self.exact_hashes[query_exact_hash] = query
        return query, False
    
    def _register_semantic(self, query: str) -> Tuple[str, bool]:
        """Register with semantic similarity matching.
        
        Args:
            query: Query text
            
        Returns:
            (canonical_query, is_duplicate)
        """
        # Check against all registered queries
        all_queries = list(set(list(self.exact_hashes.values()) + list(self.normalized_hashes.values())))
        
        if all_queries:
            similar = self.matcher.find_similar(
                query,
                all_queries,
                self.similarity_threshold
            )
            
            if similar:
                canonical = similar[0][0]
                self.total_dedup_detected += 1
                return canonical, True
        
        # New query
        query_hash = self.hasher.hash_exact(query)
        self.exact_hashes[query_hash] = query
        return query, False
    
    def get_stats(self) -> Dict[str, any]:
        """Get deduplication statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "strategy": self.strategy.value,
            "total_deduplicated": self.total_dedup_detected,
            "unique_queries": len(self.exact_hashes),
            "duplicate_groups": len(self.duplicate_groups),
        }
    
    def clear(self) -> None:
        """Clear all tracking data."""
        self.exact_hashes.clear()
        self.normalized_hashes.clear()
        self.duplicate_groups.clear()
        self.query_to_group.clear()
        self.total_dedup_detected = 0


class PrefixMatchingEngine:
    """Matches query prefixes for efficient grouping."""
    
    def __init__(self, min_prefix_length: int = 5):
        """Initialize prefix matching engine.
        
        Args:
            min_prefix_length: Minimum prefix length to track
        """
        self.min_prefix_length = min_prefix_length
        self.prefix_to_queries: Dict[str, Set[str]] = {}
    
    def register_prefix(self, query: str) -> str:
        """Register query prefix and return matching prefix.
        
        Args:
            query: Query text
            
        Returns:
            Matched prefix or empty string
        """
        query_lower = query.lower().strip()
        
        # Check existing prefixes
        for length in range(len(query_lower), self.min_prefix_length - 1, -1):
            prefix = query_lower[:length]
            
            if prefix in self.prefix_to_queries:
                self.prefix_to_queries[prefix].add(query_lower)
                return prefix
        
        # Create new prefix
        if len(query_lower) >= self.min_prefix_length:
            prefix = query_lower[:self.min_prefix_length]
            self.prefix_to_queries[prefix] = {query_lower}
            return prefix
        
        return ""
    
    def find_by_prefix(self, prefix: str) -> List[str]:
        """Find all queries matching a prefix.
        
        Args:
            prefix: Query prefix
            
        Returns:
            List of matching queries
        """
        if prefix in self.prefix_to_queries:
            return list(self.prefix_to_queries[prefix])
        
        return []
    
    def clear(self) -> None:
        """Clear all prefix data."""
        self.prefix_to_queries.clear()
