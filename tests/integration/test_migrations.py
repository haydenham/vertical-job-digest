"""Migrations build the full schema and stay in sync with the metadata (Block 1)."""

from alembic import command
from sqlalchemy import Engine, inspect

from tests.integration.conftest import alembic_config

_EXPECTED_TABLES = {
    "employers",
    "sources",
    "postings",
    "profiles",
    "matches",
    "digests",
    "pipeline_runs",
}


def test_upgrade_head_creates_all_tables(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names())
    assert tables >= _EXPECTED_TABLES


def test_no_drift_between_schema_and_migration(migrated_engine: Engine) -> None:
    # `alembic check` raises if the autogenerate diff is non-empty — i.e. if schema.py
    # and the committed migration have drifted apart. (Engine fixture leaves the DB
    # migrated + VJA_DATABASE_URL pointing at it.)
    command.check(alembic_config())
