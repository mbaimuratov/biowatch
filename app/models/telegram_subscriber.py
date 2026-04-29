from __future__ import annotations

from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.telegram_delivery import TelegramDigestDelivery
    from app.models.topic import Topic


def utc_now() -> datetime:
    return datetime.now(UTC)


class TelegramSubscriber(Base):
    __tablename__ = "telegram_subscribers"
    __table_args__ = (
        CheckConstraint("article_count > 0", name="ck_telegram_subscribers_article_count_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Rome", nullable=False)
    morning_send_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        default=time(8, 0),
        nullable=False,
    )
    article_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    topics: Mapped[list[Topic]] = relationship(back_populates="subscriber")
    deliveries: Mapped[list[TelegramDigestDelivery]] = relationship(
        back_populates="subscriber",
        cascade="all, delete-orphan",
    )
