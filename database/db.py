"""Async database engine, session factory and initialization helpers."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False, future=True)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def init_db() -> None:
    """Create all tables if they do not exist and apply lightweight migrations."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migration: add columns introduced after the initial release.
        try:
            await conn.execute(
                text("ALTER TABLE transactions ADD COLUMN screenshot_path VARCHAR(512) DEFAULT ''")
            )
            logger.info("Migration applied: transactions.screenshot_path")
        except Exception:
            pass  # column already exists
    logger.info("Database initialized (%s)", settings.database_url)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session inside a context manager with rollback on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Database session rolled back due to an error")
            raise
