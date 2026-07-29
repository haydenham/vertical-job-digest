"""add pipeline_runs postings_reopened

Revision ID: 79c5ef618c90
Revises: a7c15e0b93d2
Create Date: 2026-07-28 19:54:39.172995

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79c5ef618c90'
down_revision: Union[str, Sequence[str], None] = 'a7c15e0b93d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Additive and nullable (D-103): existing rows keep NULL rather than a misleading 0, since the
    reopen count for a run that predates this column is genuinely unknown, not zero.
    """
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('postings_reopened', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.drop_column('postings_reopened')
