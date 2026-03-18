"""
Custom exceptions for Semantic Cache system.

Provides typed exceptions for different error categories across the system.
"""


class SemanticCacheException(Exception):
    """Base exception for all semantic cache errors."""

    def __init__(self, message: str, error_code: str = "SEMANTIC_CACHE_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")


class CacheError(SemanticCacheException):
    """Exceptions related to cache operations."""

    def __init__(self, message: str, error_code: str = "CACHE_ERROR"):
        super().__init__(message, error_code)


class CacheNotFoundError(CacheError):
    """Raised when a cache entry is not found."""

    def __init__(self, cache_key: str):
        super().__init__(f"Cache entry not found: {cache_key}", "CACHE_NOT_FOUND")
        self.cache_key = cache_key


class CacheEvictionError(CacheError):
    """Raised when cache eviction fails."""

    def __init__(self, message: str):
        super().__init__(message, "CACHE_EVICTION_ERROR")


class CacheFullError(CacheError):
    """Raised when cache is full and cannot add new entries."""

    def __init__(self, message: str):
        super().__init__(message, "CACHE_FULL")


class EmbeddingError(SemanticCacheException):
    """Exceptions related to embedding operations."""

    def __init__(self, message: str, error_code: str = "EMBEDDING_ERROR"):
        super().__init__(message, error_code)


class EmbeddingProviderError(EmbeddingError):
    """Raised when embedding provider fails."""

    def __init__(self, provider: str, message: str):
        super().__init__(
            f"Embedding provider '{provider}' error: {message}",
            "EMBEDDING_PROVIDER_ERROR",
        )
        self.provider = provider


class EmbeddingDimensionError(EmbeddingError):
    """Raised when embedding dimension mismatch."""

    def __init__(self, expected: int, got: int):
        super().__init__(
            f"Embedding dimension mismatch: expected {expected}, got {got}",
            "EMBEDDING_DIMENSION_ERROR",
        )
        self.expected = expected
        self.got = got


class SimilarityError(SemanticCacheException):
    """Exceptions related to similarity search operations."""

    def __init__(self, message: str, error_code: str = "SIMILARITY_ERROR"):
        super().__init__(message, error_code)


class SimilarityIndexError(SimilarityError):
    """Raised when similarity index operations fail."""

    def __init__(self, message: str):
        super().__init__(message, "SIMILARITY_INDEX_ERROR")


class SimilaritySearchError(SimilarityError):
    """Raised when similarity search fails."""

    def __init__(self, message: str):
        super().__init__(message, "SIMILARITY_SEARCH_ERROR")


class ConfigurationError(SemanticCacheException):
    """Exceptions related to configuration."""

    def __init__(self, message: str):
        super().__init__(message, "CONFIGURATION_ERROR")


class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration validation fails."""

    def __init__(self, field: str, message: str):
        super().__init__(f"Configuration validation failed for '{field}': {message}")
        self.field = field


class DatabaseError(SemanticCacheException):
    """Exceptions related to database operations."""

    def __init__(self, message: str, error_code: str = "DATABASE_ERROR"):
        super().__init__(message, error_code)


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    def __init__(self, message: str):
        super().__init__(message, "DATABASE_CONNECTION_ERROR")


class DatabaseMigrationError(DatabaseError):
    """Raised when database migration fails."""

    def __init__(self, message: str):
        super().__init__(message, "DATABASE_MIGRATION_ERROR")


class MultiTenancyError(SemanticCacheException):
    """Exceptions related to multi-tenancy operations."""

    def __init__(self, message: str, error_code: str = "MULTI_TENANCY_ERROR"):
        super().__init__(message, error_code)


class TenantNotFoundError(MultiTenancyError):
    """Raised when tenant is not found."""

    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant not found: {tenant_id}", "TENANT_NOT_FOUND")
        self.tenant_id = tenant_id


class QuotaExceededError(MultiTenancyError):
    """Raised when tenant quota is exceeded."""

    def __init__(self, tenant_id: str, quota_type: str, limit: int):
        super().__init__(
            f"Tenant '{tenant_id}' exceeded {quota_type} quota (limit: {limit})",
            "QUOTA_EXCEEDED",
        )
        self.tenant_id = tenant_id
        self.quota_type = quota_type
        self.limit = limit


class ValidationError(SemanticCacheException):
    """Exceptions related to validation."""

    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class InputValidationError(ValidationError):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str):
        super().__init__(f"Input validation failed for '{field}': {message}")
        self.field = field
