"""
Redis Configuration for L2 Cache

Handles Redis connection pooling, retry logic, serialization, and configuration.
"""

import json
import pickle
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Type, Union
from enum import Enum

import redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError


logger = logging.getLogger(__name__)


class SerializationFormat(Enum):
    """Serialization format options."""
    JSON = "json"
    PICKLE = "pickle"


@dataclass
class RedisConfig:
    """Redis connection and behavior configuration."""
    
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    
    # Connection pool settings
    max_connections: int = 50
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    socket_keepalive_options: Optional[dict] = None
    
    # Retry settings
    retry_on_timeout: bool = True
    max_retries: int = 3
    retry_delay_ms: int = 100
    
    # Serialization
    serialization_format: SerializationFormat = SerializationFormat.JSON
    
    # Key settings
    key_prefix: str = "cache:"
    default_ttl_seconds: Optional[int] = 86400  # 24 hours
    
    # Performance
    enable_pipelining: bool = True
    pipeline_batch_size: int = 100
    
    def validate(self) -> bool:
        """Validate configuration."""
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {self.port}")
        
        if self.db < 0 or self.db > 15:
            raise ValueError(f"DB must be between 0 and 15, got {self.db}")
        
        if self.max_connections < 1:
            raise ValueError(f"max_connections must be >= 1, got {self.max_connections}")
        
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        
        return True
    
    def get_connection_url(self) -> str:
        """Get connection URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class RedisConnectionManager:
    """Manages Redis connection pooling and lifecycle."""
    
    def __init__(self, config: RedisConfig):
        """Initialize connection manager.
        
        Args:
            config: Redis configuration
        """
        config.validate()
        self.config = config
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._connected = False
    
    def connect(self) -> redis.Redis:
        """Establish Redis connection.
        
        Returns:
            Redis client instance
            
        Raises:
            RedisConnectionError: If connection fails after retries
        """
        if self._client is not None:
            return self._client
        
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                self._pool = ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    max_connections=self.config.max_connections,
                    socket_connect_timeout=self.config.socket_connect_timeout,
                    socket_keepalive=self.config.socket_keepalive,
                    socket_keepalive_options=self.config.socket_keepalive_options,
                    retry_on_timeout=self.config.retry_on_timeout,
                )
                
                self._client = redis.Redis(connection_pool=self._pool)
                
                # Test connection
                self._client.ping()
                
                self._connected = True
                logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
                return self._client
                
            except (RedisError, RedisConnectionError) as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config.max_retries:
                    import time
                    time.sleep(self.config.retry_delay_ms / 1000.0)
        
        raise RedisConnectionError(
            f"Failed to connect to Redis after {self.config.max_retries + 1} attempts: {last_error}"
        )
    
    def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._client = None
                self._pool = None
                self._connected = False
    
    def get_client(self) -> redis.Redis:
        """Get Redis client, connecting if needed.
        
        Returns:
            Connected Redis client
        """
        if self._client is None:
            return self.connect()
        return self._client
    
    def is_connected(self) -> bool:
        """Check if connected."""
        if not self._connected or self._client is None:
            return False
        
        try:
            self._client.ping()
            return True
        except Exception:
            self._connected = False
            return False
    
    def health_check(self) -> bool:
        """Perform health check.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.is_connected():
                return False
            
            # Check basic operations
            test_key = f"{self.config.key_prefix}test"
            self._client.setex(test_key, 10, "health_check")
            self._client.delete(test_key)
            
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


class RedisSerializer:
    """Handles serialization/deserialization for Redis storage."""
    
    def __init__(self, format: SerializationFormat = SerializationFormat.JSON):
        """Initialize serializer.
        
        Args:
            format: Serialization format to use
        """
        self.format = format
    
    def serialize(self, data: Any) -> Union[str, bytes]:
        """Serialize data for Redis storage.
        
        Args:
            data: Data to serialize
            
        Returns:
            Serialized data (str for JSON, bytes for pickle)
        """
        if self.format == SerializationFormat.JSON:
            return self._serialize_json(data)
        elif self.format == SerializationFormat.PICKLE:
            return self._serialize_pickle(data)
        else:
            raise ValueError(f"Unknown format: {self.format}")
    
    def deserialize(self, data: Union[str, bytes], expected_type: Optional[Type] = None) -> Any:
        """Deserialize data from Redis.
        
        Args:
            data: Serialized data
            expected_type: Expected type for validation
            
        Returns:
            Deserialized data
        """
        if self.format == SerializationFormat.JSON:
            return self._deserialize_json(data)
        elif self.format == SerializationFormat.PICKLE:
            return self._deserialize_pickle(data)
        else:
            raise ValueError(f"Unknown format: {self.format}")
    
    @staticmethod
    def _serialize_json(data: Any) -> str:
        """Serialize to JSON."""
        try:
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization failed: {e}")
            raise
    
    @staticmethod
    def _deserialize_json(data: Union[str, bytes]) -> Any:
        """Deserialize from JSON."""
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON deserialization failed: {e}")
            raise
    
    @staticmethod
    def _serialize_pickle(data: Any) -> bytes:
        """Serialize to pickle."""
        try:
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        except pickle.PicklingError as e:
            logger.error(f"Pickle serialization failed: {e}")
            raise
    
    @staticmethod
    def _deserialize_pickle(data: Union[str, bytes]) -> Any:
        """Deserialize from pickle."""
        try:
            return pickle.loads(data)
        except pickle.UnpicklingError as e:
            logger.error(f"Pickle deserialization failed: {e}")
            raise


class RedisPipelineManager:
    """Manages batch operations using Redis pipelines."""
    
    def __init__(self, client: redis.Redis, batch_size: int = 100):
        """Initialize pipeline manager.
        
        Args:
            client: Redis client
            batch_size: Operations per pipeline
        """
        self.client = client
        self.batch_size = batch_size
        self.pipeline = None
        self.operation_count = 0
    
    def start(self) -> None:
        """Start a new pipeline."""
        self.pipeline = self.client.pipeline()
        self.operation_count = 0
    
    def add_operation(self, operation: callable, *args, **kwargs) -> None:
        """Add operation to pipeline.
        
        Args:
            operation: Redis operation (e.g., client.set)
            args: Positional arguments
            kwargs: Keyword arguments
        """
        if self.pipeline is None:
            self.start()
        
        operation(*args, **kwargs)
        self.operation_count += 1
        
        if self.operation_count >= self.batch_size:
            self.flush()
    
    def flush(self) -> None:
        """Execute pipeline and reset."""
        if self.pipeline is not None:
            try:
                self.pipeline.execute()
            finally:
                self.pipeline = None
                self.operation_count = 0
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.flush()
