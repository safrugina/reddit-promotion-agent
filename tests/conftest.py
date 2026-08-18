import asyncio

import pytest
from sqlalchemy import text

from app.db.session import dispose_engine as _dispose_engine
from app.db.session import get_engine


def _database_reachable() -> bool:
    async def _check() -> bool:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            await _dispose_engine()

    return asyncio.run(_check())


@pytest.fixture(scope="session")
def database_available() -> bool:
    return _database_reachable()


def pytest_collection_modifyitems(config, items):
    if _database_reachable():
        return
    skip_db = pytest.mark.skip(reason="PostgreSQL is not reachable (start `docker compose up -d`)")
    for item in items:
        if "requires_db" in item.keywords:
            item.add_marker(skip_db)
