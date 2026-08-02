"""add users vertical switch timestamp

Revision ID: 3f8ad42c17be
Revises: 79c5ef618c90
Create Date: 2026-07-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f8ad42c17be"
down_revision: str | Sequence[str] | None = "79c5ef618c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the per-user vertical-switch clock (self-serve switching).

    Separate from `last_resume_reupload_at` on purpose: conflating them would make a résumé
    upload block a vertical switch and vice versa.
    """
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("last_vertical_switch_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Remove the per-user vertical-switch clock."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("last_vertical_switch_at")
