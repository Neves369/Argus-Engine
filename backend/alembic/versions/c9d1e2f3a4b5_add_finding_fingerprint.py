"""add finding fingerprint column

Revision ID: c9d1e2f3a4b5
Revises: f3a1b2c4d5e6
Create Date: 2026-09-22 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9d1e2f3a4b5'
down_revision: str | None = 'f3a1b2c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'findings',
        sa.Column('fingerprint', sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f('ix_findings_fingerprint'), 'findings', ['fingerprint'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_findings_fingerprint'), table_name='findings')
    op.drop_column('findings', 'fingerprint')
