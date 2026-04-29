"""add telegram subscribers

Revision ID: 20260429_0005
Revises: 20260429_0004
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260429_0005"
down_revision: str | None = "20260429_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_subscribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="Europe/Rome", nullable=False),
        sa.Column(
            "morning_send_time",
            sa.Time(timezone=False),
            server_default="08:00:00",
            nullable=False,
        ),
        sa.Column("article_count", sa.Integer(), server_default="5", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "article_count > 0",
            name=op.f("ck_telegram_subscribers_article_count_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_subscribers")),
        sa.UniqueConstraint(
            "telegram_chat_id", name=op.f("uq_telegram_subscribers_telegram_chat_id")
        ),
    )
    op.alter_column(
        "topics",
        "max_results_per_run",
        new_column_name="max_papers_per_run",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.drop_constraint("ck_topics_max_results_per_run_positive", "topics", type_="check")
    op.create_check_constraint(
        "ck_topics_max_papers_per_run_positive",
        "topics",
        "max_papers_per_run > 0",
    )
    op.add_column("topics", sa.Column("subscriber_id", sa.Integer(), nullable=True))
    op.add_column("topics", sa.Column("priority", sa.Integer(), server_default="0", nullable=False))
    op.create_foreign_key(
        op.f("fk_topics_subscriber_id_telegram_subscribers"),
        "topics",
        "telegram_subscribers",
        ["subscriber_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_topics_subscriber_id"), "topics", ["subscriber_id"], unique=False)
    op.create_index(
        "ix_topics_subscriber_enabled_priority",
        "topics",
        ["subscriber_id", "enabled", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_topics_subscriber_enabled_priority", table_name="topics")
    op.drop_index(op.f("ix_topics_subscriber_id"), table_name="topics")
    op.drop_constraint(
        op.f("fk_topics_subscriber_id_telegram_subscribers"), "topics", type_="foreignkey"
    )
    op.drop_column("topics", "priority")
    op.drop_column("topics", "subscriber_id")
    op.drop_constraint("ck_topics_max_papers_per_run_positive", "topics", type_="check")
    op.create_check_constraint(
        "ck_topics_max_results_per_run_positive",
        "topics",
        "max_papers_per_run > 0",
    )
    op.alter_column(
        "topics",
        "max_papers_per_run",
        new_column_name="max_results_per_run",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.drop_table("telegram_subscribers")
