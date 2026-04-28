from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ingestion_run import IngestionRun
    from app.models.paper import TopicPaper


def utc_now() -> datetime:
    return datetime.now(UTC)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    papers: Mapped[list[TopicPaper]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
