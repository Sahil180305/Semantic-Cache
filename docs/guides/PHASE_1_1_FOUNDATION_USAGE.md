"""
Quick reference and usage examples for Phase 1.1 Foundation components.

This guide demonstrates how to use exceptions, logging, configuration, and database setup.
"""

# ============================================================================
# 1. EXCEPTION HANDLING
# ============================================================================

# Example: Using custom exceptions
from src.core.exceptions import (
    CacheNotFoundError,
    EmbeddingDimensionError,
    QuotaExceededError,
    ConfigurationError,
)

# Type-safe exception handling with context
try:
    raise CacheNotFoundError("query_hash_123")
except CacheNotFoundError as e:
    print(f"Cache miss: {e.cache_key}")
    # Handle gracefully

# ============================================================================
# 2. STRUCTURED LOGGING
# ============================================================================

from src.utils.logging import get_logger, configure_logging

# Configure logging once at app startup
configure_logging(level="INFO", format_type="json", log_file="./logs/app.log")

# Get logger in any module
logger = get_logger(__name__)

# Log with context
logger.set_context(request_id_val="req_123", tenant_id_val="tenant_456")
logger.info("Processing query")
# Outputs JSON: {"timestamp": "...", "request_id": "req_123", "tenant_id": "tenant_456", ...}

# Log with extra data
logger.info("Cache operation", extra={"entries": 5000, "hit_rate": 0.62})

# Usage patterns
logger.debug("Debug information")
logger.info("Important event")
logger.warning("Potential issue")
logger.error("Error occurred")
logger.critical("Critical failure")

# Clear context when done
logger.clear_context()

# ============================================================================
# 3. CONFIGURATION MANAGEMENT
# ============================================================================

from src.core.config import ConfigLoader, get_config
from pathlib import Path

# Option 1: Load default configuration
config = get_config()
print(f"API runs on {config.api.host}:{config.api.port}")
print(f"Embedding model: {config.embedding.model}")
print(f"Default similarity threshold: {config.similarity.default_threshold}")

# Option 2: Load from custom YAML
config = get_config(config_path=Path("config/production.yaml"))

# Option 3: Manual configuration with validation
from src.core.config import SemanticCacheConfig, EmbeddingConfig
custom_config = SemanticCacheConfig()
custom_config.embedding = EmbeddingConfig(
    model="sentence-transformers/all-mpnet-base-v2",
    provider="local",
    dimension=768
)
custom_config.validate()  # Raises ConfigurationValidationError if invalid

# Access configuration
cache_config = config.cache
print(f"L1 max entries: {cache_config.l1.max_entries}")  # 100,000
print(f"L2 max entries: {cache_config.l2.max_entries}")  # 1,000,000

embedding_config = config.embedding
print(f"Batch size: {embedding_config.batch_size}")  # 32

similarity_config = config.similarity
print(f"Medical threshold: {similarity_config.adaptive_thresholds['medical']}")  # 0.95
print(f"E-commerce threshold: {similarity_config.adaptive_thresholds['ecommerce']}")  # 0.80

# ============================================================================
# 4. DATABASE INITIALIZATION
# ============================================================================

from src.core.database import init_database, get_session, get_db_manager
from src.core.models import Tenant, CacheEntry

# At application startup
config = get_config()
db_manager = init_database(config)

# Create all tables
db_manager.create_all_tables()

# Get a new session
session = db_manager.get_session()

# Use context manager for automatic cleanup
from src.core.database import get_db_manager
db_manager = get_db_manager()

with db_manager.session_context() as session:
    # Create a tenant
    tenant = Tenant(
        id="customer_123",
        name="Customer Company",
        max_cache_entries=100000
    )
    session.add(tenant)
    session.commit()

# Query operations
with db_manager.session_context() as session:
    # Find tenant
    tenant = session.query(Tenant).filter(Tenant.id == "customer_123").first()
    
    # Update tenant
    tenant.max_qps = 2000
    session.commit()
    
    # Check tenant metrics
    print(f"Tenant {tenant.name}: {tenant.max_cache_entries} max entries")

# ============================================================================
# 5. API REQUEST/RESPONSE VALIDATION
# ============================================================================

from src.core.schemas import QueryRequest, CacheResponse, CacheStats

# Validate incoming request
request_data = {
    "query_text": "What is machine learning?",
    "tenant_id": "tenant_123",
    "domain": "general",
    "similarity_threshold": 0.85
}
request = QueryRequest(**request_data)

# Build response
response = CacheResponse(
    response_text="Machine learning is a subset of AI...",
    is_cached=True,
    cache_level="L1",
    similarity_score=0.92,
    latency_ms=2.5,
    processing_time_ms=15.3,
    cost_saved=0.002
)

# Generate cache statistics
stats = CacheStats(
    total_queries=1000,
    cache_hits=620,
    cache_misses=380,
    hit_rate=0.62,
    avg_latency_ms=25.5,
    p95_latency_ms=45.3,
    p99_latency_ms=95.2,
    total_cached_entries=5000,
    l1_entries=3000,
    l2_entries=2000,
    total_cost_saved=150.50
)

# Convert to JSON (for API responses)
response_json = response.model_dump_json()
stats_json = stats.model_dump_json()

# ============================================================================
# 6. COMPLETE INITIALIZATION EXAMPLE
# ============================================================================

def initialize_application():
    """Complete application initialization example."""
    
    # 1. Configure logging
    configure_logging(level="INFO", format_type="json")
    logger = get_logger(__name__)
    
    try:
        # 2. Load configuration
        config = get_config()
        logger.info("Configuration loaded")
        
        # 3. Initialize database
        db_manager = init_database(config)
        db_manager.create_all_tables()
        logger.info("Database initialized")
        
        # 4. Create default tenant
        with db_manager.session_context() as session:
            tenant = Tenant(
                id="default",
                name="Default Tenant",
                max_cache_entries=config.multi_tenancy.default_quota["max_entries"]
            )
            session.add(tenant)
            logger.info("Default tenant created")
        
        logger.info("Application initialization complete")
        return db_manager
        
    except Exception as e:
        logger.error(f"Initialization failed: {e}", extra={"error_type": type(e).__name__})
        raise

# ============================================================================
# 7. ENVIRONMENT CONFIGURATION
# ============================================================================

# Create .env file in project root:
"""
# .env file example
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false

REDIS_HOST=localhost
REDIS_PORT=6379

DATABASE_URL=postgresql://user:password@localhost/semantic_cache

EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_PROVIDER=local

SIMILARITY_THRESHOLD=0.85

LOG_LEVEL=INFO
"""

# These environment variables automatically override YAML configuration

# ============================================================================
# 8. TESTING PATTERNS
# ============================================================================

# Example test file patterns from test_phase1_1_foundation.py:

import pytest
from src.core.config import ConfigLoader
from src.core.database import DatabaseManager

def test_configuration_loading():
    """Test configuration loads and validates."""
    loader = ConfigLoader()
    config = loader.load()
    assert config is not None
    assert config.api.port > 0

def test_database_initialization(monkeypatch):
    """Test database manager with SQLite (for testing)."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    
    from src.core.config import DatabaseConfig
    db_config = DatabaseConfig(url="sqlite:///:memory:")
    db_manager = DatabaseManager(db_config)
    
    assert db_manager.engine is not None
    
    with db_manager.session_context() as session:
        from src.core.models import Tenant
        tenant = Tenant(id="test", name="Test")
        session.add(tenant)
    
    with db_manager.session_context() as session:
        tenant = session.query(Tenant).filter(Tenant.id == "test").first()
        assert tenant is not None

# ============================================================================
# SUMMARY
# ============================================================================

"""
Phase 1.1 Foundation Components:

1. EXCEPTIONS
   - Type-safe error handling
   - Hierarchical exception classes
   - Error codes for programmatic handling
   
2. LOGGING
   - Structured JSON logging
   - Context tracking (request_id, tenant_id, etc.)
   - File and console handlers
   
3. DATA MODELS
   - 9 SQLAlchemy ORM models
   - Tenant management
   - Cache entry storage
   - Metrics tracking
   
4. API SCHEMAS
   - Pydantic validation models
   - Request/response validation
   - Type-safe API contracts
   
5. CONFIGURATION
   - YAML file loading
   - Environment variable override
   - Validation on startup
   - Dataclass-based configuration
   
6. DATABASE
   - SQLAlchemy setup
   - Connection pooling
   - Session management
   - Slow query logging
   - Transaction support

Ready for Phase 1.2: Embedding Service Layer
"""
