"""
L2 Cache - Redis-Backed Distributed Cache Layer

Provides persistent, distributed caching using Redis as the backend.
Handles serialization, connection management, and TTL-based expiration.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import redis
from redis.exceptions import RedisError

from src.cache.base import CacheEntry, CacheHitReason
from src.cache.redis_config import (
    RedisConfig, RedisConnectionManager, RedisSerializer, 
    SerializationFormat, RedisPipelineManager
)


logger = logging.getLogger(__name__)


class L2CacheMetrics:
    """Metrics for L2 Redis cache."""
    
    def __init__(self):
        """Initialize metrics."""
        self.redis_hits = 0
        self.redis_misses = 0
        self.serialization_errors = 0
        self.connection_errors = 0
        self.evictions = 0
        self.bytes_stored = 0
        self.bytes_retrieved = 0
        self.latency_ms = 0.0
        self.created_at = time.time()
    
    def get_hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self.redis_hits + self.redis_misses
        if total == 0:
            return 0.0
        return self.redis_hits / total
    
    def record_hit(self, latency_ms: float = 0.0) -> None:
        """Record cache hit."""
        self.redis_hits += 1
        self.latency_ms += latency_ms
    
    def record_miss(self, latency_ms: float = 0.0) -> None:
        """Record cache miss."""
        self.redis_misses += 1
        self.latency_ms += latency_ms
    
    def reset(self) -> None:
        """Reset metrics."""
        self.redis_hits = 0
        self.redis_misses = 0
        self.serialization_errors = 0
        self.connection_errors = 0
        self.evictions = 0
        self.bytes_stored = 0
        self.bytes_retrieved = 0
        self.latency_ms = 0.0
        self.created_at = time.time()


class L2Cache:
    """Redis-backed L2 cache implementation.
    
    Stores cache entries in Redis for persistence and distributed access.
    Complements L1 in-memory cache for a two-tier caching strategy.
    """
    
    def __init__(self, config: Optional[RedisConfig] = None):
        """Initialize L2 cache.
        
        Args:
            config: Redis configuration
        """
        if config is None:
            config = RedisConfig()
        
        self.config = config
        self.connection_manager = RedisConnectionManager(config)
        self.serializer = RedisSerializer(config.serialization_format)
        self.metrics = L2CacheMetrics()
        
        self._client: Optional[redis.Redis] = None
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to Redis.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self._client = self.connection_manager.connect()
            self._connected = True
            logger.info("L2Cache connected to Redis")
            return True
        except Exception as e:
            logger.error(f"Failed to connect L2Cache: {e}")
            self.metrics.connection_errors += 1
            return False
    
    def disconnect(self) -> None:
        """Disconnect from Redis."""
        self.connection_manager.disconnect()
        self._client = None
        self._connected = False
    
    def ensure_connected(self) -> bool:
        """Ensure connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        if self._client is None:
            return self.connect()
        
        if not self.connection_manager.is_connected():
            self._connected = False
            return self.connect()
        
        return True
    
    def put(self, entry: CacheEntry) -> bool:
        """Store entry in Redis.
        
        Args:
            entry: Cache entry to store
            
        Returns:
            True if successful, False otherwise
        """
        if not self.ensure_connected():
            self.metrics.connection_errors += 1
            return False
        
        try:
            key = self._make_key(entry.query_id)
            
            # Serialize entry
            data = {
                "query_id": entry.query_id,
                "query_text": entry.query_text,
                "embedding": entry.embedding,
                "response": entry.response,
                "metadata": entry.metadata,
                "created_at": entry.created_at,
                "last_accessed_at": entry.last_accessed_at,
                "access_count": entry.access_count,
            }
            
            serialized = self.serializer.serialize(data)
            
            # Store in Redis with TTL
            ttl = self.config.default_ttl_seconds
            
            if self.config.serialization_format == SerializationFormat.JSON:
                self._client.setex(key, ttl, serialized)
            else:
                self._client.setex(key, ttl, serialized)
            
            # Track bytes
            size = len(serialized) if isinstance(serialized, bytes) else len(serialized.encode())
            self.metrics.bytes_stored += size
            
            logger.debug(f"L2: Stored query {entry.query_id} ({size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"L2: Failed to store entry: {e}")
            self.metrics.serialization_errors += 1
            return False
    
    def get(self, query_id: str) -> Optional[CacheEntry]:
        """Retrieve entry from Redis.
        
        Args:
            query_id: Query ID to retrieve
            
        Returns:
            Cache entry if found, None otherwise
        """
        if not self.ensure_connected():
            self.metrics.connection_errors += 1
            self.metrics.record_miss()
            return None
        
        try:
            start_time = time.time()
            key = self._make_key(query_id)
            
            # Get from Redis
            serialized = self._client.get(key)
            
            if serialized is None:
                self.metrics.record_miss(
                    (time.time() - start_time) * 1000
                )
                logger.debug(f"L2: Cache miss for {query_id}")
                return None
            
            # Deserialize
            data = self.serializer.deserialize(serialized)
            
            # Reconstruct entry
            entry = CacheEntry(
                query_id=data["query_id"],
                query_text=data["query_text"],
                embedding=data["embedding"],
                response=data["response"],
                metadata=data.get("metadata", {})
            )
            entry.created_at = data["created_at"]
            entry.last_accessed_at = data["last_accessed_at"]
            entry.access_count = data["access_count"]
            
            # Track metrics
            size = len(serialized) if isinstance(serialized, bytes) else len(serialized.encode())
            self.metrics.bytes_retrieved += size
            self.metrics.record_hit((time.time() - start_time) * 1000)
            
            logger.debug(f"L2: Cache hit for {query_id}")
            return entry
            
        except Exception as e:
            logger.error(f"L2: Failed to retrieve entry: {e}")
            self.metrics.serialization_errors += 1
            self.metrics.record_miss()
            return None
    
    def delete(self, query_id: str) -> bool:
        """Delete entry from Redis.
        
        Args:
            query_id: Query ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.ensure_connected():
            self.metrics.connection_errors += 1
            return False
        
        try:
            key = self._make_key(query_id)
            result = self._client.delete(key)
            
            if result > 0:
                logger.debug(f"L2: Deleted {query_id}")
            
            return result > 0
            
        except Exception as e:
            logger.error(f"L2: Failed to delete entry: {e}")
            self.metrics.connection_errors += 1
            return False
    
    def clear(self) -> bool:
        """Clear all entries from L2 cache.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        try:
            pattern = f"{self.config.key_prefix}*"
            cursor = 0
            deleted = 0
            
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern)
                
                if keys:
                    deleted += self._client.delete(*keys)
                
                if cursor == 0:
                    break
            
            logger.info(f"L2: Cleared {deleted} entries")
            return True
            
        except Exception as e:
            logger.error(f"L2: Failed to clear cache: {e}")
            return False
    
    def exists(self, query_id: str) -> bool:
        """Check if entry exists in Redis.
        
        Args:
            query_id: Query ID to check
            
        Returns:
            True if exists, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        try:
            key = self._make_key(query_id)
            return self._client.exists(key) > 0
        except Exception:
            return False
    
    def get_all_keys(self) -> List[str]:
        """Get all cache keys.
        
        Returns:
            List of query IDs
        """
        if not self.ensure_connected():
            return []
        
        try:
            pattern = f"{self.config.key_prefix}*"
            cursor = 0
            keys = []
            
            while True:
                cursor, batch_keys = self._client.scan(cursor, match=pattern)
                
                for key in batch_keys:
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    
                    # Remove prefix
                    query_id = key.replace(self.config.key_prefix, "")
                    keys.append(query_id)
                
                if cursor == 0:
                    break
            
            return keys
            
        except Exception as e:
            logger.error(f"L2: Failed to get keys: {e}")
            return []
    
    def size(self) -> int:
        """Get number of entries.
        
        Returns:
            Number of entries in L2 cache
        """
        if not self.ensure_connected():
            return 0
        
        try:
            pattern = f"{self.config.key_prefix}*"
            cursor = 0
            count = 0
            
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern)
                count += len(keys)
                
                if cursor == 0:
                    break
            
            return count
            
        except Exception:
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Redis server stats.
        
        Returns:
            Server statistics
        """
        if not self.ensure_connected():
            return {}
        
        try:
            stats = self._client.info()
            return {
                "used_memory": stats.get("used_memory"),
                "used_memory_human": stats.get("used_memory_human"),
                "connected_clients": stats.get("connected_clients"),
                "total_commands_processed": stats.get("total_commands_processed"),
                "cached_entries": self.size(),
                "hit_rate": self.metrics.get_hit_rate(),
            }
        except Exception as e:
            logger.error(f"L2: Failed to get stats: {e}")
            return {}
    
    def get_metrics(self) -> L2CacheMetrics:
        """Get cache metrics.
        
        Returns:
            L2 cache metrics
        """
        return self.metrics
    
    def batch_put(self, entries: List[CacheEntry]) -> Tuple[int, int]:
        """Store multiple entries using pipeline.
        
        Args:
            entries: List of entries to store
            
        Returns:
            (successful, failed) count
        """
        if not self.ensure_connected():
            return 0, len(entries)
        
        successful = 0
        failed = 0
        
        try:
            with RedisPipelineManager(
                self._client, 
                batch_size=self.config.pipeline_batch_size
            ) as pipe:
                for entry in entries:
                    try:
                        if self.put(entry):
                            successful += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.error(f"L2: Error in batch put: {e}")
                        failed += 1
            
            return successful, failed
            
        except Exception as e:
            logger.error(f"L2: Batch put failed: {e}")
            return 0, len(entries)
    
    def batch_get(self, query_ids: List[str]) -> List[Optional[CacheEntry]]:
        """Retrieve multiple entries.
        
        Args:
            query_ids: List of query IDs
            
        Returns:
            List of entries (None if not found)
        """
        results = []
        
        for query_id in query_ids:
            entry = self.get(query_id)
            results.append(entry)
        
        return results
    
    def set_ttl(self, query_id: str, ttl_seconds: int) -> bool:
        """Set TTL for an entry.
        
        Args:
            query_id: Query ID
            ttl_seconds: TTL in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        try:
            key = self._make_key(query_id)
            return self._client.expire(key, ttl_seconds)
        except Exception as e:
            logger.error(f"L2: Failed to set TTL: {e}")
            return False
    
    def get_ttl(self, query_id: str) -> Optional[int]:
        """Get TTL for an entry.
        
        Args:
            query_id: Query ID
            
        Returns:
            TTL in seconds, or None if not found
        """
        if not self.ensure_connected():
            return None
        
        try:
            key = self._make_key(query_id)
            ttl = self._client.ttl(key)
            
            if ttl == -2:  # Key doesn't exist
                return None
            if ttl == -1:  # No expiration
                return -1
            
            return ttl
            
        except Exception:
            return None
    
    def _make_key(self, query_id: str) -> str:
        """Create Redis key from query ID.
        
        Args:
            query_id: Query ID
            
        Returns:
            Full Redis key with prefix
        """
        return f"{self.config.key_prefix}{query_id}"
    
    def health_check(self) -> bool:
        """Check L2 cache health.
        
        Returns:
            True if healthy, False otherwise
        """
        return self.connection_manager.health_check()
