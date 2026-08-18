from fastapi import FastAPI
from sqlalchemy import text

from app.db.session import get_engine

app = FastAPI(title="Reddit Promotion Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    db_status = "ok"
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"
    return {"status": "ok", "database": db_status}
