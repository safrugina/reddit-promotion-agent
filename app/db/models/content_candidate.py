import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import ApprovalStatus, ContentAngle, ContentType, ValidationStatus


class ContentCandidate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "content_candidates"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reddit_opportunities.id", ondelete="CASCADE")
    )
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType, name="content_type"))
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    body: Mapped[str] = mapped_column(Text)
    cta: Mapped[str | None] = mapped_column(Text, default=None)
    source_link: Mapped[str | None] = mapped_column(String(1000), default=None)
    angle: Mapped[ContentAngle] = mapped_column(Enum(ContentAngle, name="content_angle"))
    rationale: Mapped[str | None] = mapped_column(Text, default=None)
    # ProjectFact ids the generator drew on, for grounding/traceability (spec section 15).
    source_fact_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus, name="validation_status"), default=ValidationStatus.PENDING
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"), default=ApprovalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
