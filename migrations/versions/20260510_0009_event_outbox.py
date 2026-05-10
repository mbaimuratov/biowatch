"""add event outbox

Revision ID: 20260510_0009
Revises: 20260430_0008
Create Date: 2026-05-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_0009"
down_revision: str | None = "20260430_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'published')",
            name=op.f("ck_event_outbox_status"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_event_outbox_attempts_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_outbox")),
    )
    op.create_index(
        op.f("ix_event_outbox_event_type"),
        "event_outbox",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_outbox_status"),
        "event_outbox",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_event_outbox_status_id",
        "event_outbox",
        ["status", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_event_outbox_status_id", table_name="event_outbox")
    op.drop_index(op.f("ix_event_outbox_status"), table_name="event_outbox")
    op.drop_index(op.f("ix_event_outbox_event_type"), table_name="event_outbox")
    op.drop_table("event_outbox")
