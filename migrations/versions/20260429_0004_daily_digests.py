"""add daily digest tables

Revision ID: 20260429_0004
Revises: 20260428_0003
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260429_0004"
down_revision: str | None = "20260428_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="generated", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paper_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "summary_status",
            sa.String(length=32),
            server_default="not_started",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digests")),
        sa.UniqueConstraint("digest_date", name="uq_digests_digest_date"),
    )
    op.create_index("ix_digests_digest_date", "digests", ["digest_date"], unique=False)
    op.create_table(
        "digest_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("digest_id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("is_new", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_saved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_dismissed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["digest_id"],
            ["digests.id"],
            name=op.f("fk_digest_items_digest_id_digests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name=op.f("fk_digest_items_paper_id_papers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_digest_items_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digest_items")),
        sa.UniqueConstraint(
            "digest_id",
            "paper_id",
            "topic_id",
            name="uq_digest_items_digest_paper_topic",
        ),
    )
    op.create_index(
        "ix_digest_items_digest_rank",
        "digest_items",
        ["digest_id", "rank"],
        unique=False,
    )
    op.create_index("ix_digest_items_paper_id", "digest_items", ["paper_id"], unique=False)
    op.create_index("ix_digest_items_topic_id", "digest_items", ["topic_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_digest_items_topic_id", table_name="digest_items")
    op.drop_index("ix_digest_items_paper_id", table_name="digest_items")
    op.drop_index("ix_digest_items_digest_rank", table_name="digest_items")
    op.drop_table("digest_items")
    op.drop_index("ix_digests_digest_date", table_name="digests")
    op.drop_table("digests")
