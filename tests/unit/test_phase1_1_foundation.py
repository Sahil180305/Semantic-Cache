"""
Unit tests for Phase 1.1 - Foundation & Infrastructure.

Tests for core data models, configuration, logging, and database setup.
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import yaml

from src.core.exceptions import (
    ConfigurationError,
    ConfigurationValidationError,
    DatabaseError,
)
from src.core.config import (
    ConfigLoader,
    SemanticCacheConfig,
    L1CacheConfig,
    EmbeddingConfig,
    SimilarityConfig,
)
from src.utils.logging import get_logger, configure_logging, StructuredLogger
from src.core.database import DatabaseManager
from src.core.schemas import QueryRequest, CacheResponse, CacheStats


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_base_exception(self):
        """Test base semantic cache exception."""
        from src.core.exceptions import SemanticCacheException

        exc = SemanticCacheException("Test error", "TEST_ERROR")
        assert exc.message == "Test error"
        assert exc.error_code == "TEST_ERROR"
        assert "[TEST_ERROR]" in str(exc)

    def test_cache_errors(self):
        """Test cache-related exceptions."""
        from src.core.exceptions import CacheNotFoundError, CacheFullError

        exc = CacheNotFoundError("key123")
        assert exc.cache_key == "key123"
        assert "CACHE_NOT_FOUND" in str(exc)

        exc2 = CacheFullError("Cache is at capacity")
        assert "CACHE_FULL" in str(exc2)

    def test_embedding_errors(self):
        """Test embedding-related exceptions."""
        from src.core.exceptions import EmbeddingDimensionError

        exc = EmbeddingDimensionError(384, 512)
        assert exc.expected == 384
        assert exc.got == 512
        assert "384" in str(exc)

    def test_configuration_errors(self):
        """Test configuration exceptions."""
        exc = ConfigurationValidationError("field_name", "Invalid value")
        assert exc.field == "field_name"
        assert "field_name" in str(exc)


class TestLogging:
    """Test logging utilities."""

    def test_get_logger(self):
        """Test getting a logger instance."""
        logger = get_logger(__name__)
        assert isinstance(logger, StructuredLogger)
        assert logger._logger.name == __name__

    def test_logger_context(self):
        """Test setting logging context."""
        logger = get_logger(__name__)
        logger.set_context(
            request_id_val="req123",
            tenant_id_val="tenant456",
            user_id_val="user789",
        )
        # Context is set (verified through logging output)
        logger.clear_context()

    def test_configure_logging(self, tmp_path):
        """Test logging configuration."""
        log_file = tmp_path / "test.log"
        configure_logging(level="DEBUG", format_type="json", log_file=str(log_file))
        logger = get_logger("test_logger")
        logger.info("Test message")
        assert log_file.exists()

    def test_logger_methods(self):
        """Test all logger methods."""
        logger = get_logger("test_logger")
        # These should not raise
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")


class TestDataModels:
    """Test SQLAlchemy data models."""

    def test_tenant_model(self):
        """Test Tenant model definition."""
        from src.core.models import Tenant

        tenant = Tenant(
            id="tenant_test",
            name="Test Tenant",
            max_cache_entries=50000,
            is_active=True,  # Must be explicitly set when creating instance
        )
        assert tenant.id == "tenant_test"
        assert tenant.is_active is True

    def test_cache_entry_model(self):
        """Test CacheEntry model structure."""
        from src.core.models import CacheEntry

        entry = CacheEntry(
            id="entry_1",
            tenant_id="tenant_1",
            query_text="What is ML?",
            query_hash="abc123",
            embedding=b"fake_embedding",
            embedding_model="test-model",
            embedding_dimension=384,
            response="Machine learning is...",
            l1_cached=False,  # Must be explicitly set when creating instance
            l2_cached=False,
            l3_cached=False,            actual_hits=0,  # Must be explicitly set when creating instance
            estimated_future_hits=1,        )
        assert entry.query_text == "What is ML?"
        assert entry.l1_cached is False
        assert entry.actual_hits == 0


class TestPydanticSchemas:
    """Test Pydantic schema validation."""

    def test_query_request_validation(self):
        """Test QueryRequest schema validation."""
        req = QueryRequest(
            query_text="What is AI?",
            tenant_id="tenant_1",
        )
        assert req.query_text == "What is AI?"
        assert req.user_id is None

        # With optional fields
        req2 = QueryRequest(
            query_text="Query",
            tenant_id="tenant_1",
            user_id="user_1",
            domain="general",
            similarity_threshold=0.90,
        )
        assert req2.domain == "general"
        assert req2.similarity_threshold == 0.90

    def test_query_request_validation_fails(self):
        """Test QueryRequest validation failures."""
        with pytest.raises(ValueError):
            QueryRequest(
                query_text="",  # Empty not allowed
                tenant_id="tenant_1",
            )

        with pytest.raises(ValueError):
            QueryRequest(
                query_text="Query",
                tenant_id="tenant_1",
                similarity_threshold=1.5,  # Out of range
            )

    def test_cache_response_schema(self):
        """Test CacheResponse schema."""
        resp = CacheResponse(
            response_text="Response text",
            is_cached=True,
            cache_level="L1",
            similarity_score=0.95,
            latency_ms=2.5,
            processing_time_ms=10.0,
        )
        assert resp.is_cached is True
        assert resp.cache_level == "L1"

    def test_cache_stats_schema(self):
        """Test CacheStats schema."""
        stats = CacheStats(
            total_queries=1000,
            cache_hits=600,
            cache_misses=400,
            hit_rate=0.6,
            avg_latency_ms=25.5,
            p95_latency_ms=45.3,
            p99_latency_ms=95.2,
            total_cached_entries=5000,
            l1_entries=3000,
            l2_entries=2000,
            total_cost_saved=150.50,
        )
        assert stats.hit_rate == 0.6
        assert stats.total_cached_entries == 5000


class TestConfiguration:
    """Test configuration loading and validation."""

    def test_l1_cache_config_validation(self):
        """Test L1 cache config validation."""
        # Valid config
        config = L1CacheConfig(max_entries=50000)
        config.validate()  # Should not raise

        # Invalid config
        with pytest.raises(ConfigurationValidationError):
            config = L1CacheConfig(max_entries=500)  # Too small
            config.validate()

    def test_embedding_config_validation(self):
        """Test embedding config validation."""
        # Valid config
        config = EmbeddingConfig(provider="local")
        config.validate()

        # Invalid provider
        with pytest.raises(ConfigurationValidationError):
            config = EmbeddingConfig(provider="invalid")
            config.validate()

    def test_similarity_config_validation(self):
        """Test similarity config validation."""
        # Valid config
        config = SimilarityConfig(default_threshold=0.85)
        config.validate()

        # Invalid threshold
        with pytest.raises(ConfigurationValidationError):
            config = SimilarityConfig(default_threshold=1.5)
            config.validate()

    def test_full_config_validation(self):
        """Test full configuration validation."""
        config = SemanticCacheConfig()
        config.validate()  # Should pass with defaults

    def test_config_loader_from_yaml(self, monkeypatch):
        """Test loading configuration from YAML file."""
        # Clear environment variables that might override YAML config
        monkeypatch.delenv("API_HOST", raising=False)
        monkeypatch.delenv("API_PORT", raising=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test YAML file
            config_file = Path(tmpdir) / "test_config.yaml"
            config_data = {
                "api": {"host": "127.0.0.1", "port": 8080},
                "cache": {
                    "l1": {"max_entries": 50000},
                    "l2": {"max_entries": 500000},
                },
            }
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            # Load configuration
            loader = ConfigLoader(config_path=config_file)
            config = loader.load()

            assert config.api.host == "127.0.0.1"
            assert config.api.port == 8080
            assert config.cache.l1.max_entries == 50000

    def test_config_loader_env_override(self, monkeypatch):
        """Test environment variable override."""
        monkeypatch.setenv("API_PORT", "9000")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        loader = ConfigLoader()
        config = loader.load()

        assert config.api.port == 9000
        assert config.monitoring.log_level == "DEBUG"

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = SemanticCacheConfig()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert "api" in config_dict
        assert "cache" in config_dict
        assert "embedding" in config_dict


class TestDatabase:
    """Test database manager and setup."""

    def test_database_manager_creation(self, monkeypatch):
        """Test database manager initialization."""
        # Use SQLite for testing
        monkeypatch.setenv(
            "DATABASE_URL",
            "sqlite:///:memory:",
        )

        from src.core.config import DatabaseConfig

        config = DatabaseConfig(url="sqlite:///:memory:")
        db_manager = DatabaseManager(config)

        assert db_manager.engine is not None
        assert db_manager.session_factory is not None

    def test_database_session_creation(self, monkeypatch):
        """Test getting database sessions."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

        from src.core.config import DatabaseConfig

        config = DatabaseConfig(url="sqlite:///:memory:")
        db_manager = DatabaseManager(config)

        session = db_manager.get_session()
        assert session is not None
        session.close()

    def test_database_context_manager(self, monkeypatch):
        """Test session context manager."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

        from src.core.config import DatabaseConfig

        config = DatabaseConfig(url="sqlite:///:memory:")
        db_manager = DatabaseManager(config)

        with db_manager.session_context() as session:
            assert session is not None


class TestIntegration:
    """Integration tests for Phase 1.1 components."""

    def test_config_and_logging_integration(self, monkeypatch):
        """Test configuration working with logging."""
        configure_logging(level="INFO", format_type="json")
        logger = get_logger("integration_test")

        loader = ConfigLoader()
        config = loader.load()

        logger.info("Configuration loaded", extra={"config": config.to_dict()})
        assert config is not None

    def test_full_initialization_flow(self, monkeypatch):
        """Test complete initialization flow."""
        # Setup
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        # Configure logging
        configure_logging(level="DEBUG")
        logger = get_logger("test")

        # Load config
        loader = ConfigLoader()
        config = loader.load()

        # Initialize database
        from src.core.database import init_database
        db_manager = init_database(config)

        # Create tables
        db_manager.create_all_tables()

        # Verify
        assert db_manager.engine is not None
        assert config.monitoring.log_level == "DEBUG"

        logger.info("Full initialization test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
