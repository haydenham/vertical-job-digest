"""Shared test fixtures: a fresh DB built from the real Alembic migrations.

Lives at the tests root so both `tests/integration` and `tests/system` use it. Per
`docs/08`, the test schema is created the same way prod's is — `alembic upgrade head`
against a throwaway database — so the migrations themselves are exercised, not just
`metadata.create_all`.

Dialect: SQLite by default (a throwaway `tmp_path` file, as in dev). When
`VJA_TEST_DATABASE_URL` is set (the Postgres CI job, D-054), the suite runs against that
Postgres instead — the same migrations, proving the dialect-portable cutover (D-025). One
shared Postgres service can't lean on a fresh file per test, so each test resets `public`
(`DROP SCHEMA ... CASCADE; CREATE SCHEMA`) before the upgrade — robust isolation that doesn't
depend on every migration having a working `downgrade()`.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from vja.db.engine import get_engine

_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    return cfg


def _reset_postgres_schema(url: str) -> None:
    """Drop and recreate `public` so each test starts from a clean Postgres (shared service)."""
    engine = get_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


@pytest.fixture
def migrated_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    pg_url = os.environ.get("VJA_TEST_DATABASE_URL")
    url = pg_url or f"sqlite:///{tmp_path / 'test.db'}"
    if pg_url:
        _reset_postgres_schema(pg_url)
    monkeypatch.setenv("VJA_DATABASE_URL", url)  # env.py reads this
    command.upgrade(alembic_config(), "head")
    engine = get_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
