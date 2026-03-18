"""
SQLAlchemy models for Semantic Cache system.

Defines database schema for cache entries, metadata, and operational metrics.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    Text,
    LargeBinary,
    Index,
    ForeignKey,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Tenant(Base):
    """Tenant model for multi-tenancy support."""

    __tablename__ = "tenants"

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False)

    # Quotas
    max_cache_entries = Column(Integer, default=100000, nullable=False)
    max_qps = Column(Integer, default=1000, nullable=False)
    max_storage_gb = Column(Float, default=10.0, nullable=False)

    # Relationships
    cache_entries = relationship("CacheEntry", back_populates="tenant")
    metrics = relationship("TenantMetrics", back_populates="tenant")

    __table_args__ = (Index("idx_tenant_is_active", "is_active"),)


class CacheEntry(Base):
    """Main cache entry model storing queries, embeddings, and responses."""

    __tablename__ = "cache_entries"

    id = Column(String(255), primary_key=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    
    # Query information
    query_text = Column(Text, nullable=False)
    query_hash = Column(String(255), nullable=False, unique=False)
    
    # Embedding
    embedding = Column(LargeBinary, nullable=False)  # Serialized vector
    embedding_model = Column(String(255), nullable=False)
    embedding_dimension = Column(Integer, nullable=False)
    
    # Response
    response = Column(Text, nullable=False)
    response_metadata = Column(JSON, nullable=True)
    
    # Classification
    domain = Column(String(100), nullable=True)  # medical, legal, ecommerce, general
    similarity_threshold_used = Column(Float, nullable=True)
    
    # Metrics & Cost
    generation_cost = Column(Float, nullable=True)  # Cost to generate this entry
    estimated_future_hits = Column(Integer, default=1)  # ML prediction
    actual_hits = Column(Integer, default=0)
    last_hit_at = Column(DateTime, nullable=True)
    
    # Cache levels
    l1_cached = Column(Boolean, default=False, nullable=False)
    l2_cached = Column(Boolean, default=False, nullable=False)
    l3_cached = Column(Boolean, default=False, nullable=False)
    
    # Temporal
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # TTL
    
    # Relationships
    tenant = relationship("Tenant", back_populates="cache_entries")

    __table_args__ = (
        Index("idx_tenant_query_hash", "tenant_id", "query_hash"),
        Index("idx_domain", "domain"),
        Index("idx_l1_cached", "l1_cached"),
        Index("idx_l2_cached", "l2_cached"),
        Index("idx_created_at", "created_at"),
        Index("idx_expires_at", "expires_at"),
    )


class CacheMetadata(Base):
    """Metadata for cache entry lookups and filtering."""

    __tablename__ = "cache_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_entry_id = Column(String(255), ForeignKey("cache_entries.id"), nullable=False)
    
    # Metadata for filtering
    key = Column(String(255), nullable=False)
    value = Column(String(1024), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_cache_entry_id", "cache_entry_id"),
        Index("idx_metadata_key_value", "key", "value"),
    )


class EmbeddingModel(Base):
    """Track embedding models used in the system."""

    __tablename__ = "embedding_models"

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False)  # local, openai, cohere, huggingface
    dimension = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(100), nullable=True)
    
    # Configuration
    is_active = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_embedding_model_provider", "provider"),)


class TenantMetrics(Base):
    """Operational metrics per tenant."""

    __tablename__ = "tenant_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    
    # Cache statistics
    total_queries = Column(Integer, default=0)
    cache_hits = Column(Integer, default=0)
    cache_misses = Column(Integer, default=0)
    
    # Performance
    avg_latency_ms = Column(Float, default=0.0)
    p95_latency_ms = Column(Float, default=0.0)
    p99_latency_ms = Column(Float, default=0.0)
    
    # Cost tracking
    total_cached_entries = Column(Integer, default=0)
    total_cost_saved = Column(Float, default=0.0)
    
    # Temporal
    measured_at = Column(DateTime, default=datetime.utcnow)
    period_start = Column(DateTime, nullable=True)  # Start of measurement period
    period_end = Column(DateTime, nullable=True)  # End of measurement period
    
    # Relationship
    tenant = relationship("Tenant", back_populates="metrics")

    __table_args__ = (
        Index("idx_tenant_id_measured_at", "tenant_id", "measured_at"),
    )


class DomainClassifier(Base):
    """Domain classification results for queries."""

    __tablename__ = "domain_classifiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(String(255), ForeignKey("cache_entries.id"), nullable=False)
    
    # Classification
    predicted_domain = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=False)  # 0-1
    
    # Ground truth (if available)
    actual_domain = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_query_id", "query_id"),
        Index("idx_predicted_domain", "predicted_domain"),
    )


class SimilaritySearch(Base):
    """Log of similarity searches for analytics and debugging."""

    __tablename__ = "similarity_searches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)
    
    # Search query
    query_text = Column(Text, nullable=False)
    query_embedding = Column(LargeBinary, nullable=False)
    
    # Results
    top_k = Column(Integer, default=5)
    cache_entry_id = Column(String(255), nullable=True)  # Best match if any
    similarity_score = Column(Float, nullable=True)
    threshold_used = Column(Float, nullable=False)
    threshold_met = Column(Boolean, default=False)
    
    # Temporal
    searched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_tenant_searched_at", "tenant_id", "searched_at"),
        Index("idx_threshold_met", "threshold_met"),
    )


class SystemConfig(Base):
    """System-wide configuration stored in database."""

    __tablename__ = "system_config"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(255), nullable=True)
