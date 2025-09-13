"""
Database configuration and session management.
Uses async SQLAlchemy for high-performance database operations.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
try:
    # SQLAlchemy 2.x
    from sqlalchemy.ext.asyncio import async_sessionmaker  # type: ignore
except Exception:  # pragma: no cover
    # SQLAlchemy 1.4 fallback
    from sqlalchemy.orm import sessionmaker as _sessionmaker  # type: ignore

    def async_sessionmaker(*args, **kwargs):  # type: ignore
        return _sessionmaker(*args, **kwargs)
from typing import AsyncGenerator
from loguru import logger
from .config import settings
from models.base import Base


# Create async engine
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug,  # Log SQL queries in debug mode
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that yields database sessions.
    
    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            # Use db session here
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error occurred: {e}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    try:
        async with engine.begin() as conn:
            # Import all models to register with metadata
            from models import database  # noqa
            
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_db() -> None:
    """Close database connections."""
    try:
        await engine.dispose()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")
        raise
