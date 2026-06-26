"""Migrations build the full schema and stay in sync with the metadata (Block 1).

Also pins a populated-DB regression (D-021, D-054): the `migrated_engine` fixture builds straight to
head against empty tables, so a batch table-rebuild that only fails when a *referencing* table holds
rows slips through — exactly what bit the real `vja.db` on the 9.2 `profiles.user_id` migration.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Connection, Engine, inspect, select
from sqlalchemy.sql import Insert

from tests.conftest import alembic_config
from vja.db.engine import begin, get_engine
from vja.db.schema import employers, matches, postings, profiles

_EXPECTED_TABLES = {
    "employers",
    "sources",
    "postings",
    "profiles",
    "matches",
    "digests",
    "pipeline_runs",
    "users",
}

# The revision immediately before the 9.2 users/user_id migration (7d5b69c46786).
_PRE_USER_ID_REVISION = "d30501b4c8ab"
_NOW = datetime(2026, 6, 26, tzinfo=UTC)


def test_upgrade_head_creates_all_tables(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names())
    assert tables >= _EXPECTED_TABLES


def test_no_drift_between_schema_and_migration(migrated_engine: Engine) -> None:
    # `alembic check` raises if the autogenerate diff is non-empty — i.e. if schema.py
    # and the committed migration have drifted apart. (Engine fixture leaves the DB
    # migrated + VJA_DATABASE_URL pointing at it.)
    command.check(alembic_config())


def _insert(conn: Connection, stmt: Insert) -> int:
    pk = conn.execute(stmt).inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _seed_match_referencing_a_profile(url: str) -> int:
    """Insert employer→posting→profile→match so `matches` references `profiles` (the FK the naive
    rebuild tripped). Returns the match id. Runs under FKs ON (the app engine)."""
    engine = get_engine(url)
    try:
        with begin(engine) as conn:
            emp = _insert(
                conn,
                employers.insert().values(
                    vertical="grid_power_software",
                    name="GridCo",
                    ats_type="greenhouse",
                    source="manual",
                    status="active",
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
            )
            posting = _insert(
                conn,
                postings.insert().values(
                    employer_id=emp,
                    external_id="x1",
                    content_hash="h1",
                    raw_payload={},
                    status="open",
                    first_seen_at=_NOW,
                    last_seen_at=_NOW,
                ),
            )
            profile = _insert(
                conn,
                profiles.insert().values(
                    user_email="me@example.com",
                    vertical="grid_power_software",
                    resume_version="v1",
                    resume_text="r",
                    active=1,
                    created_at=_NOW,
                ),
            )
            return _insert(
                conn,
                matches.insert().values(
                    posting_id=posting,
                    profile_id=profile,
                    resume_version="v1",
                    verdict="yes",
                    model_version="m",
                    trigger="nightly",
                    created_at=_NOW,
                ),
            )
    finally:
        engine.dispose()


def test_add_user_id_on_populated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite-only: the 9.2 rebuild succeeds + preserves data when `matches` already has rows."""
    url = f"sqlite:///{tmp_path / 'populated.db'}"
    monkeypatch.setenv("VJA_DATABASE_URL", url)  # env.py reads this
    cfg = alembic_config()

    command.upgrade(cfg, _PRE_USER_ID_REVISION)
    match_id = _seed_match_referencing_a_profile(url)

    # The rebuild that crashed in prod: must not trip the matches→profiles FK (migrations: FKs OFF).
    command.upgrade(cfg, "head")

    engine = get_engine(url)  # FKs back ON
    try:
        with engine.connect() as conn:
            assert conn.execute(select(profiles.c.user_id)).scalar_one() is None
            survived = conn.execute(
                select(matches.c.id).where(matches.c.id == match_id)
            ).scalar_one()
            assert survived == match_id
    finally:
        engine.dispose()
