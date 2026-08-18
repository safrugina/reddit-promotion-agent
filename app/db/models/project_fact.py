import uuid
from typing import Any

from sqlalchemy import JSON, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import FactType


class ProjectFact(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_facts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    fact: Mapped[str] = mapped_column(Text)
    source_chunk_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    fact_type: Mapped[FactType] = mapped_column(Enum(FactType, name="fact_type"))
