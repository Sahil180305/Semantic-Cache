"""
Concrete Embedding Provider Implementations

Provides implementations for:
- SentenceTransformer (local embeddings)
- OpenAI (API-based)
- Cohere (API-based)
- HuggingFace Inference (API-based)
"""

import asyncio
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from src.embedding.base import (
    EmbeddingProvider,
    EmbeddingProviderType,
    EmbeddingRecord,
    BatchEmbeddingRequest,
    ProviderConfig,
    EmbeddingProviderFactory,
)
from src.core.exceptions import EmbeddingError, EmbeddingDimensionError
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Local embedding provider using Sentence Transformers.
    
    No API keys required, runs locally. Good for development and
    models where you have specific privacy requirements.
    
    Supported models:
    - all-MiniLM-L6-v2 (384 dims) - fast, recommended for most use cases
    - all-mpnet-base-v2 (768 dims) - slower but higher quality
    - paraphrase-MiniLM-L6-v2 (384 dims) - optimized for paraphrase detection
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", config: Optional[ProviderConfig] = None):
        """Initialize SentenceTransformer provider."""
        super().__init__(model_name, config)
        self.model = None
        self.device = None  # Will be set to 'cuda' or 'cpu' based on availability
    
    @staticmethod
    def _provider_type() -> EmbeddingProviderType:
        return EmbeddingProviderType.SENTENCE_TRANSFORMER
    
    async def initialize(self) -> None:
        """Download and load the Sentence Transformer model."""
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            
            # Check for GPU availability
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading Sentence Transformer model: {self.model_name} on {self.device}")
            
            # Load model
            self.model = SentenceTransformer(self.model_name)
            self.model.to(self.device)
            
            # Set embedding dimension by testing with dummy text
            dummy_embedding = self.model.encode("test", convert_to_tensor=False)
            self._embedding_dimension = len(dummy_embedding)
            
            self._is_initialized = True
            logger.info(f"Sentence Transformer initialized: dim={self._embedding_dimension}")
            
        except ImportError:
            raise EmbeddingError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers",
                error_code="PROVIDER_IMPORT_ERROR"
            )
        except Exception as e:
            raise EmbeddingError(
                f"Failed to initialize SentenceTransformer: {str(e)}",
                error_code="PROVIDER_INIT_ERROR"
            )
    
    async def embed_text(self, text: str) -> EmbeddingRecord:
        """Generate embedding for a single text."""
        if not self._is_initialized or self.model is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text must be a non-empty string")
        
        try:
            start_time = time.time()
            
            # Generate embedding
            embedding = self.model.encode(text, convert_to_tensor=False)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
            
            # Normalize if configured
            if self.config.to_dict().get('normalize', True):
                embedding_list = self.normalize_embedding(embedding_list)
            
            generation_time_ms = (time.time() - start_time) * 1000
            
            return EmbeddingRecord(
                text=text,
                embedding=embedding_list,
                dimension=self._embedding_dimension,
                model=self.model_name,
                provider=self.provider_type,
                tokens_used=len(text.split()),  # Rough approximation
                generation_time_ms=generation_time_ms,
                timestamp=datetime.utcnow(),
            )
            
        except Exception as e:
            raise EmbeddingError(
                f"Failed to embed text: {str(e)}",
                error_code="EMBEDDING_GENERATION_ERROR"
            )
    
    async def embed_batch(self, request: BatchEmbeddingRequest) -> List[EmbeddingRecord]:
        """Generate embeddings for batch of texts."""
        if not self._is_initialized or self.model is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        
        try:
            start_time = time.time()
            
            # Generate embeddings
            embeddings = self.model.encode(
                request.texts,
                convert_to_tensor=False,
                batch_size=32,
                show_progress_bar=False
            )
            
            records = []
            for text, embedding in zip(request.texts, embeddings):
                embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                
                # Normalize if requested
                if request.normalize:
                    embedding_list = self.normalize_embedding(embedding_list)
                
                records.append(EmbeddingRecord(
                    text=text,
                    embedding=embedding_list,
                    dimension=self._embedding_dimension,
                    model=request.model,
                    provider=self.provider_type,
                    tokens_used=len(text.split()),
                    generation_time_ms=(time.time() - start_time) * 1000 / len(request.texts),
                    timestamp=datetime.utcnow(),
                ))
            
            return records
            
        except Exception as e:
            raise EmbeddingError(
                f"Failed to embed batch: {str(e)}",
                error_code="BATCH_EMBEDDING_ERROR"
            )
    
    def supports_batch(self) -> bool:
        """SentenceTransformer supports batching."""
        return True
    
    def get_cost_estimate(self, num_tokens: int) -> float:
        """Local models have no API cost."""
        return 0.0
    
    async def health_check(self) -> bool:
        """Check if model is loaded and operational."""
        if not self._is_initialized or self.model is None:
            return False
        
        try:
            # Try embedding a test string
            await self.embed_text("health check")
            return True
        except Exception:
            return False


class OpenAIProvider(EmbeddingProvider):
    """
    OpenAI embedding provider (text-embedding-3-small, text-embedding-3-large).
    
    Requires OPENAI_API_KEY environment variable or passed in config.
    
    Pricing (as of 2024):
    - text-embedding-3-small: $0.02 per 1M tokens
    - text-embedding-3-large: $0.13 per 1M tokens
    """
    
    def __init__(self, model_name: str = "text-embedding-3-small", config: Optional[ProviderConfig] = None):
        """Initialize OpenAI provider."""
        super().__init__(model_name, config)
        self.api_key = None
        self.client = None
        self._token_prices = {
            "text-embedding-3-small": 0.02 / 1_000_000,  # $0.02 per 1M tokens
            "text-embedding-3-large": 0.13 / 1_000_000,  # $0.13 per 1M tokens
        }
    
    @staticmethod
    def _provider_type() -> EmbeddingProviderType:
        return EmbeddingProviderType.OPENAI
    
    async def initialize(self) -> None:
        """Initialize OpenAI client."""
        try:
            import os
            from openai import AsyncOpenAI
            
            # Get API key from config or environment
            self.api_key = self.config.to_dict().get('api_key') or os.getenv('OPENAI_API_KEY')
            
            if not self.api_key:
                raise EmbeddingError(
                    "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                    "or pass api_key in config.",
                    error_code="MISSING_API_KEY"
                )
            
            self.client = AsyncOpenAI(api_key=self.api_key)
            
            # Determine embedding dimension
            dimension_map = {
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,
            }
            
            if self.model_name not in dimension_map:
                raise ValueError(f"Unknown OpenAI model: {self.model_name}")
            
            self._embedding_dimension = dimension_map[self.model_name]
            self._is_initialized = True
            logger.info(f"OpenAI provider initialized: model={self.model_name}, dim={self._embedding_dimension}")
            
        except ImportError:
            raise EmbeddingError(
                "openai library not installed. Install with: pip install openai",
                error_code="PROVIDER_IMPORT_ERROR"
            )
        except Exception as e:
            raise EmbeddingError(
                f"Failed to initialize OpenAI provider: {str(e)}",
                error_code="PROVIDER_INIT_ERROR"
            )
    
    async def embed_text(self, text: str) -> EmbeddingRecord:
        """Generate embedding using OpenAI API."""
        if not self._is_initialized or self.client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text must be a non-empty string")
        
        try:
            start_time = time.time()
            
            # Call OpenAI API
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=text,
                encoding_format="float"
            )
            
            embedding = response.data[0].embedding
            generation_time_ms = (time.time() - start_time) * 1000
            tokens_used = response.usage.total_tokens
            
            return EmbeddingRecord(
                text=text,
                embedding=embedding,
                dimension=self._embedding_dimension,
                model=self.model_name,
                provider=self.provider_type,
                tokens_used=tokens_used,
                generation_time_ms=generation_time_ms,
                timestamp=datetime.utcnow(),
                metadata={"api_usage": response.usage.model_dump()}
            )
            
        except Exception as e:
            raise EmbeddingError(
                f"OpenAI API error: {str(e)}",
                error_code="API_ERROR"
            )
    
    async def embed_batch(self, request: BatchEmbeddingRequest) -> List[EmbeddingRecord]:
        """Generate embeddings for batch of texts using OpenAI API."""
        if not self._is_initialized or self.client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        
        try:
            start_time = time.time()
            
            # Call OpenAI API with batch
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=request.texts,
                encoding_format="float"
            )
            
            # Match embeddings to texts (response may reorder)
            embeddings_by_index = {item.index: item.embedding for item in response.data}
            
            records = []
            for i, text in enumerate(request.texts):
                embedding = embeddings_by_index[i]
                
                records.append(EmbeddingRecord(
                    text=text,
                    embedding=embedding,
                    dimension=self._embedding_dimension,
                    model=request.model,
                    provider=self.provider_type,
                    tokens_used=response.usage.total_tokens // len(request.texts),  # Approximate
                    generation_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.utcnow(),
                    metadata={"api_usage": response.usage.model_dump()}
                ))
            
            return records
            
        except Exception as e:
            raise EmbeddingError(
                f"OpenAI batch API error: {str(e)}",
                error_code="BATCH_API_ERROR"
            )
    
    def supports_batch(self) -> bool:
        """OpenAI supports batching."""
        return True
    
    def get_cost_estimate(self, num_tokens: int) -> float:
        """Estimate cost for embedding generation."""
        price_per_token = self._token_prices.get(self.model_name, 0.0)
        return num_tokens * price_per_token
    
    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        if not self._is_initialized or self.client is None:
            return False
        
        try:
            await self.embed_text("health check")
            return True
        except Exception:
            return False


class CohereProvider(EmbeddingProvider):
    """
    Cohere embedding provider (embed-english-v3.0, embed-english-light-v3.0).
    
    Requires COHERE_API_KEY environment variable or passed in config.
    
    Pricing varies by model and plan. Check Cohere documentation for current rates.
    """
    
    def __init__(self, model_name: str = "embed-english-v3.0", config: Optional[ProviderConfig] = None):
        """Initialize Cohere provider."""
        super().__init__(model_name, config)
        self.api_key = None
        self.client = None
    
    @staticmethod
    def _provider_type() -> EmbeddingProviderType:
        return EmbeddingProviderType.COHERE
    
    async def initialize(self) -> None:
        """Initialize Cohere client."""
        try:
            import os
            import cohere
            
            # Get API key from config or environment
            self.api_key = self.config.to_dict().get('api_key') or os.getenv('COHERE_API_KEY')
            
            if not self.api_key:
                raise EmbeddingError(
                    "Cohere API key not provided. Set COHERE_API_KEY environment variable "
                    "or pass api_key in config.",
                    error_code="MISSING_API_KEY"
                )
            
            self.client = cohere.AsyncClientV2(api_key=self.api_key)
            
            # Determine embedding dimension based on model
            if "light" in self.model_name:
                self._embedding_dimension = 384
            else:
                self._embedding_dimension = 1024
            
            self._is_initialized = True
            logger.info(f"Cohere provider initialized: model={self.model_name}, dim={self._embedding_dimension}")
            
        except ImportError:
            raise EmbeddingError(
                "cohere library not installed. Install with: pip install cohere",
                error_code="PROVIDER_IMPORT_ERROR"
            )
        except Exception as e:
            raise EmbeddingError(
                f"Failed to initialize Cohere provider: {str(e)}",
                error_code="PROVIDER_INIT_ERROR"
            )
    
    async def embed_text(self, text: str) -> EmbeddingRecord:
        """Generate embedding using Cohere API."""
        if not self._is_initialized or self.client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text must be a non-empty string")
        
        try:
            start_time = time.time()
            
            # Call Cohere API
            response = await self.client.embed(
                model=self.model_name,
                texts=[text],
                input_type="search_document"
            )
            
            embedding = response.embeddings[0]
            generation_time_ms = (time.time() - start_time) * 1000
            
            return EmbeddingRecord(
                text=text,
                embedding=embedding,
                dimension=self._embedding_dimension,
                model=self.model_name,
                provider=self.provider_type,
                tokens_used=len(text.split()) * 4 // 3,  # Rough approximation
                generation_time_ms=generation_time_ms,
                timestamp=datetime.utcnow(),
            )
            
        except Exception as e:
            raise EmbeddingError(
                f"Cohere API error: {str(e)}",
                error_code="API_ERROR"
            )
    
    async def embed_batch(self, request: BatchEmbeddingRequest) -> List[EmbeddingRecord]:
        """Generate embeddings for batch of texts using Cohere API."""
        if not self._is_initialized or self.client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        
        try:
            start_time = time.time()
            
            # Call Cohere API with batch
            response = await self.client.embed(
                model=self.model_name,
                texts=request.texts,
                input_type="search_document"
            )
            
            records = []
            for text, embedding in zip(request.texts, response.embeddings):
                records.append(EmbeddingRecord(
                    text=text,
                    embedding=embedding,
                    dimension=self._embedding_dimension,
                    model=request.model,
                    provider=self.provider_type,
                    tokens_used=len(text.split()) // len(request.texts),
                    generation_time_ms=(time.time() - start_time) * 1000 / len(request.texts),
                    timestamp=datetime.utcnow(),
                ))
            
            return records
            
        except Exception as e:
            raise EmbeddingError(
                f"Cohere batch API error: {str(e)}",
                error_code="BATCH_API_ERROR"
            )
    
    def supports_batch(self) -> bool:
        """Cohere supports batching."""
        return True
    
    def get_cost_estimate(self, num_tokens: int) -> float:
        """Estimate cost for embedding generation."""
        # Placeholder - actual pricing varies by plan
        # Check https://cohere.com/pricing for current rates
        return 0.0  # Requires checking your specific Cohere plan
    
    async def health_check(self) -> bool:
        """Check if Cohere API is accessible."""
        if not self._is_initialized or self.client is None:
            return False
        
        try:
            await self.embed_text("health check")
            return True
        except Exception:
            return False


# Register providers with factory
EmbeddingProviderFactory.register(
    EmbeddingProviderType.SENTENCE_TRANSFORMER,
    SentenceTransformerProvider
)
EmbeddingProviderFactory.register(
    EmbeddingProviderType.OPENAI,
    OpenAIProvider
)
EmbeddingProviderFactory.register(
    EmbeddingProviderType.COHERE,
    CohereProvider
)
