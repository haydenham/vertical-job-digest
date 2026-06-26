"""add users and profiles.user_id

Revision ID: 7d5b69c46786
Revises: d30501b4c8ab
Create Date: 2026-06-26 10:48:07.641939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d5b69c46786'
down_revision: Union[str, Sequence[str], None] = 'd30501b4c8ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # UTCDateTime renders as its impl (DateTime(timezone=True)) — same convention as the initial
    # schema + source_updated_at migrations; the TypeDecorator only normalizes tz at the app boundary.
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('google_sub', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('google_sub')
    )
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_profiles_user_id_users', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_constraint('fk_profiles_user_id_users', type_='foreignkey')
        batch_op.drop_column('user_id')

    op.drop_table('users')
