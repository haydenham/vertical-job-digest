"""add users resume reupload timestamp

Revision ID: c4e8a7d9132f
Revises: a06b99424c4c
Create Date: 2026-07-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a7d9132f"
down_revision: str | Sequence[str] | None = "a06b99424c4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the per-user rolling reupload clock (D-085)."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("last_resume_reupload_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Remove the per-user rolling reupload clock."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("last_resume_reupload_at")
