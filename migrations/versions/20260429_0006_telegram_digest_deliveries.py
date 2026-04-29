"""add telegram digest deliveries

Revision ID: 20260429_0006
Revises: 20260429_0005
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260429_0006"
down_revision: str | None = "20260429_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_digest_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("digest_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed')",
            name=op.f("ck_telegram_digest_deliveries_status"),
        ),
        sa.ForeignKeyConstraint(
            ["digest_id"],
            ["digests.id"],
            name=op.f("fk_telegram_digest_deliveries_digest_id_digests"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["telegram_subscribers.id"],
            name=op.f("fk_telegram_digest_deliveries_subscriber_id_telegram_subscribers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_digest_deliveries")),
    )
    op.create_index(
        "ix_telegram_digest_deliveries_subscriber_scheduled",
        "telegram_digest_deliveries",
        ["subscriber_id", "scheduled_for"],
        unique=True,
    )
    op.create_index(
        "ix_telegram_digest_deliveries_status",
        "telegram_digest_deliveries",
        ["status"],
        unique=False,
    )
    op.create_table(
        "telegram_digest_delivery_items",
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["telegram_digest_deliveries.id"],
            name=op.f("fk_telegram_digest_delivery_items_delivery_id_telegram_digest_deliveries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name=op.f("fk_telegram_digest_delivery_items_paper_id_papers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_telegram_digest_delivery_items_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "delivery_id",
            "paper_id",
            "topic_id",
            name=op.f("pk_telegram_digest_delivery_items"),
        ),
    )
    op.create_index(
        "ix_telegram_digest_delivery_items_delivery_position",
        "telegram_digest_delivery_items",
        ["delivery_id", "position"],
        unique=True,
    )
    op.create_index(
        "ix_telegram_digest_delivery_items_paper_id",
        "telegram_digest_delivery_items",
        ["paper_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_digest_delivery_items_topic_id",
        "telegram_digest_delivery_items",
        ["topic_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_digest_delivery_items_topic_id",
        table_name="telegram_digest_delivery_items",
    )
    op.drop_index(
        "ix_telegram_digest_delivery_items_paper_id",
        table_name="telegram_digest_delivery_items",
    )
    op.drop_index(
        "ix_telegram_digest_delivery_items_delivery_position",
        table_name="telegram_digest_delivery_items",
    )
    op.drop_table("telegram_digest_delivery_items")
    op.drop_index("ix_telegram_digest_deliveries_status", table_name="telegram_digest_deliveries")
    op.drop_index(
        "ix_telegram_digest_deliveries_subscriber_scheduled",
        table_name="telegram_digest_deliveries",
    )
    op.drop_table("telegram_digest_deliveries")
