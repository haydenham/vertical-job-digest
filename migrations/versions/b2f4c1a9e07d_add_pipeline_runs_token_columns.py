"""add pipeline_runs token-usage columns (D-069)

Revision ID: b2f4c1a9e07d
Revises: 7d5b69c46786
Create Date: 2026-07-07 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f4c1a9e07d'
down_revision: Union[str, Sequence[str], None] = '7d5b69c46786'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('input_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('output_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cache_read_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cache_write_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.drop_column('cache_write_tokens')
        batch_op.drop_column('cache_read_tokens')
        batch_op.drop_column('output_tokens')
        batch_op.drop_column('input_tokens')
