from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ingestion_run import IngestionRun
    from app.models.paper import TopicPaper
    from app.models.telegram_subscriber import TelegramSubscriber


def utc_now() -> datetime:
    return datetime.now(UTC)


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint(
            "ingestion_frequency IN ('daily', 'weekly')",
            name="ck_topics_ingestion_frequency",
        ),
        CheckConstraint("max_papers_per_run > 0", name="ck_topics_max_papers_per_run_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_subscribers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ingestion_frequency: Mapped[str] = mapped_column(
        String(32),
        default="daily",
        nullable=False,
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_successful_ingestion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_papers_per_run: Mapped[int] = mapped_column(Integer, default=25, nullable=False)

    subscriber: Mapped[TelegramSubscriber | None] = relationship(back_populates="topics")

    papers: Mapped[list[TopicPaper]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
