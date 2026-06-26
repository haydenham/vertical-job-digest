"""users repository — the authenticated identity (Phase 9.2, D-055).

A `users` row is one person, created at first Google OIDC login. Identity still *anchors on email*
(D-027): a profile (e.g. the seed) can exist before any login keyed only on `user_email`, and the
first login **adopts** it — `_link_profiles` backfills `profiles.user_id` by email, the bridge from
the email seam to the FK. PII tier (docs/11 §2): never denormalized into employers/postings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine, select, update

from vja.db.engine import begin
from vja.db.schema import profiles, users

_USER_COLS = (users.c.id, users.c.google_sub, users.c.email, users.c.name)


@dataclass(frozen=True)
class User:
    id: int
    google_sub: str | None
    email: str
    name: str | None


def _load_user(conn: Connection, user_id: int) -> User:
    row = conn.execute(select(*_USER_COLS).where(users.c.id == user_id)).mappings().one()
    return User(id=row["id"], google_sub=row["google_sub"], email=row["email"], name=row["name"])


def get_user(engine: Engine, user_id: int) -> User | None:
    """The user for a session id, or None if it no longer exists (stale cookie)."""
    with engine.connect() as conn:
        row = (
            conn.execute(select(*_USER_COLS).where(users.c.id == user_id)).mappings().one_or_none()
        )
    if row is None:
        return None
    return User(id=row["id"], google_sub=row["google_sub"], email=row["email"], name=row["name"])


def upsert_user_by_google(
    engine: Engine,
    *,
    google_sub: str,
    email: str,
    name: str | None = None,
    now: datetime | None = None,
) -> User:
    """Idempotently resolve the `users` row for a Google login, linking any email-only profiles.

    Match order: existing `google_sub` → an email-only row (adopt it, stamp `google_sub`) → insert.
    Either way the user's profiles are linked by email (`_link_profiles`), so the seed profile
    attaches on first login. Returns the resolved user.
    """
    stamp = now or datetime.now(UTC)

    with begin(engine) as conn:
        existing = conn.execute(
            select(users.c.id).where(users.c.google_sub == google_sub)
        ).scalar_one_or_none()

        if existing is not None:
            user_id = int(existing)
            # Keep the display name fresh on repeat logins.
            conn.execute(update(users).where(users.c.id == user_id).values(name=name))
        else:
            # Adopt a pre-existing email identity if present, else insert a fresh user.
            by_email = conn.execute(
                select(users.c.id).where(users.c.email == email)
            ).scalar_one_or_none()
            if by_email is not None:
                user_id = int(by_email)
                conn.execute(
                    update(users)
                    .where(users.c.id == user_id)
                    .values(google_sub=google_sub, name=name)
                )
            else:
                result = conn.execute(
                    users.insert().values(
                        google_sub=google_sub, email=email, name=name, created_at=stamp
                    )
                )
                pk = result.inserted_primary_key
                assert pk is not None
                user_id = int(pk[0])

        _link_profiles(conn, user_id, email)
        return _load_user(conn, user_id)


def _link_profiles(conn: Connection, user_id: int, email: str) -> None:
    """Backfill `profiles.user_id` for this user's email-keyed, not-yet-linked profiles."""
    conn.execute(
        update(profiles)
        .where(profiles.c.user_email == email, profiles.c.user_id.is_(None))
        .values(user_id=user_id)
    )
