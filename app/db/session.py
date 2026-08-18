from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # NullPool: no cross-invocation connection pooling. asyncpg connections
        # are bound to the event loop that created them, and short-lived
        # processes (CLI commands, tests) each run their own `asyncio.run()`
        # loop, so pooled connections must not outlive a single loop.
        _engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the cached engine and drop cached state.

    asyncpg connections are bound to the event loop they were created on, so a
    process that runs multiple independent `asyncio.run()` calls (e.g. the CLI,
    or tests invoking CLI commands back to back) must dispose the engine between
    loops or reused connections raise "Event loop is closed".
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
