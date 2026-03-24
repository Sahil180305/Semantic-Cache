"""
L3 Cache - PostgreSQL-Backed Persistent Cold Storage Layer

Provides persistent, cold storage caching using PostgreSQL as the backend.
This is the third tier (L3) in the multi-level cache hierarchy:
- L1: In-memory (fastest, smallest)
- L2: Redis (fast, medium)
- L3: PostgreSQL (slowest, largest, persistent)

L3 is designed for:
- Long-term persistence of cache entries
- Large capacity (millions of entries)
- Queries that haven't been accessed recently but shouldn't be regenerated
"""

import json
import logging
import time
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, desc, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.cache.base import CacheEntry as BaseCacheEntry, CacheHitReason
from src.core.models import CacheEntry as DBCacheEntry, Tenant
from src.core.database import DatabaseManager, get_db_manager


logger = logging.getLogger(__name__)


@dataclass
class L3CacheMetrics:
    """Metrics for L3 PostgreSQL cache."""
    
    postgres_hits: int = 0
    postgres_misses: int = 0
    write_count: int = 0
    delete_count: int = 0
    errors: int = 0
    bytes_stored: int = 0
    bytes_retrieved: int = 0
    avg_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    created_at: float = 0.0
    
    def __post_init__(self):
        self.created_at = time.time()
    
    def get_hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self.postgres_hits + self.postgres_misses
        if total == 0:
            return 0.0
        return self.postgres_hits / total
    
    def record_hit(self, latency_ms: float = 0.0) -> None:
        """Record cache hit."""
        self.postgres_hits += 1
        self.total_latency_ms += latency_ms
        self._update_avg_latency()
    
    def record_miss(self, latency_ms: float = 0.0) -> None:
        """Record cache miss."""
        self.postgres_misses += 1
        self.total_latency_ms += latency_ms
        self._update_avg_latency()
    
    def _update_avg_latency(self) -> None:
        """Update average latency."""
        total = self.postgres_hits + self.postgres_misses
        if total > 0:
            self.avg_latency_ms = self.total_latency_ms / total
    
    def reset(self) -> None:
        """Reset metrics."""
        self.postgres_hits = 0
        self.postgres_misses = 0
        self.write_count = 0
        self.delete_count = 0
        self.errors = 0
        self.bytes_stored = 0
        self.bytes_retrieved = 0
        self.avg_latency_ms = 0.0
        self.total_latency_ms = 0.0
        self.created_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "postgres_hits": self.postgres_hits,
            "postgres_misses": self.postgres_misses,
            "hit_rate": self.get_hit_rate(),
            "write_count": self.write_count,
            "delete_count": self.delete_count,
            "errors": self.errors,
            "bytes_stored": self.bytes_stored,
            "bytes_retrieved": self.bytes_retrieved,
            "avg_latency_ms": self.avg_latency_ms,
            "uptime_seconds": time.time() - self.created_at,
        }


class L3Cache:
    """PostgreSQL-backed L3 cache implementation.
    
    Stores cache entries in PostgreSQL for persistent, cold storage.
    Complements L1 (memory) and L2 (Redis) for a three-tier caching strategy.
    
    Features:
    - Persistent storage surviving restarts
    - Large capacity (millions of entries)
    - Full SQL query capabilities
    - TTL-based expiration
    - Tenant isolation
    """
    
    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        default_ttl_days: int = 30,
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_dimension: int = 384,
    ):
        """Initialize L3 cache.
        
        Args:
            db_manager: Database manager instance (uses global if not provided)
            default_ttl_days: Default TTL in days for cache entries
            embedding_model: Name of embedding model used
            embedding_dimension: Dimension of embeddings
        """
        self._db_manager = db_manager
        self.default_ttl_days = default_ttl_days
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.metrics = L3CacheMetrics()
        self._connected = False
    
    @property
    def db_manager(self) -> DatabaseManager:
        """Get database manager, initializing if needed."""
        if self._db_manager is None:
            try:
                self._db_manager = get_db_manager()
            except Exception as e:
                logger.error(f"Failed to get database manager: {e}")
                raise
        return self._db_manager
    
    def connect(self) -> bool:
        """Connect to PostgreSQL.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Test connection
            with self.db_manager.session_context() as session:
                session.execute(text("SELECT 1"))
            self._connected = True
            logger.info("L3Cache connected to PostgreSQL")
            return True
        except Exception as e:
            logger.error(f"Failed to connect L3Cache: {e}")
            self.metrics.errors += 1
            return False
    
    def disconnect(self) -> None:
        """Disconnect from PostgreSQL."""
        self._connected = False
        logger.info("L3Cache disconnected")
    
    def ensure_connected(self) -> bool:
        """Ensure connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        if not self._connected:
            return self.connect()
        return True
    
    def _serialize_embedding(self, embedding: List[float]) -> bytes:
        """Serialize embedding to bytes for storage.
        
        Args:
            embedding: Embedding vector
            
        Returns:
            Serialized bytes
        """
        return pickle.dumps(embedding)
    
    def _deserialize_embedding(self, data: bytes) -> List[float]:
        """Deserialize embedding from bytes.
        
        Args:
            data: Serialized embedding bytes
            
        Returns:
            Embedding vector
        """
        return pickle.loads(data)
    
    def _entry_to_db_model(
        self,
        entry: BaseCacheEntry,
        tenant_id: str,
    ) -> DBCacheEntry:
        """Convert base cache entry to database model.
        
        Args:
            entry: Base cache entry
            tenant_id: Tenant ID
            
        Returns:
            Database model instance
        """
        import hashlib
        query_hash = hashlib.sha256(entry.query_text.encode()).hexdigest()[:32]
        
        expires_at = None
        if self.default_ttl_days > 0:
            expires_at = datetime.utcnow() + timedelta(days=self.default_ttl_days)
        
        return DBCacheEntry(
            id=entry.query_id,
            tenant_id=tenant_id,
            query_text=entry.query_text,
            query_hash=query_hash,
            embedding=self._serialize_embedding(entry.embedding),
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            response=json.dumps(entry.response) if not isinstance(entry.response, str) else entry.response,
            response_metadata=entry.metadata,
            domain=entry.domain,
            generation_cost=entry.metadata.get("cost") if entry.metadata else None,
            l3_cached=True,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )
    
    def _db_model_to_entry(self, db_entry: DBCacheEntry) -> BaseCacheEntry:
        """Convert database model to base cache entry.
        
        Args:
            db_entry: Database model
            
        Returns:
            Base cache entry
        """
        # Try to parse response as JSON, fall back to string
        try:
            response = json.loads(db_entry.response)
        except (json.JSONDecodeError, TypeError):
            response = db_entry.response
        
        entry = BaseCacheEntry(
            query_id=db_entry.id,
            query_text=db_entry.query_text,
            embedding=self._deserialize_embedding(db_entry.embedding),
            response=response,
            metadata=db_entry.response_metadata or {},
            domain=db_entry.domain or "general",
        )
        entry.created_at = db_entry.created_at.timestamp() if db_entry.created_at else time.time()
        entry.access_count = db_entry.actual_hits or 0
        
        return entry
    
    def put(self, entry: BaseCacheEntry, tenant_id: str = "default") -> bool:
        """Store entry in PostgreSQL.
        
        Args:
            entry: Cache entry to store
            tenant_id: Tenant ID for isolation
            
        Returns:
            True if successful, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        start_time = time.time()
        
        try:
            with self.db_manager.session_context() as session:
                # Check if entry already exists
                existing = session.query(DBCacheEntry).filter(
                    DBCacheEntry.id == entry.query_id
                ).first()
                
                if existing:
                    # Update existing entry
                    existing.response = json.dumps(entry.response) if not isinstance(entry.response, str) else entry.response
                    existing.response_metadata = entry.metadata
                    existing.l3_cached = True
                    existing.updated_at = datetime.utcnow()
                    logger.debug(f"Updated L3 cache entry: {entry.query_id}")
                else:
                    # Ensure tenant exists
                    tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
                    if not tenant:
                        tenant = Tenant(
                            id=tenant_id,
                            name=tenant_id,
                            is_active=True,
                        )
                        session.add(tenant)
                        session.flush()
                    
                    # Create new entry
                    db_entry = self._entry_to_db_model(entry, tenant_id)
                    session.add(db_entry)
                    logger.debug(f"Created L3 cache entry: {entry.query_id}")
                
                session.commit()
            
            latency_ms = (time.time() - start_time) * 1000
            self.metrics.write_count += 1
            self.metrics.bytes_stored += len(self._serialize_embedding(entry.embedding))
            logger.debug(f"L3 put completed in {latency_ms:.2f}ms")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"L3 put failed: {e}")
            self.metrics.errors += 1
            return False
    
    def get(self, query_id: str, tenant_id: Optional[str] = None) -> Optional[BaseCacheEntry]:
        """Retrieve entry from PostgreSQL.
        
        Args:
            query_id: Query ID to retrieve
            tenant_id: Optional tenant ID filter
            
        Returns:
            Cache entry if found, None otherwise
        """
        if not self.ensure_connected():
            return None
        
        start_time = time.time()
        
        try:
            with self.db_manager.session_context() as session:
                # Build query
                query = session.query(DBCacheEntry).filter(
                    DBCacheEntry.id == query_id,
                    DBCacheEntry.l3_cached == True,
                )
                
                # Add tenant filter if provided
                if tenant_id:
                    query = query.filter(DBCacheEntry.tenant_id == tenant_id)
                
                # Check expiration
                query = query.filter(
                    or_(
                        DBCacheEntry.expires_at.is_(None),
                        DBCacheEntry.expires_at > datetime.utcnow()
                    )
                )
                
                db_entry = query.first()
                
                latency_ms = (time.time() - start_time) * 1000
                
                if db_entry:
                    # Update hit count
                    db_entry.actual_hits = (db_entry.actual_hits or 0) + 1
                    db_entry.last_hit_at = datetime.utcnow()
                    session.commit()
                    
                    entry = self._db_model_to_entry(db_entry)
                    self.metrics.record_hit(latency_ms)
                    self.metrics.bytes_retrieved += len(db_entry.embedding)
                    logger.debug(f"L3 hit for {query_id} in {latency_ms:.2f}ms")
                    return entry
                else:
                    self.metrics.record_miss(latency_ms)
                    logger.debug(f"L3 miss for {query_id}")
                    return None
                    
        except SQLAlchemyError as e:
            logger.error(f"L3 get failed: {e}")
            self.metrics.errors += 1
            return None
    
    def delete(self, query_id: str, tenant_id: Optional[str] = None) -> bool:
        """Delete entry from PostgreSQL.
        
        Args:
            query_id: Query ID to delete
            tenant_id: Optional tenant ID filter
            
        Returns:
            True if deleted, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        try:
            with self.db_manager.session_context() as session:
                query = session.query(DBCacheEntry).filter(
                    DBCacheEntry.id == query_id
                )
                
                if tenant_id:
                    query = query.filter(DBCacheEntry.tenant_id == tenant_id)
                
                deleted = query.delete()
                session.commit()
                
                if deleted > 0:
                    self.metrics.delete_count += 1
                    logger.debug(f"Deleted L3 entry: {query_id}")
                    return True
                return False
                
        except SQLAlchemyError as e:
            logger.error(f"L3 delete failed: {e}")
            self.metrics.errors += 1
            return False
    
    def clear(self, tenant_id: Optional[str] = None) -> int:
        """Clear cache entries.
        
        Args:
            tenant_id: If provided, only clear entries for this tenant
            
        Returns:
            Number of entries deleted
        """
        if not self.ensure_connected():
            return 0
        
        try:
            with self.db_manager.session_context() as session:
                query = session.query(DBCacheEntry).filter(
                    DBCacheEntry.l3_cached == True
                )
                
                if tenant_id:
                    query = query.filter(DBCacheEntry.tenant_id == tenant_id)
                
                deleted = query.delete()
                session.commit()
                
                self.metrics.delete_count += deleted
                logger.info(f"Cleared {deleted} L3 entries" + (f" for tenant {tenant_id}" if tenant_id else ""))
                return deleted
                
        except SQLAlchemyError as e:
            logger.error(f"L3 clear failed: {e}")
            self.metrics.errors += 1
            return 0
    
    def get_all_keys(self, tenant_id: Optional[str] = None, limit: int = 1000) -> List[str]:
        """Get all cache entry keys.
        
        Args:
            tenant_id: Optional tenant filter
            limit: Maximum number of keys to return
            
        Returns:
            List of cache entry IDs
        """
        if not self.ensure_connected():
            return []
        
        try:
            with self.db_manager.session_context() as session:
                query = session.query(DBCacheEntry.id).filter(
                    DBCacheEntry.l3_cached == True
                )
                
                if tenant_id:
                    query = query.filter(DBCacheEntry.tenant_id == tenant_id)
                
                # Filter expired entries
                query = query.filter(
                    or_(
                        DBCacheEntry.expires_at.is_(None),
                        DBCacheEntry.expires_at > datetime.utcnow()
                    )
                )
                
                results = query.limit(limit).all()
                return [r[0] for r in results]
                
        except SQLAlchemyError as e:
            logger.error(f"L3 get_all_keys failed: {e}")
            self.metrics.errors += 1
            return []
    
    def get_hot_entries(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 50,
        min_hits: int = 1,
    ) -> List[Tuple[str, int, BaseCacheEntry]]:
        """Get most frequently accessed entries (candidates for L1/L2 promotion).
        
        Args:
            tenant_id: Optional tenant filter
            limit: Maximum number of entries to return
            min_hits: Minimum hit count threshold
            
        Returns:
            List of (query_id, hit_count, entry) tuples sorted by hits descending
        """
        if not self.ensure_connected():
            return []
        
        try:
            with self.db_manager.session_context() as session:
                query = session.query(DBCacheEntry).filter(
                    DBCacheEntry.l3_cached == True,
                    DBCacheEntry.actual_hits >= min_hits,
                )
                
                if tenant_id:
                    query = query.filter(DBCacheEntry.tenant_id == tenant_id)
                
                # Filter expired entries
                query = query.filter(
                    or_(
                        DBCacheEntry.expires_at.is_(None),
                        DBCacheEntry.expires_at > datetime.utcnow()
                    )
                )
                
                # Order by hits descending
                query = query.order_by(desc(DBCacheEntry.actual_hits))
                
                results = query.limit(limit).all()
                
                return [
                    (db_entry.id, db_entry.actual_hits or 0, self._db_model_to_entry(db_entry))
                    for db_entry in results
                ]
                
        except SQLAlchemyError as e:
            logger.error(f"L3 get_hot_entries failed: {e}")
            self.metrics.errors += 1
            return []
    
    def cleanup_expired(self) -> int:
        """Remove expired entries.
        
        Returns:
            Number of entries removed
        """
        if not self.ensure_connected():
            return 0
        
        try:
            with self.db_manager.session_context() as session:
                deleted = session.query(DBCacheEntry).filter(
                    DBCacheEntry.expires_at.isnot(None),
                    DBCacheEntry.expires_at < datetime.utcnow()
                ).delete()
                
                session.commit()
                
                if deleted > 0:
                    self.metrics.delete_count += deleted
                    logger.info(f"Cleaned up {deleted} expired L3 entries")
                
                return deleted
                
        except SQLAlchemyError as e:
            logger.error(f"L3 cleanup_expired failed: {e}")
            self.metrics.errors += 1
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get L3 cache statistics.
        
        Returns:
            Dictionary of statistics
        """
        stats = self.metrics.to_dict()
        
        if self.ensure_connected():
            try:
                with self.db_manager.session_context() as session:
                    # Total entries
                    total = session.query(DBCacheEntry).filter(
                        DBCacheEntry.l3_cached == True
                    ).count()
                    
                    # Non-expired entries
                    active = session.query(DBCacheEntry).filter(
                        DBCacheEntry.l3_cached == True,
                        or_(
                            DBCacheEntry.expires_at.is_(None),
                            DBCacheEntry.expires_at > datetime.utcnow()
                        )
                    ).count()
                    
                    stats["total_entries"] = total
                    stats["active_entries"] = active
                    stats["expired_entries"] = total - active
                    
            except SQLAlchemyError as e:
                logger.error(f"Failed to get L3 stats: {e}")
                stats["total_entries"] = -1
                stats["error"] = str(e)
        
        return stats
    
    def is_connected(self) -> bool:
        """Check if connected to database.
        
        Returns:
            True if connected
        """
        return self._connected
