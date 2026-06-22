"""FastAPI read-only dashboard API (Phase 6 · B1, D-030/D-041).

One endpoint of substance: `GET /api/postings`, a window onto the in-scope open set with this
profile's match quality LEFT-joined on. Two orthogonal axes map onto the query
(`open_postings_with_match_quality`): **recency** (`window`) and **match-status**
(`include_unassessed` / `include_rejected`). The dashboard never triggers a fetch/LLM/write
(D-005, docs/11 §2); the engine is read-only here.

Single-user today: `profile_id` is optional and a thin default resolves the one active profile
for the vertical (docs/11 §2 seam). Multi-user adds *resolve from auth → filter*, not a redesign.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, cast

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from vja.db.engine import get_engine
from vja.db.postings import open_postings_with_match_quality
from vja.db.profiles import Profile, active_profiles, active_verticals

# The built React SPA (B2). Mounted at `/` only when present, so dev (Vite server + CORS) and
# tests/CI (no build) are unaffected; prod serves the SPA same-origin from this dir. (D-042)
_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"

# Dev-server origins allowed by CORS. Prod is same-origin (static mount), so this is the Vite
# dev server by default; override with `VJA_CORS_ORIGINS` (comma-separated). (D-042)
_DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class Window(StrEnum):
    """Recency toggle (D-030). Maps to a cutoff over the ATS activity date (`week`/`two_weeks`) or
    our detection date (`new_today`, mirroring the digest); `all` applies no date filter."""

    NEW_TODAY = "new_today"
    WEEK = "week"
    TWO_WEEKS = "two_weeks"
    ALL = "all"


class View(StrEnum):
    """Match-status view (D-043). `matched` (default) = relevant matches only; `cleaned` = the whole
    in-scope US-software universe (incl. not-yet-assessed). Rejected (`no`) is never shown."""

    MATCHED = "matched"
    CLEANED = "cleaned"


class PostingRow(BaseModel):
    """One dashboard row. Match fields are `None` when the posting is in-scope but not yet assessed
    for this profile (only present in the `cleaned` view)."""

    model_config = ConfigDict(from_attributes=True)

    posting_id: int
    company: str
    title: str | None
    location: str | None
    apply_url: str | None
    first_seen_at: datetime
    source_updated_at: datetime | None
    verdict: str | None
    score: int | None
    fits: list[str] | None
    gaps: list[str] | None
    rationale: str | None


class PostingsResponse(BaseModel):
    """The resolved query echoed back alongside the rows — so the client knows which profile and
    filters produced this set (the default `profile_id`/window aren't otherwise visible)."""

    vertical: str
    profile_id: int
    window: Window
    view: View
    count: int
    postings: list[PostingRow]


def _window_cutoff(window: Window, now: datetime) -> tuple[datetime | None, bool]:
    """(cutoff, by_first_seen) for a toggle. `new_today` = calendar midnight UTC on first_seen."""
    if window is Window.ALL:
        return None, False
    if window is Window.NEW_TODAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0), True
    if window is Window.WEEK:
        return now - timedelta(days=7), False
    return now - timedelta(days=14), False  # TWO_WEEKS


def _resolve_profile(engine: Engine, vertical: str, profile_id: int | None) -> Profile:
    """Resolve the profile to score against (docs/11 §2 seam). Explicit id, else the single active
    profile for the vertical. 404 if none / id not found; 409 if ambiguous (multi-user, later)."""
    profiles = active_profiles(engine, vertical)
    if profile_id is not None:
        match = next((p for p in profiles if p.id == profile_id), None)
        if match is None:
            raise HTTPException(404, f"no active profile {profile_id} for vertical {vertical!r}")
        return match
    if not profiles:
        raise HTTPException(404, f"no active profile for vertical {vertical!r}")
    if len(profiles) > 1:
        raise HTTPException(
            409, f"multiple active profiles for vertical {vertical!r}; pass profile_id"
        )
    return profiles[0]


def _get_engine(request: Request) -> Engine:
    return cast("Engine", request.app.state.engine)


def _cors_origins() -> list[str]:
    """Allowed CORS origins: `VJA_CORS_ORIGINS` (comma-separated) or the Vite dev defaults."""
    raw = os.environ.get("VJA_CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_CORS_ORIGINS)


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the read-only dashboard API. Pass `engine` in tests; defaults to `get_engine()`."""
    app = FastAPI(title="VJA dashboard API", version="0.1.0")
    app.state.engine = engine if engine is not None else get_engine()

    # Dev serves the SPA from a separate Vite origin → CORS; prod is same-origin (mount below).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/verticals")
    def verticals(engine: Annotated[Engine, Depends(_get_engine)]) -> list[str]:
        """Active verticals — the frontend's vertical picker, so no slug is hardcoded (D-042)."""
        return active_verticals(engine)

    @app.get("/api/postings")
    def postings(
        engine: Annotated[Engine, Depends(_get_engine)],
        vertical: str,
        window: Window = Window.ALL,
        view: View = View.MATCHED,
        profile_id: Annotated[int | None, Query()] = None,
    ) -> PostingsResponse:
        profile = _resolve_profile(engine, vertical, profile_id)
        cutoff, by_first_seen = _window_cutoff(window, datetime.now(UTC))
        rows = open_postings_with_match_quality(
            engine,
            vertical,
            profile.id,
            profile.resume_version,
            cutoff=cutoff,
            by_first_seen=by_first_seen,
            cleaned=view is View.CLEANED,
        )
        return PostingsResponse(
            vertical=vertical,
            profile_id=profile.id,
            window=window,
            view=view,
            count=len(rows),
            postings=[PostingRow.model_validate(r) for r in rows],
        )

    # Serve the built SPA same-origin in prod, if it exists. Mounted last so `/api/*` wins;
    # `html=True` makes it serve `index.html` for the SPA's client routes. (D-042)
    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="spa")

    return app


def api_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-api [--host H] [--port P]` — serve the read-only dashboard API via uvicorn."""
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="vja-api", description="Serve the read-only dashboard API."
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()
    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(api_main())
