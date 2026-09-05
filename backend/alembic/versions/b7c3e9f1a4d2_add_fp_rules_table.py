"""add fp_rules table

Revision ID: b7c3e9f1a4d2
Revises: 0c11d25e9cb6
Create Date: 2026-09-04 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7c3e9f1a4d2'
down_revision: str | None = '0c11d25e9cb6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'fp_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern', sa.String(length=512), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_finding_id', sa.Integer(), nullable=True),
        sa.Column('hit_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_finding_id'], ['findings.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fp_rules_pattern'), 'fp_rules', ['pattern'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_fp_rules_pattern'), table_name='fp_rules')
    op.drop_table('fp_rules')