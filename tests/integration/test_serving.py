"""Integration tests for the 9.5a SPA serving + deep-link catch-all (D-059).

The catch-all returns `index.html` for the SPA's client routes so a hard-refresh / deep-link of
`/upload` or `/login` doesn't 404, while real static files are served verbatim and `/api`·`/auth`
paths are never masked. The mount is gated on a real `index.html` (stale/empty `dist/` skipped).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from vja.api.app import create_app


def _build_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Rolefeed</title>")
    (dist / "assets" / "app.js").write_text("console.log('spa')")
    (dist / "favicon.ico").write_text("icon")
    return dist


def test_spa_serves_index_assets_and_deeplinks(
    tmp_path: Path, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = _build_dist(tmp_path)
    monkeypatch.setattr("vja.api.app._FRONTEND_DIST", dist)
    client = TestClient(create_app(migrated_engine))

    root = client.get("/")
    assert root.status_code == 200
    assert "Rolefeed" in root.text

    # deep link / hard refresh of a client route → index.html (the fix), not 404
    deep = client.get("/upload")
    assert deep.status_code == 200
    assert "Rolefeed" in deep.text

    # real static files served verbatim
    assert client.get("/assets/app.js").text.strip() == "console.log('spa')"
    assert client.get("/favicon.ico").text == "icon"


def test_spa_does_not_mask_api_or_auth(
    tmp_path: Path, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vja.api.app._FRONTEND_DIST", _build_dist(tmp_path))
    client = TestClient(create_app(migrated_engine))

    assert client.get("/api/health").json() == {"status": "ok"}
    # an unknown /api path 404s rather than being masked by index.html
    assert client.get("/api/does-not-exist").status_code == 404


def test_no_spa_mount_without_a_real_build(
    tmp_path: Path, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "dist"  # exists but has no index.html (stale build)
    empty.mkdir()
    monkeypatch.setattr("vja.api.app._FRONTEND_DIST", empty)
    client = TestClient(create_app(migrated_engine))

    assert client.get("/api/health").status_code == 200  # API still up
    assert client.get("/").status_code == 404  # no SPA mounted
