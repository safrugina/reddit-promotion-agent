from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AuditLog
from app.errors import RateLimitError

PUBLISHED_EVENT = "PUBLISHED"


async def _count_published(
    session: AsyncSession, since: datetime, subreddit_name: str | None = None
) -> int:
    stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.event_type == PUBLISHED_EVENT, AuditLog.created_at >= since
    )
    if subreddit_name is not None:
        stmt = stmt.where(AuditLog.subreddit_name == subreddit_name)
    result = await session.execute(stmt)
    return result.scalar_one()


async def _last_published_at(session: AsyncSession) -> datetime | None:
    result = await session.execute(
        select(AuditLog.created_at)
        .where(AuditLog.event_type == PUBLISHED_EVENT)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def enforce_rate_limits(session: AsyncSession, subreddit_name: str) -> None:
    """Application-level publishing limits (spec section 23). Raises RateLimitError
    and blocks publishing if any limit would be exceeded."""
    settings = get_settings()
    now = datetime.now(UTC)

    day_count = await _count_published(session, now - timedelta(days=1))
    if day_count >= settings.MAX_PUBLICATIONS_PER_DAY:
        raise RateLimitError(
            f"Daily publication limit reached ({settings.MAX_PUBLICATIONS_PER_DAY}/day)."
        )

    hour_count = await _count_published(session, now - timedelta(hours=1))
    if hour_count >= settings.MAX_PUBLICATIONS_PER_HOUR:
        raise RateLimitError(
            f"Hourly publication limit reached ({settings.MAX_PUBLICATIONS_PER_HOUR}/hour)."
        )

    last_published_at = await _last_published_at(session)
    if last_published_at is not None:
        elapsed = (now - last_published_at).total_seconds()
        if elapsed < settings.MIN_PUBLICATION_INTERVAL_SECONDS:
            wait = settings.MIN_PUBLICATION_INTERVAL_SECONDS - elapsed
            raise RateLimitError(
                f"Minimum interval between publications not met; wait {wait:.0f}s more."
            )

    subreddit_day_count = await _count_published(
        session, now - timedelta(days=1), subreddit_name=subreddit_name
    )
    if subreddit_day_count >= settings.MAX_PUBLICATIONS_PER_SUBREDDIT_PER_DAY:
        raise RateLimitError(
            f"Daily per-subreddit limit reached for r/{subreddit_name} "
            f"({settings.MAX_PUBLICATIONS_PER_SUBREDDIT_PER_DAY}/day)."
        )
