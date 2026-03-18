"""
Embedding Module

Provides embedding generation with support for multiple providers:
- Sentence Transformers (local)
- OpenAI (API)
- Cohere (API)
- HuggingFace Inference (API)

Usage:
    from src.embedding.service import EmbeddingService
    from src.embedding.base import EmbeddingProviderType, ProviderConfig
    
    service = EmbeddingService(
        provider_type=EmbeddingProviderType.SENTENCE_TRANSFORMER,
        model_name="all-MiniLM-L6-v2"
    )
    await service.initialize()
    
    record = await service.embed_text("Hello, world!")
    print(record.embedding)  # [0.123, -0.456, ...]
"""

from src.embedding.base import (
    EmbeddingProvider,
    EmbeddingProviderType,
    EmbeddingRecord,
    BatchEmbeddingRequest,
    ProviderConfig,
    EmbeddingProviderFactory,
)
from src.embedding.providers import (
    SentenceTransformerProvider,
    OpenAIProvider,
    CohereProvider,
)
from src.embedding.service import (
    EmbeddingService,
    EmbeddingCache,
    RetryConfig,
    EmbeddingMetrics,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderType",
    "EmbeddingRecord",
    "BatchEmbeddingRequest",
    "ProviderConfig",
    "EmbeddingProviderFactory",
    "SentenceTransformerProvider",
    "OpenAIProvider",
    "CohereProvider",
    "EmbeddingService",
    "EmbeddingCache",
    "RetryConfig",
    "EmbeddingMetrics",
]
