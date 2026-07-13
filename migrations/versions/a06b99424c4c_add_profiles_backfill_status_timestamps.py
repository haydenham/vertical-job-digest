"""add profiles backfill status timestamps

Revision ID: a06b99424c4c
Revises: b2f4c1a9e07d
Create Date: 2026-07-13 13:26:12.302618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a06b99424c4c'
down_revision: Union[str, Sequence[str], None] = 'b2f4c1a9e07d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the two nullable backfill stamps (D-082) — additive, no table rebuild needed."""
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('backfill_started_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('backfill_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_column('backfill_completed_at')
        batch_op.drop_column('backfill_started_at')
