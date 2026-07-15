"""Production schema-readiness guard (D-083).

The service image must not become ready when its database is behind the Alembic head packaged
with that image. A database revision unknown to an older image is allowed, preserving rollback
after an additive migration has already advanced production.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from vja.api.app import create_app
from vja.db.engine import get_engine
from vja.db.schema_guard import SchemaBehindError, ensure_schema_ready

_PRE_BACKFILL_REVISION = "b2f4c1a9e07d"
_PACKAGED_HEAD = "c4e8a7d9132f"
_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    return cfg


def test_schema_guard_accepts_database_at_packaged_head(
    migrated_engine: Engine,
) -> None:
    ensure_schema_ready(migrated_engine, _alembic_config())


def test_schema_guard_rejects_database_behind_packaged_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'behind.db'}"
    monkeypatch.setenv("VJA_DATABASE_URL", url)
    command.upgrade(_alembic_config(), _PRE_BACKFILL_REVISION)
    engine = get_engine(url)
    try:
        with pytest.raises(SchemaBehindError, match=_PACKAGED_HEAD):
            ensure_schema_ready(engine, _alembic_config())
    finally:
        engine.dispose()


def test_configured_schema_guard_fails_app_startup_before_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'startup-behind.db'}"
    monkeypatch.setenv("VJA_DATABASE_URL", url)
    monkeypatch.setenv("VJA_ALEMBIC_INI", str(_ROOT / "alembic.ini"))
    command.upgrade(_alembic_config(), _PRE_BACKFILL_REVISION)
    engine = get_engine(url)
    try:
        with (
            pytest.raises(SchemaBehindError, match=_PACKAGED_HEAD),
            TestClient(create_app(engine)),
        ):
            pass
    finally:
        engine.dispose()


def test_schema_guard_allows_unknown_revision_for_old_image_rollback(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'future_revision'"))

    ensure_schema_ready(migrated_engine, _alembic_config())
