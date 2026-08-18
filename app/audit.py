import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def log_event(
    session: AsyncSession,
    event_type: str,
    *,
    project_id: uuid.UUID | None = None,
    subreddit_name: str | None = None,
    **payload: Any,
) -> AuditLog:
    """Append an immutable audit record (spec section 24). Callers should never
    update or delete an AuditLog row -- only insert."""
    entry = AuditLog(
        event_type=event_type,
        project_id=project_id,
        subreddit_name=subreddit_name,
        payload=payload,
    )
    session.add(entry)
    await session.flush()
    return entry
