"""add precomputed telegram deliveries

Revision ID: 20260430_0008
Revises: 20260429_0007
Create Date: 2026-04-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260430_0008"
down_revision: str | None = "20260429_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_telegram_digest_deliveries_status"),
        "telegram_digest_deliveries",
        type_="check",
    )
    op.add_column(
        "telegram_digest_deliveries",
        sa.Column("preparation_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_digest_deliveries",
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_digest_deliveries",
        sa.Column("send_queued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_telegram_digest_deliveries_status"),
        "telegram_digest_deliveries",
        "status IN ("
        "'queued', 'preparing', 'ready', 'send_queued', 'sending', "
        "'sent', 'not_ready', 'failed'"
        ")",
    )
    op.add_column(
        "telegram_digest_delivery_items",
        sa.Column("summary_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_telegram_digest_delivery_items_summary_id_paper_summaries"),
        "telegram_digest_delivery_items",
        "paper_summaries",
        ["summary_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "telegram_digest_delivery_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["telegram_digest_deliveries.id"],
            name=op.f(
                "fk_telegram_digest_delivery_messages_delivery_id_telegram_digest_deliveries"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_digest_delivery_messages")),
    )
    op.create_index(
        "ix_telegram_digest_delivery_messages_delivery_position",
        "telegram_digest_delivery_messages",
        ["delivery_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_digest_delivery_messages_delivery_position",
        table_name="telegram_digest_delivery_messages",
    )
    op.drop_table("telegram_digest_delivery_messages")
    op.drop_constraint(
        op.f("fk_telegram_digest_delivery_items_summary_id_paper_summaries"),
        "telegram_digest_delivery_items",
        type_="foreignkey",
    )
    op.drop_column("telegram_digest_delivery_items", "summary_id")
    op.drop_constraint(
        op.f("ck_telegram_digest_deliveries_status"),
        "telegram_digest_deliveries",
        type_="check",
    )
    op.drop_column("telegram_digest_deliveries", "send_queued_at")
    op.drop_column("telegram_digest_deliveries", "prepared_at")
    op.drop_column("telegram_digest_deliveries", "preparation_started_at")
    op.create_check_constraint(
        op.f("ck_telegram_digest_deliveries_status"),
        "telegram_digest_deliveries",
        "status IN ('queued', 'sending', 'sent', 'failed')",
    )
