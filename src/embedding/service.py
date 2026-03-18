"""
Embedding Service Orchestrator

Provides high-level embedding generation with:
- Provider abstraction (local, OpenAI, Cohere, etc.)
- Automatic batching for efficiency
- Caching to avoid re-embedding same texts
- Retry logic with exponential backoff
- Cost tracking and quota management
- Monitoring and metrics
"""

import asyncio
import time
import hashlib
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from src.embedding.base import (
    EmbeddingProvider,
    EmbeddingProviderType,
    EmbeddingRecord,
    BatchEmbeddingRequest,
    ProviderConfig,
    EmbeddingProviderFactory,
)
from src.core.exceptions import (
    EmbeddingError,
    EmbeddingDimensionError,
    CacheError,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingCache:
    """Simple in-memory cache for embeddings."""
    
    def __init__(self, max_size: int = 100000, ttl_seconds: Optional[int] = None):
        """
        Initialize embedding cache.
        
        Args:
            max_size: Maximum number of cached embeddings
            ttl_seconds: Time-to-live in seconds (None = no expiration)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[EmbeddingRecord, float]] = {}  # hash -> (record, timestamp)
    
    def _get_text_hash(self, text: str) -> str:
        """Generate hash key for text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def get(self, text: str) -> Optional[EmbeddingRecord]:
        """Get cached embedding for text."""
        hash_key = self._get_text_hash(text)
        
        if hash_key not in self.cache:
            return None
        
        record, timestamp = self.cache[hash_key]
        
        # Check TTL
        if self.ttl_seconds and (time.time() - timestamp) > self.ttl_seconds:
            del self.cache[hash_key]
            return None
        
        return record
    
    def set(self, text: str, record: EmbeddingRecord) -> None:
        """Cache an embedding record."""
        if len(self.cache) >= self.max_size:
            # Simple eviction: remove oldest entry
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        hash_key = self._get_text_hash(text)
        self.cache[hash_key] = (record, time.time())
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cached_entries": len(self.cache),
            "max_size": self.max_size,
            "usage_percent": (len(self.cache) / self.max_size * 100) if self.max_size > 0 else 0,
        }


class RetryConfig:
    """Configuration for retry logic."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_ms: float = 100.0,
        max_delay_ms: float = 5000.0,
        backoff_factor: float = 2.0,
        retryable_errors: Optional[List[str]] = None,
    ):
        """
        Initialize retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts
            initial_delay_ms: Initial delay between retries in milliseconds
            max_delay_ms: Maximum delay between retries
            backoff_factor: Multiplier for exponential backoff
            retryable_errors: List of error codes to retry on
        """
        self.max_retries = max_retries
        self.initial_delay_ms = initial_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_factor = backoff_factor
        self.retryable_errors = retryable_errors or [
            "API_ERROR",
            "RATE_LIMITED",
            "TEMPORARY_ERROR",
        ]
    
    def get_delay_ms(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = self.initial_delay_ms * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay_ms)


class EmbeddingMetrics:
    """Track embedding generation metrics."""
    
    def __init__(self):
        """Initialize metrics."""
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_time_ms = 0.0
        self.errors = defaultdict(int)
        self.start_time = datetime.utcnow()
    
    def record_request(
        self,
        tokens: int,
        cost: float,
        time_ms: float,
        is_cache_hit: bool,
        error: Optional[str] = None,
    ):
        """Record metrics for an embedding request."""
        self.total_requests += 1
        self.total_tokens += tokens
        self.total_cost += cost
        self.total_time_ms += time_ms
        
        if is_cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        
        if error:
            self.errors[error] += 1
    
    def get_stats(self) -> Dict[str, any]:
        """Get aggregated metrics."""
        elapsed_minutes = (datetime.utcnow() - self.start_time).total_seconds() / 60
        
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": self.cache_hits / self.total_requests if self.total_requests > 0 else 0,
            "total_time_ms": self.total_time_ms,
            "avg_time_ms": self.total_time_ms / self.total_requests if self.total_requests > 0 else 0,
            "requests_per_minute": self.total_requests / elapsed_minutes if elapsed_minutes > 0 else 0,
            "errors": dict(self.errors),
        }


class EmbeddingService:
    """
    High-level embedding service.
    
    Handles:
    - Provider management and switching
    - Embedding caching
    - Automatic batching
    - Retry logic with backoff
    - Cost tracking
    - Metrics and monitoring
    """
    
    def __init__(
        self,
        provider_type: EmbeddingProviderType,
        model_name: str,
        config: Optional[ProviderConfig] = None,
        cache_config: Optional[Dict] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize embedding service.
        
        Args:
            provider_type: Type of embedding provider
            model_name: Model identifier
            config: Provider configuration
            cache_config: Cache configuration (size, ttl)
            retry_config: Retry configuration
        """
        self.provider = EmbeddingProviderFactory.create(provider_type, model_name, config)
        
        # Initialize cache
        cache_size = cache_config.get("max_size", 100000) if cache_config else 100000
        cache_ttl = cache_config.get("ttl_seconds") if cache_config else None
        self.cache = EmbeddingCache(max_size=cache_size, ttl_seconds=cache_ttl)
        
        # Initialize retry config
        self.retry_config = retry_config or RetryConfig()
        
        # Initialize metrics
        self.metrics = EmbeddingMetrics()
        
        # Pending batch info
        self.pending_batch: Dict[str, str] = {}  # text -> task_id for deduplication
        self.pending_batch_lock = asyncio.Lock()
        
        self._is_initialized = False
    
    async def initialize(self) -> None:
        """Initialize the embedding provider."""
        if self._is_initialized:
            return
        
        logger.info(f"Initializing embedding service with provider: {self.provider}")
        await self.provider.initialize()
        self._is_initialized = True
        logger.info(f"Embedding service initialized: dimension={self.provider.embedding_dimension}")
    
    async def embed_text(self, text: str) -> EmbeddingRecord:
        """
        Generate embedding for a single text with caching.
        
        Args:
            text: Text to embed
            
        Returns:
            EmbeddingRecord
            
        Raises:
            EmbeddingError: If embedding fails
        """
        if not self._is_initialized:
            raise RuntimeError("Service not initialized. Call initialize() first.")
        
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text must be a non-empty string")
        
        start_time = time.time()
        is_cache_hit = False
        
        try:
            # Check cache first
            cached = self.cache.get(text)
            if cached:
                is_cache_hit = True
                generation_time_ms = (time.time() - start_time) * 1000
                self.metrics.record_request(
                    tokens=cached.tokens_used,
                    cost=0,  # Cached, no cost
                    time_ms=generation_time_ms,
                    is_cache_hit=True,
                )
                logger.debug(f"Cache hit for text: {text[:50]}...")
                return cached
            
            # Not in cache - generate embedding with retries
            record = await self._embed_with_retries(text)
            
            # Cache the result
            self.cache.set(text, record)
            
            generation_time_ms = (time.time() - start_time) * 1000
            cost = self.provider.get_cost_estimate(record.tokens_used)
            
            self.metrics.record_request(
                tokens=record.tokens_used,
                cost=cost,
                time_ms=generation_time_ms,
                is_cache_hit=False,
            )
            
            logger.debug(f"Generated embedding for text: {text[:50]}... (dim={len(record.embedding)})")
            return record
            
        except EmbeddingError as e:
            generation_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_request(
                tokens=0,
                cost=0,
                time_ms=generation_time_ms,
                is_cache_hit=False,
                error=e.error_code,
            )
            raise
    
    async def embed_batch(self, texts: List[str], normalize: bool = True) -> List[EmbeddingRecord]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            normalize: Whether to normalize embeddings
            
        Returns:
            List of EmbeddingRecords in same order as input
            
        Raises:
            EmbeddingError: If batch embedding fails
        """
        if not self._is_initialized:
            raise RuntimeError("Service not initialized. Call initialize() first.")
        
        if not texts:
            raise ValueError("Batch must contain at least one text")
        
        if not all(isinstance(t, str) for t in texts):
            raise ValueError("All texts must be strings")
        
        logger.info(f"Processing batch of {len(texts)} texts")
        start_time = time.time()
        
        # Separate cached and uncached texts
        results = [None] * len(texts)
        uncached_indices = []
        cache_hits = 0
        
        for i, text in enumerate(texts):
            cached = self.cache.get(text)
            if cached:
                results[i] = cached
                cache_hits += 1
            else:
                uncached_indices.append(i)
        
        logger.info(f"Cache hits: {cache_hits}/{len(texts)}")
        
        # Process uncached texts
        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            
            request = BatchEmbeddingRequest(
                texts=uncached_texts,
                model=self.provider.model_name,
                normalize=normalize,
            )
            
            records = await self._embed_batch_with_retries(request)
            
            # Cache results and place in correct positions
            for idx, record in zip(uncached_indices, records):
                results[idx] = record
                self.cache.set(texts[idx], record)
        
        # Record metrics
        generation_time_ms = (time.time() - start_time) * 1000
        total_tokens = sum(r.tokens_used for r in results)
        total_cost = sum(self.provider.get_cost_estimate(r.tokens_used) for r in results)
        
        self.metrics.record_request(
            tokens=total_tokens,
            cost=total_cost,
            time_ms=generation_time_ms,
            is_cache_hit=cache_hits > 0,
        )
        
        logger.info(f"Batch processing completed: {generation_time_ms:.2f}ms, cost=${total_cost:.6f}")
        return results
    
    async def _embed_with_retries(self, text: str) -> EmbeddingRecord:
        """Embed text with retry logic."""
        last_error = None
        
        for attempt in range(self.retry_config.max_retries):
            try:
                return await self.provider.embed_text(text)
            except EmbeddingError as e:
                last_error = e
                
                # Check if we should retry
                if e.error_code not in self.retry_config.retryable_errors:
                    raise
                
                # Calculate backoff delay
                if attempt < self.retry_config.max_retries - 1:
                    delay_ms = self.retry_config.get_delay_ms(attempt)
                    logger.warning(
                        f"Embedding failed (attempt {attempt + 1}/{self.retry_config.max_retries}): "
                        f"{e.message}. Retrying in {delay_ms}ms..."
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
        
        raise last_error or EmbeddingError(
            "Embedding failed after retries",
            error_code="RETRY_EXHAUSTED"
        )
    
    async def _embed_batch_with_retries(self, request: BatchEmbeddingRequest) -> List[EmbeddingRecord]:
        """Embed batch with retry logic."""
        last_error = None
        
        for attempt in range(self.retry_config.max_retries):
            try:
                return await self.provider.embed_batch(request)
            except EmbeddingError as e:
                last_error = e
                
                # Check if we should retry
                if e.error_code not in self.retry_config.retryable_errors:
                    raise
                
                # Calculate backoff delay
                if attempt < self.retry_config.max_retries - 1:
                    delay_ms = self.retry_config.get_delay_ms(attempt)
                    logger.warning(
                        f"Batch embedding failed (attempt {attempt + 1}/{self.retry_config.max_retries}): "
                        f"{e.message}. Retrying in {delay_ms}ms..."
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
        
        raise last_error or EmbeddingError(
            "Batch embedding failed after retries",
            error_code="BATCH_RETRY_EXHAUSTED"
        )
    
    async def health_check(self) -> bool:
        """Check if embedding service is healthy."""
        if not self._is_initialized:
            return False
        
        return await self.provider.health_check()
    
    def get_metrics(self) -> Dict:
        """Get service metrics."""
        return {
            "embedding_service": self.metrics.get_stats(),
            "cache": self.cache.get_stats(),
            "provider": {
                "type": self.provider.provider_type,
                "model": self.provider.model_name,
                "dimension": self.provider.embedding_dimension,
            }
        }
    
    async def clear_cache(self) -> None:
        """Clear all cached embeddings."""
        self.cache.cache.clear()
        logger.info("Embedding cache cleared")
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"EmbeddingService(provider={self.provider.provider_type}, "
            f"model={self.provider.model_name}, initialized={self._is_initialized})"
        )
