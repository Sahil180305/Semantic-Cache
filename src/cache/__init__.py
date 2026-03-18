"""
Cache Layer Module

High-performance two-tier caching system combining:
- L1: In-memory HNSW cache with eviction policies
- L2: Redis-backed distributed cache
- Manager: Intelligent tiered orchestration
"""

from src.cache.base import (
    CacheConfig,
    CacheEntry,
    CacheMetrics,
    EvictionPolicy,
    CacheHitReason,
    CacheBackendInterface,
    EvictionPolicyInterface,
)
from src.cache.policies import (
    LRUEvictionPolicy,
    LFUEvictionPolicy,
    FIFOEvictionPolicy,
    TTLEvictionPolicy,
    AdaptiveEvictionPolicy,
    create_eviction_policy,
)
from src.cache.l1_cache import L1Cache
from src.cache.redis_config import (
    RedisConfig,
    RedisConnectionManager,
    RedisSerializer,
    SerializationFormat,
    RedisPipelineManager,
)
from src.cache.l2_cache import L2Cache, L2CacheMetrics
from src.cache.cache_manager import (
    CacheManager,
    CacheManagerConfig,
    CacheStrategy,
    TieredCacheMetrics,
)

__all__ = [
    # Configuration
    "CacheConfig",
    "EvictionPolicy",
    "RedisConfig",
    "CacheManagerConfig",
    "CacheStrategy",
    # Data structures
    "CacheEntry",
    "CacheMetrics",
    "CacheHitReason",
    "L2CacheMetrics",
    "TieredCacheMetrics",
    # Interfaces
    "CacheBackendInterface",
    "EvictionPolicyInterface",
    # Policies
    "LRUEvictionPolicy",
    "LFUEvictionPolicy",
    "FIFOEvictionPolicy",
    "TTLEvictionPolicy",
    "AdaptiveEvictionPolicy",
    "create_eviction_policy",
    # Redis components
    "RedisConnectionManager",
    "RedisSerializer",
    "SerializationFormat",
    "RedisPipelineManager",
    # Cache implementations
    "L1Cache",
    "L2Cache",
    "CacheManager",
]
