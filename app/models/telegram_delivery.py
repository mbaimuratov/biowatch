from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.digest import Digest
    from app.models.paper import Paper
    from app.models.telegram_subscriber import TelegramSubscriber
    from app.models.topic import Topic


class TelegramDigestDelivery(Base):
    __tablename__ = "telegram_digest_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed')",
            name="ck_telegram_digest_deliveries_status",
        ),
        Index(
            "ix_telegram_digest_deliveries_subscriber_scheduled",
            "subscriber_id",
            "scheduled_for",
            unique=True,
        ),
        Index("ix_telegram_digest_deliveries_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_subscribers.id", ondelete="CASCADE"),
        nullable=False,
    )
    digest_id: Mapped[int | None] = mapped_column(
        ForeignKey("digests.id", ondelete="SET NULL"),
        nullable=True,
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscriber: Mapped[TelegramSubscriber] = relationship(back_populates="deliveries")
    digest: Mapped[Digest | None] = relationship()
    items: Mapped[list[TelegramDigestDeliveryItem]] = relationship(
        back_populates="delivery",
        cascade="all, delete-orphan",
        order_by="TelegramDigestDeliveryItem.position",
    )


class TelegramDigestDeliveryItem(Base):
    __tablename__ = "telegram_digest_delivery_items"
    __table_args__ = (
        Index(
            "ix_telegram_digest_delivery_items_delivery_position",
            "delivery_id",
            "position",
            unique=True,
        ),
        Index("ix_telegram_digest_delivery_items_paper_id", "paper_id"),
        Index("ix_telegram_digest_delivery_items_topic_id", "topic_id"),
    )

    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("telegram_digest_deliveries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    delivery: Mapped[TelegramDigestDelivery] = relationship(back_populates="items")
    paper: Mapped[Paper] = relationship()
    topic: Mapped[Topic] = relationship()
