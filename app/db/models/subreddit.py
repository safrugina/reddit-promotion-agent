from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class Subreddit(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "subreddits"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    rules: Mapped[list[Any]] = mapped_column(JSON, default=list)
    restrictions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    culture_summary: Mapped[str | None] = mapped_column(Text, default=None)
    activity_score: Mapped[float | None] = mapped_column(Float, default=None)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
