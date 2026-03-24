"""
Database configuration and session management for Semantic Cache.

Provides SQLAlchemy engine, session factory, and database utilities.
"""

from typing import Optional, Generator
from contextlib import contextmanager
from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import NullPool

from src.core.config import SemanticCacheConfig, DatabaseConfig
from src.core.exceptions import DatabaseConnectionError, DatabaseError
from src.core.models import Base
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, config: DatabaseConfig):
        """Initialize database manager.

        Args:
            config: Database configuration

        Raises:
            DatabaseConnectionError: If database connection fails
        """
        self.config = config
        self._engine = None
        self._session_factory = None
        self._scoped_session = None

    @property
    def engine(self):
        """Get or create database engine."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> sessionmaker:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
        return self._session_factory

    @property
    def scoped_session(self) -> scoped_session:
        """Get scoped session."""
        if self._scoped_session is None:
            self._scoped_session = scoped_session(self.session_factory)
        return self._scoped_session

    def _create_engine(self):
        """Create SQLAlchemy engine with proper configuration.

        Returns:
            SQLAlchemy Engine instance

        Raises:
            DatabaseConnectionError: If engine creation fails
        """
        try:
            logger.info(f"Creating database engine: {self._mask_url(self.config.url)}")

            # Determine pool class based on connection string
            pool_class = pool.QueuePool
            if "sqlite" in self.config.url:
                pool_class = NullPool

            # Build engine kwargs - SQLite doesn't support pool_size/max_overflow
            engine_kwargs = {
                "echo": self.config.echo,
                "pool_recycle": 3600,  # Recycle connections every hour
            }
            
            # Only add pooling options for non-SQLite databases
            if "sqlite" not in self.config.url:
                engine_kwargs["pool_size"] = self.config.pool_size
                engine_kwargs["max_overflow"] = self.config.max_overflow
                engine_kwargs["poolclass"] = pool_class
            else:
                engine_kwargs["poolclass"] = NullPool
            
            # Add connection timeout for PostgreSQL (psycopg2 uses connect_timeout)
            if "postgresql" in self.config.url:
                engine_kwargs["connect_args"] = {"connect_timeout": 30}
            
            engine = create_engine(self.config.url, **engine_kwargs)

            # Register event listeners
            self._register_event_listeners(engine)

            # Test connection
            self._test_connection(engine)

            logger.info("Database engine created successfully")
            return engine

        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise DatabaseConnectionError(f"Failed to create database engine: {e}")

    @staticmethod
    def _register_event_listeners(engine) -> None:
        """Register SQLAlchemy event listeners for logging and monitoring.

        Args:
            engine: SQLAlchemy Engine instance
        """
        # Log slow queries
        @event.listens_for(engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if context is not None:
                context._query_start_time = getattr(context, "_query_start_time", None)
                if context._query_start_time is None:
                    import time
                    context._query_start_time = time.time()

        @event.listens_for(engine, "after_cursor_execute")
        def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if context is not None and hasattr(context, "_query_start_time"):
                import time
                elapsed = time.time() - context._query_start_time
                if elapsed > 1.0:  # Log queries taking > 1 second
                    logger.warning(
                        f"Slow query detected ({elapsed:.2f}s): {statement[:100]}..."
                    )

    @staticmethod
    def _test_connection(engine) -> None:
        """Test database connection.

        Args:
            engine: SQLAlchemy Engine instance

        Raises:
            DatabaseConnectionError: If connection test fails
        """
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection test passed")
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise DatabaseConnectionError(f"Failed to connect to database: {e}")

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy Session instance
        """
        return self.session_factory()

    @contextmanager
    def session_context(self) -> Generator[Session, None, None]:
        """Context manager for database sessions.

        Yields:
            SQLAlchemy Session instance

        Cleans up session properly on exit.
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()

    def create_all_tables(self) -> None:
        """Create all database tables.

        Raises:
            DatabaseError: If table creation fails
        """
        try:
            logger.info("Creating database tables...")
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise DatabaseError(f"Failed to create tables: {e}")

    def drop_all_tables(self) -> None:
        """Drop all database tables (for testing/cleanup).

        Raises:
            DatabaseError: If table drop fails
        """
        try:
            logger.warning("Dropping all database tables...")
            Base.metadata.drop_all(self.engine)
            logger.info("Database tables dropped")
        except Exception as e:
            logger.error(f"Failed to drop tables: {e}")
            raise DatabaseError(f"Failed to drop tables: {e}")

    def close(self) -> None:
        """Close database connections.

        Properly closes scoped session and engine.
        """
        try:
            if self._scoped_session is not None:
                self._scoped_session.remove()
            if self._engine is not None:
                self._engine.dispose()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask sensitive information in database URL for logging.

        Args:
            url: Database URL

        Returns:
            Masked URL safe for logging
        """
        # Replace password with ****
        import re
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def init_database(config: SemanticCacheConfig) -> DatabaseManager:
    """Initialize database manager with configuration.

    Args:
        config: Semantic cache configuration

    Returns:
        Initialized DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(config.database)
    return _db_manager


def get_db_manager() -> DatabaseManager:
    """Get global database manager instance.

    Returns:
        DatabaseManager instance

    Raises:
        DatabaseError: If database manager not initialized
    """
    if _db_manager is None:
        raise DatabaseError("Database manager not initialized. Call init_database() first.")
    return _db_manager


def get_session() -> Session:
    """Get a new database session.

    Returns:
        SQLAlchemy Session instance
    """
    return get_db_manager().get_session()


def get_scoped_session() -> scoped_session:
    """Get thread-local scoped session.

    Returns:
        Scoped session instance
    """
    return get_db_manager().scoped_session
