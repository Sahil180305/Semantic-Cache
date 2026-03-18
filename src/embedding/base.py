"""
Embedding Provider Abstraction Layer

This module defines the abstract interface for embedding providers.
All embedding implementations (OpenAI, Cohere, local models, etc.) 
must inherit from EmbeddingProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
import hashlib


class EmbeddingProviderType(str, Enum):
    """Supported embedding provider types."""
    SENTENCE_TRANSFORMER = "sentence_transformer"  # Local embedding model
    OPENAI = "openai"  # OpenAI API
    COHERE = "cohere"  # Cohere API
    HUGGINGFACE = "huggingface"  # HuggingFace Inference API
    AZURE_OPENAI = "azure_openai"  # Azure OpenAI


@dataclass
class EmbeddingRecord:
    """Represents a single embedding result."""
    
    text: str  # Original input text
    embedding: List[float]  # Dense vector (normalized if applicable)
    dimension: int  # Vector dimension
    model: str  # Model identifier
    provider: EmbeddingProviderType  # Which provider generated this
    tokens_used: int  # Token count (relevant for paid APIs)
    generation_time_ms: float  # Time to generate in milliseconds
    timestamp: datetime  # When generated
    metadata: Optional[Dict[str, Any]] = None  # Additional info (e.g., truncation_count)
    
    def __post_init__(self):
        """Validate embedding record after initialization."""
        if len(self.embedding) != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: len(embedding)={len(self.embedding)} "
                f"but dimension={self.dimension}"
            )
        
        # Validate embedding is finite
        if not all(isinstance(x, (int, float)) for x in self.embedding):
            raise ValueError("All embedding values must be numeric")
            
        if any(not (-1e10 < x < 1e10) for x in self.embedding):
            raise ValueError("Embedding contains infinite or NaN values")
    
    @property
    def text_hash(self) -> str:
        """Generate SHA256 hash of the original text for deduplication."""
        return hashlib.sha256(self.text.encode()).hexdigest()


@dataclass
class BatchEmbeddingRequest:
    """Request for batch embedding generation."""
    
    texts: List[str]  # Texts to embed
    model: str  # Model identifier
    normalize: bool = True  # Normalize vectors to unit length
    cache_key_override: Optional[str] = None  # Override automatic cache key
    timeout_seconds: Optional[float] = None  # Request timeout
    
    @property
    def batch_size(self) -> int:
        """Return number of texts in batch."""
        return len(self.texts)
    
    def __post_init__(self):
        """Validate batch request."""
        if not self.texts:
            raise ValueError("Batch must contain at least one text")
        
        if any(not isinstance(t, str) for t in self.texts):
            raise ValueError("All texts must be strings")


class ProviderConfig:
    """Base configuration class for embedding providers."""
    
    def __init__(self, **kwargs):
        """Initialize provider config with arbitrary kwargs."""
        self.config = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return self.config.copy()


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    
    All embedding implementations must:
    1. Inherit from this class
    2. Implement all abstract methods
    3. Handle rate limiting and retries
    4. Track token usage for cost calculation
    5. Normalize vectors appropriately
    """
    
    def __init__(self, model_name: str, config: Optional[ProviderConfig] = None):
        """
        Initialize embedding provider.
        
        Args:
            model_name: Model identifier (e.g., 'text-embedding-3-small')
            config: Optional configuration for the provider
        """
        self.model_name = model_name
        self.config = config or ProviderConfig()
        self._embedding_dimension: Optional[int] = None
        self._is_initialized = False
    
    @property
    def provider_type(self) -> EmbeddingProviderType:
        """Return the provider type."""
        return self._provider_type()
    
    @property
    def embedding_dimension(self) -> int:
        """Get embedding dimension. Must be initialized first."""
        if self._embedding_dimension is None:
            raise RuntimeError(
                f"Provider {self.model_name} must be initialized before accessing embedding_dimension"
            )
        return self._embedding_dimension
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize provider (download models, authenticate with API, etc.).
        
        This is called once before any embeddings are generated.
        Raises:
            Exception: If initialization fails
        """
        pass
    
    @abstractmethod
    async def embed_text(self, text: str) -> EmbeddingRecord:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            EmbeddingRecord with the generated embedding
            
        Raises:
            ValueError: If text is invalid
            RuntimeError: If embedding generation fails
        """
        pass
    
    @abstractmethod
    async def embed_batch(self, request: BatchEmbeddingRequest) -> List[EmbeddingRecord]:
        """
        Generate embeddings for multiple texts in parallel/batch.
        
        Args:
            request: Batch embedding request
            
        Returns:
            List of EmbeddingRecords in same order as input texts
            
        Raises:
            ValueError: If request is invalid
            RuntimeError: If batch embedding fails
        """
        pass
    
    @abstractmethod
    def supports_batch(self) -> bool:
        """Whether this provider supports batch operations."""
        pass
    
    @abstractmethod
    def get_cost_estimate(self, num_tokens: int) -> float:
        """
        Estimate cost for embedding generation.
        
        Args:
            num_tokens: Number of tokens to embed
            
        Returns:
            Estimated cost in USD
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is operational.
        
        Returns:
            True if provider is healthy, False otherwise
        """
        pass
    
    def normalize_embedding(self, embedding: List[float]) -> List[float]:
        """
        Normalize embedding vector to unit length (L2 norm).
        
        Args:
            embedding: Embedding vector
            
        Returns:
            Normalized embedding
        """
        import math
        
        # Calculate L2 norm
        norm = math.sqrt(sum(x ** 2 for x in embedding))
        
        if norm == 0:
            return embedding  # Return as-is if zero vector
        
        # Divide by norm
        return [x / norm for x in embedding]
    
    def __repr__(self) -> str:
        """String representation of provider."""
        return f"{self.__class__.__name__}(model={self.model_name}, type={self.provider_type})"
    
    @staticmethod
    def _provider_type() -> EmbeddingProviderType:
        """Override in subclasses to return provider type."""
        raise NotImplementedError("Subclasses must implement _provider_type()")


class EmbeddingProviderFactory:
    """Factory for creating embedding providers."""
    
    _providers: Dict[EmbeddingProviderType, type] = {}
    
    @classmethod
    def register(cls, provider_type: EmbeddingProviderType, provider_class: type):
        """Register a provider implementation."""
        cls._providers[provider_type] = provider_class
    
    @classmethod
    def create(
        cls,
        provider_type: EmbeddingProviderType,
        model_name: str,
        config: Optional[ProviderConfig] = None
    ) -> EmbeddingProvider:
        """
        Create an embedding provider instance.
        
        Args:
            provider_type: Type of provider
            model_name: Model identifier
            config: Optional provider configuration
            
        Returns:
            EmbeddingProvider instance
            
        Raises:
            ValueError: If provider type not registered
        """
        if provider_type not in cls._providers:
            raise ValueError(f"Unknown provider type: {provider_type}")
        
        provider_class = cls._providers[provider_type]
        return provider_class(model_name, config)
    
    @classmethod
    def get_registered_providers(cls) -> Dict[EmbeddingProviderType, type]:
        """Get all registered provider types."""
        return cls._providers.copy()
