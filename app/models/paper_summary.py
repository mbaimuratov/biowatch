from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.paper import Paper


class PaperSummary(Base):
    __tablename__ = "paper_summaries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'completed', 'failed')",
            name="ck_paper_summaries_status",
        ),
        UniqueConstraint(
            "paper_id",
            "input_hash",
            "prompt_version",
            name="uq_paper_summaries_paper_hash_prompt",
        ),
        Index("ix_paper_summaries_paper_id", "paper_id"),
        Index("ix_paper_summaries_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="summaries")

    def normalized_key_points(self) -> list[str]:
        value: Any = self.key_points
        if not isinstance(value, list):
            return []
        return [str(point) for point in value if str(point).strip()]
