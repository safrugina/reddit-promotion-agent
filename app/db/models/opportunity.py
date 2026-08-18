import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import OpportunityStatus


class RedditOpportunity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reddit_opportunities"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    subreddit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subreddits.id", ondelete="CASCADE")
    )
    reddit_post_id: Mapped[str | None] = mapped_column(String(50), default=None)
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    url: Mapped[str | None] = mapped_column(String(1000), default=None)
    # Individual scoring components (spec section 12) are stored alongside the
    # combined score so the user can see why an opportunity was ranked as it was.
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    discussion_score: Mapped[float] = mapped_column(Float, default=0.0)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)  # audience_fit
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)  # promotion_risk
    topical_fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    contribution_potential_score: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)  # weighted combination
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, name="opportunity_status"), default=OpportunityStatus.NEW
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
