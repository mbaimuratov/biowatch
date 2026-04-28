"""add ingestion run job id

Revision ID: 20260427_0002
Revises: 20260427_0001
Create Date: 2026-04-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260427_0002"
down_revision: str | None = "20260427_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("job_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_runs", "job_id")
