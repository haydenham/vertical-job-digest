"""add users digest paused

Revision ID: e91b3a6f2d04
Revises: c4e8a7d9132f
Create Date: 2026-07-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e91b3a6f2d04"
down_revision: str | Sequence[str] | None = "c4e8a7d9132f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the per-user digest-email pause flag (D-094)."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("digest_paused", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Remove the per-user digest-email pause flag."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("digest_paused")
