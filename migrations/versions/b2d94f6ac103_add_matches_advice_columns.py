"""add matches advice columns

Revision ID: b2d94f6ac103
Revises: 3f8ad42c17be
Create Date: 2026-08-06 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d94f6ac103"
down_revision: str | Sequence[str] | None = "3f8ad42c17be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist actionable match advice beside the fits/gaps argument (D-111).

    Two columns rather than one blended list because they license different acts: `resume_actions`
    is definitionally about content already on the resume (lead with this, reword that), while
    `application_notes` is about content that is *not* there and cannot be added honestly (how to
    frame a real gap). Blended, the model has no boundary to respect and the failure mode is
    advising the user to claim a skill they lack.

    Nullable with no backfill, mirroring D-095: matching is idempotent per
    (posting, profile, resume_version), so a prompt change never recomputes an existing judgment
    and old rows keep NULL forever. Note that NULL and `"[]"` are different answers on the read
    side — NULL is "matched before this existed", `"[]"` is this model saying the role has no
    honest advice.
    """
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resume_actions", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("application_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove the stored match advice."""
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.drop_column("application_notes")
        batch_op.drop_column("resume_actions")
