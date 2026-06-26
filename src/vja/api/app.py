"""FastAPI read-only dashboard API (Phase 6 · B1, D-030/D-041) + auth foundation (9.2, D-055).

One endpoint of substance: `GET /api/postings`, a window onto the in-scope open set with this
profile's match quality LEFT-joined on. Two orthogonal axes map onto the query
(`open_postings_with_match_quality`): **recency** (`window`) and **match-status**
(`include_unassessed` / `include_rejected`). The dashboard never triggers a fetch/LLM/write
(D-005, docs/11 §2); the engine is read-only here.

Auth (D-055): Google OAuth login → a signed-cookie session. `_resolve_profile` now plugs the
docs/11 §2 seam — an authenticated request resolves to *its own* user's profile (403 on another's
`profile_id`). Hard enforcement is **deferred** behind `VJA_AUTH_REQUIRED` (default off), so the
single-active default still serves the local dashboard before the login frontend (9.4) / deploy.
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
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from starlette.middleware.sessions import SessionMiddleware

from vja.api.auth import (
    auth_required,
    build_oauth,
    get_current_user,
    session_secret,
)
from vja.db.engine import get_engine
from vja.db.postings import open_postings_with_match_quality
from vja.db.profiles import Profile, active_profiles, active_verticals
from vja.db.users import User, upsert_user_by_google

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
    """Match-status view (D-045). `matched` (default) = this résumé's relevant matches only (the
    AI's recommendations); `cleaned` = the whole in-scope US-software universe, every verdict incl.
    `no` and not-yet-assessed (the objective job list, the same set for any profile)."""

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


def _resolve_profile(
    engine: Engine, vertical: str, profile_id: int | None, user: User | None
) -> Profile:
    """Resolve the profile to score against (docs/11 §2 seam, D-055).

    **Authenticated:** resolve to *this user's* active profile for the vertical (linked by email,
    D-027); a `profile_id` that isn't theirs → 403; none for the vertical → 404.

    **Unauthenticated:** the deferred-enforcement path — the original single-active default (404
    none, 409 ambiguous, explicit `profile_id`). With `VJA_AUTH_REQUIRED` on, no session is 401.
    """
    if user is None and auth_required():
        raise HTTPException(401, "authentication required")

    profiles = active_profiles(engine, vertical)

    if user is not None:
        if profile_id is not None:
            match = next((p for p in profiles if p.id == profile_id), None)
            if match is None:
                raise HTTPException(404, f"no profile {profile_id} for vertical {vertical!r}")
            if match.user_email != user.email:
                raise HTTPException(403, "profile does not belong to the authenticated user")
            return match
        mine = [p for p in profiles if p.user_email == user.email]
        if not mine:
            raise HTTPException(404, f"no active profile for {user.email} in vertical {vertical!r}")
        if len(mine) > 1:
            raise HTTPException(409, f"multiple active profiles for {user.email}; pass profile_id")
        return mine[0]

    # Unauthenticated default (operable until enforcement flips on).
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
    # OAuth registry (None until GOOGLE_CLIENT_* are set); the login routes report 503 when absent.
    app.state.oauth = build_oauth()

    # Signed-cookie session carrying `user_id` (D-055). Added before CORS so it wraps every request.
    app.add_middleware(SessionMiddleware, secret_key=session_secret())
    # Dev serves the SPA from a separate Vite origin → CORS; prod is same-origin (mount below).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/auth/login")
    async def login(request: Request) -> RedirectResponse:
        """Kick off Google OAuth. 503 until `GOOGLE_CLIENT_*` are configured."""
        oauth = request.app.state.oauth
        if oauth is None:
            raise HTTPException(503, "OAuth not configured (set GOOGLE_CLIENT_ID/SECRET)")
        redirect_uri = request.url_for("auth_callback")
        resp = await oauth.google.authorize_redirect(request, redirect_uri)
        return cast("RedirectResponse", resp)

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request) -> RedirectResponse:
        """OAuth redirect target: exchange the code, upsert+link the user, open a session."""
        oauth = request.app.state.oauth
        if oauth is None:
            raise HTTPException(503, "OAuth not configured (set GOOGLE_CLIENT_ID/SECRET)")
        token = await oauth.google.authorize_access_token(request)
        info = token.get("userinfo") or {}
        sub, email = info.get("sub"), info.get("email")
        if not (sub and email):
            raise HTTPException(400, "OAuth response missing sub/email")
        user = upsert_user_by_google(
            request.app.state.engine, google_sub=sub, email=email, name=info.get("name")
        )
        request.session["user_id"] = user.id
        return RedirectResponse("/")

    @app.post("/auth/logout")
    def logout(request: Request) -> dict[str, str]:
        request.session.pop("user_id", None)
        return {"status": "ok"}

    @app.get("/api/me")
    def me(request: Request) -> dict[str, object]:
        """The authenticated user, or 401 — the frontend's session probe (9.4)."""
        user = get_current_user(request)
        if user is None:
            raise HTTPException(401, "not authenticated")
        return {"id": user.id, "email": user.email, "name": user.name}

    @app.get("/api/verticals")
    def verticals(engine: Annotated[Engine, Depends(_get_engine)]) -> list[str]:
        """Active verticals — the frontend's vertical picker, so no slug is hardcoded (D-042)."""
        return active_verticals(engine)

    @app.get("/api/postings")
    def postings(
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User | None, Depends(get_current_user)],
        vertical: str,
        window: Window = Window.ALL,
        view: View = View.MATCHED,
        profile_id: Annotated[int | None, Query()] = None,
    ) -> PostingsResponse:
        profile = _resolve_profile(engine, vertical, profile_id, user)
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
