"""Shared test fixtures: a fresh SQLite DB built from the real Alembic migrations.

Lives at the tests root so both `tests/integration` and `tests/system` use it. Per
`docs/08`, the test schema is created the same way prod's is — `alembic upgrade head`
against a throwaway `tmp_path` database — so the migrations themselves are exercised,
not just `metadata.create_all`.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from vja.db.engine import get_engine

_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    return cfg


@pytest.fixture
def migrated_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("VJA_DATABASE_URL", url)  # env.py reads this
    command.upgrade(alembic_config(), "head")
    engine = get_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
