"""add topic scheduling metadata

Revision ID: 20260428_0003
Revises: 20260427_0002
Create Date: 2026-04-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260428_0003"
down_revision: str | None = "20260427_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column(
            "ingestion_frequency",
            sa.String(length=32),
            server_default="daily",
            nullable=False,
        ),
    )
    op.add_column(
        "topics",
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "topics",
        sa.Column("last_successful_ingestion_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "topics",
        sa.Column("max_results_per_run", sa.Integer(), server_default="25", nullable=False),
    )
    op.create_check_constraint(
        "ck_topics_ingestion_frequency",
        "topics",
        "ingestion_frequency IN ('daily', 'weekly')",
    )
    op.create_check_constraint(
        "ck_topics_max_results_per_run_positive",
        "topics",
        "max_results_per_run > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_topics_max_results_per_run_positive", "topics", type_="check")
    op.drop_constraint("ck_topics_ingestion_frequency", "topics", type_="check")
    op.drop_column("topics", "max_results_per_run")
    op.drop_column("topics", "last_successful_ingestion_at")
    op.drop_column("topics", "last_ingested_at")
    op.drop_column("topics", "ingestion_frequency")
