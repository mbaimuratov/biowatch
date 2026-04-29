from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.paper import Paper
    from app.models.topic import Topic


def utc_now() -> datetime:
    return datetime.now(UTC)


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint("digest_date", name="uq_digests_digest_date"),
        Index("ix_digests_digest_date", "digest_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="generated", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paper_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_status: Mapped[str] = mapped_column(
        String(32),
        default="not_started",
        nullable=False,
    )

    items: Mapped[list[DigestItem]] = relationship(
        back_populates="digest",
        cascade="all, delete-orphan",
        order_by="DigestItem.rank",
    )


class DigestItem(Base):
    __tablename__ = "digest_items"
    __table_args__ = (
        UniqueConstraint(
            "digest_id",
            "paper_id",
            "topic_id",
            name="uq_digest_items_digest_paper_topic",
        ),
        Index("ix_digest_items_digest_rank", "digest_id", "rank"),
        Index("ix_digest_items_paper_id", "paper_id"),
        Index("ix_digest_items_topic_id", "topic_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_id: Mapped[int] = mapped_column(
        ForeignKey("digests.id", ondelete="CASCADE"),
        nullable=False,
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    digest: Mapped[Digest] = relationship(back_populates="items")
    paper: Mapped[Paper] = relationship()
    topic: Mapped[Topic] = relationship()

    @property
    def topic_name(self) -> str:
        return self.topic.name
