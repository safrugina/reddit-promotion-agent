import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class ValidationResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "validation_results"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_candidates.id", ondelete="CASCADE")
    )
    rule_compliance_score: Mapped[float] = mapped_column(Float, default=0.0)
    grounding_score: Mapped[float] = mapped_column(Float, default=0.0)
    originality_score: Mapped[float] = mapped_column(Float, default=0.0)
    promotion_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    issues: Mapped[list[Any]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
