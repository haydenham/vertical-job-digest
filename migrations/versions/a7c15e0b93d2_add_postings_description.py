"""add postings description

Revision ID: a7c15e0b93d2
Revises: e91b3a6f2d04
Create Date: 2026-07-24 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c15e0b93d2"
down_revision: str | Sequence[str] | None = "e91b3a6f2d04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the posting body as plain text for the dashboard detail panel (D-095).

    Nullable with no backfill by decision: existing rows fill naturally as postings are inserted,
    change, reopen, or re-extract — the text is already in hand at each of those points, so a
    backfill would be re-fetch load (or LLM spend) for nothing.
    """
    with op.batch_alter_table("postings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove the stored posting description."""
    with op.batch_alter_table("postings", schema=None) as batch_op:
        batch_op.drop_column("description")
