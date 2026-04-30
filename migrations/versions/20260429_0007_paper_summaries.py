"""add paper summaries

Revision ID: 20260429_0007
Revises: 20260429_0006
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260429_0007"
down_revision: str | None = "20260429_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("summary_short", sa.Text(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("why_it_matters", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'completed', 'failed')",
            name=op.f("ck_paper_summaries_status"),
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name=op.f("fk_paper_summaries_paper_id_papers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_summaries")),
        sa.UniqueConstraint(
            "paper_id",
            "input_hash",
            "prompt_version",
            name="uq_paper_summaries_paper_hash_prompt",
        ),
    )
    op.create_index(
        "ix_paper_summaries_paper_id",
        "paper_summaries",
        ["paper_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_summaries_status",
        "paper_summaries",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_paper_summaries_status", table_name="paper_summaries")
    op.drop_index("ix_paper_summaries_paper_id", table_name="paper_summaries")
    op.drop_table("paper_summaries")
