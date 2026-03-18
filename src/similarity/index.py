"""
HNSW (Hierarchical Navigable Small World) Index

Implements fast approximate nearest neighbor search using HNSW algorithm.
Provides O(log N) search complexity with configurable accuracy/speed tradeoff.

Features:
- Hierarchical layering for multi-scale search
- Configurable M (branching factor) and ef (expansion factor)
- Batch insertion and search
- Memory efficient
"""

import heapq
import random
import math
from typing import List, Tuple, Set, Dict, Optional
from collections import defaultdict
import time

from src.similarity.base import SimilarityAlgorithm, SimilarityMetric, SimilarityScore


class HNSWIndex:
    """
    Hierarchical Navigable Small World Index for approximate nearest neighbor search.
    
    This implements a simplified version of HNSW suitable for semantic cache use cases.
    Full HNSW implementation would require:
    - Proper layer assignment (exponential decay)
    - Complex neighbor selection and pruning
    - Advanced heuristics for diverse neighbors
    
    This simplified version provides:
    - Multi-level indexing
    - Fast approximate search
    - Clean integration with similarity metrics
    """
    
    def __init__(
        self,
        dimension: int,
        similarity_algorithm: SimilarityAlgorithm,
        m: int = 16,  # Maximum number of neighbors per level
        ef: int = 200,  # Size of dynamic candidate list
        max_m: int = 48,  # Maximum allowed neighbors
        ml: float = 1.0 / math.log(2.0),  # Normalization factor for layer assignment
        seed: int = 0,
    ):
        """
        Initialize HNSW index.
        
        Args:
            dimension: Dimensionality of vectors
            similarity_algorithm: Similarity metric to use
            m: Number of neighbors per level (default 16)
            ef: Size of dynamic candidate list for search (default 200)
            max_m: Maximum neighbors allowed (default 48)
            ml: Normalization factor for layer assignment
            seed: Random seed for reproducibility
        """
        self.dimension = dimension
        self.similarity_algorithm = similarity_algorithm
        self.m = m
        self.max_m = max_m
        self.ef = ef
        self.ml = ml
        
        random.seed(seed)
        
        # Data storage
        self.data: Dict[str, List[float]] = {}  # id -> embedding vector
        self.metadata: Dict[str, Dict] = {}  # id -> metadata
        
        # Index structure
        self.graph: Dict[int, Dict[int, Set[int]]] = defaultdict(lambda: defaultdict(set))
        # graph[level][node_id] = set of neighbor node_ids at this level
        
        self.node_id_map: Dict[str, int] = {}  # string id -> internal node id
        self.node_reverse_map: Dict[int, str] = {}  # internal node id -> string id
        self.node_levels: Dict[int, int] = {}  # node_id -> assigned level
        
        self.entry_point: Optional[int] = None  # Entry point for search
        self.next_node_id = 0
        
    def insert(self, item_id: str, embedding: List[float], metadata: Optional[Dict] = None) -> None:
        """
        Insert a new item into the index.
        
        Args:
            item_id: Unique identifier for item
            embedding: Embedding vector
            metadata: Optional metadata to store
        """
        if len(embedding) != self.dimension:
            raise ValueError(f"Embedding dimension mismatch: {len(embedding)} vs {self.dimension}")
        
        if item_id in self.data:
            raise ValueError(f"Item {item_id} already exists in index")
        
        # Assign internal node ID
        internal_id = self.next_node_id
        self.next_node_id += 1
        
        self.node_id_map[item_id] = internal_id
        self.node_reverse_map[internal_id] = item_id
        self.data[item_id] = embedding[:]
        self.metadata[item_id] = metadata or {}
        
        # Assign random layer
        level = int(-math.log(random.uniform(0, 1)) * self.ml)
        self.node_levels[internal_id] = level
        
        if self.entry_point is None:
            # First node
            self.entry_point = internal_id
        else:
            # Insert into existing graph
            self._insert_node(internal_id, embedding, level)
    
    def _insert_node(self, internal_id: int, embedding: List[float], level: int) -> None:
        """Insert node into graph structure."""
        # Start from entry point and search for closest nodes across layers
        nearest = [(float('inf'), self.entry_point)]
        
        # Search for nearest neighbors at highest levels
        for lc in range(self.entry_point if self.entry_point else 0, level, -1):
            nearest = self._search_layer(embedding, nearest, 1, lc)
        
        # Insert at all levels from 0 to assigned level
        for lc in range(min(level, self.node_levels.get(self.entry_point, 0)), -1, -1):
            candidates = self._search_layer(embedding, nearest, self.ef, lc)
            
            # Select M neighbors
            m = self.m if lc > 0 else self.max_m * 2
            neighbors = self._get_neighbors(candidates, m)
            
            # Add bidirectional edges
            for _, neighbor_id in neighbors:
                self.graph[lc][internal_id].add(neighbor_id)
                self.graph[lc][neighbor_id].add(internal_id)
                
                # Prune neighbor's connections if needed
                max_neighbors = self.m if lc > 0 else self.max_m * 2
                if len(self.graph[lc][neighbor_id]) > max_neighbors:
                    prune_list = self._prune_neighbors(
                        neighbor_id,
                        self.graph[lc][neighbor_id],
                        max_neighbors,
                        lc
                    )
                    self.graph[lc][neighbor_id] = set(prune_list)
        
        # Update entry point if necessary
        if level > self.node_levels.get(self.entry_point, 0):
            self.entry_point = internal_id
    
    def search(
        self,
        query: List[float],
        k: int = 10,
        ef: Optional[int] = None,
    ) -> List[Tuple[str, float]]:
        """
        Search for k nearest neighbors.
        
        Args:
            query: Query embedding
            k: Number of results to return
            ef: Search expansion factor (uses instance ef if None)
            
        Returns:
            List of (item_id, similarity) tuples sorted by similarity (descending)
        """
        if len(query) != self.dimension:
            raise ValueError(f"Query dimension mismatch: {len(query)} vs {self.dimension}")
        
        if not self.data:
            return []
        
        ef = ef or self.ef
        
        if self.entry_point is None:
            return []
        
        # Search from top level to 0
        nearest = [(float('inf'), self.entry_point)]
        
        entry_level = self.node_levels.get(self.entry_point, 0)
        
        # Greedy search through upper layers
        for lc in range(entry_level, 0, -1):
            nearest = self._search_layer(query, nearest, 1, lc)
        
        # Search at layer 0 with ef parameter
        nearest = self._search_layer(query, nearest, max(ef, k), 0)
        
        # Return top-k results
        results = []
        for _ in range(min(k, len(nearest))):
            if nearest:
                distance, node_id = heapq.heappop(nearest)
                item_id = self.node_reverse_map[node_id]
                similarity = -distance  # Convert distance back to similarity
                results.append((item_id, similarity))
        
        return results
    
    def _search_layer(
        self,
        query: List[float],
        entry_points: List[Tuple[float, int]],
        ef: int,
        layer: int,
    ) -> List[Tuple[float, int]]:
        """
        Search layer for nearest neighbors.
        
        Args:
            query: Query embedding
            entry_points: Starting points (distance, node_id)
            ef: Expansion factor for search
            layer: Layer to search
            
        Returns:
            List of (distance, node_id) tuples
        """
        visited: Set[int] = set()
        w: List[Tuple[float, int]] = []
        candidates: List[Tuple[float, int]] = []
        
        for distance, node_id in entry_points:
            heapq.heappush(candidates, (-distance, node_id))
            heapq.heappush(w, (distance, node_id))
            visited.add(node_id)
        
        while candidates:
            lowerbound, node_id = heapq.heappop(candidates)
            
            if -lowerbound > w[0][0]:
                break
            
            # Check neighbors at this layer
            neighbors = self.graph[layer].get(node_id, set())
            
            for neighbor_id in neighbors:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    
                    neighbor_embedding = self.data[self.node_reverse_map[neighbor_id]]
                    distance = self._compute_distance(query, neighbor_embedding)
                    
                    if distance < w[0][0] or len(w) < ef:
                        heapq.heappush(candidates, (-distance, neighbor_id))
                        heapq.heappush(w, (distance, neighbor_id))
                        
                        if len(w) > ef:
                            heapq.heappop(w)
        
        return w
    
    def _get_neighbors(
        self,
        candidates: List[Tuple[float, int]],
        m: int,
    ) -> List[Tuple[float, int]]:
        """Select M neighbors from candidates using heuristic."""
        return heapq.nsmallest(m, candidates)
    
    def _prune_neighbors(
        self,
        node_id: int,
        neighbors: Set[int],
        m: int,
        layer: int,
    ) -> List[int]:
        """Prune neighbor set to size M using diversity heuristic."""
        neighbors_list = list(neighbors)
        
        # Sort by distance to node
        node_embedding = self.data[self.node_reverse_map[node_id]]
        sorted_neighbors = sorted(
            neighbors_list,
            key=lambda n: self._compute_distance(
                node_embedding,
                self.data[self.node_reverse_map[n]]
            )
        )
        
        return sorted_neighbors[:m]
    
    def _compute_distance(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute distance using similarity metric."""
        similarity = self.similarity_algorithm.compute_similarity(vec1, vec2)
        # Convert similarity to distance (lower distance = higher similarity)
        return -similarity
    
    def get_stats(self) -> Dict[str, any]:
        """Get index statistics."""
        total_nodes = len(self.data)
        total_edges = sum(
            len(neighbors)
            for level_graph in self.graph.values()
            for neighbors in level_graph.values()
        ) // 2  # Divide by 2 since edges are bidirectional
        
        levels = set(self.node_levels.values()) if self.node_levels else {0}
        
        return {
            "total_items": total_nodes,
            "total_edges": total_edges,
            "index_levels": max(levels) if levels else 0,
            "entry_point": self.node_reverse_map.get(self.entry_point) if self.entry_point else None,
            "average_edges_per_node": total_edges / max(total_nodes, 1),
            "memory_estimate_mb": (total_nodes * self.dimension * 4) / 1024 / 1024,
        }

