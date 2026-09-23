"""add target authorization note

Revision ID: d5f6a7b8c9e0
Revises: c9d1e2f3a4b5
Create Date: 2026-09-23 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5f6a7b8c9e0'
down_revision: str | None = 'c9d1e2f3a4b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'targets',
        sa.Column('authorization_note', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('targets', 'authorization_note')
