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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from html import escape
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StringConstraints, computed_field
from sqlalchemy import Engine
from starlette.middleware.sessions import SessionMiddleware

from vja.api.auth import (
    auth_required,
    build_oauth,
    cookie_https_only,
    get_current_user,
    oauth_redirect_uri,
    require_user,
    session_max_age,
    session_secret,
)
from vja.api.public_cache import TTLCache
from vja.comp import annual_usd_display
from vja.db.engine import get_engine
from vja.db.postings import (
    open_posting_counts_by_vertical,
    open_postings_with_match_quality,
    posting_description,
)
from vja.db.profiles import (
    BackfillStatus,
    NoActiveProfile,
    Profile,
    ProfileVerticalConflict,
    ResumeReuploadLimited,
    VerticalSwitchLimited,
    active_profile_for_user,
    active_profiles,
    backfill_stamps,
    derive_backfill_status,
    switch_vertical,
    upload_profile,
)
from vja.db.schema_guard import ensure_configured_schema_ready
from vja.db.users import (
    User,
    delete_user_account,
    get_user,
    set_digest_paused,
    upsert_user_by_google,
)
from vja.digest.feedback import (
    FEEDBACK_MAX_CHARS,
    FeedbackCategory,
    FeedbackReport,
    send_feedback,
)
from vja.digest.send import ConfigError as SendConfigError
from vja.digest.send import SendError, load_config
from vja.digest.unsubscribe import parse_unsubscribe_token
from vja.location import us_location_display
from vja.match import BackfillBudgetExceeded, check_backfill_budget, run_backfill
from vja.resume import ResumeError, extract_resume_text
from vja.verticals import ConfigError, available_verticals, load_vertical_config

logger = logging.getLogger(__name__)


def frontend_dist_dir() -> Path:
    """The built React SPA dir (B2), mounted at `/` only when present so dev (Vite + CORS) and
    tests/CI (no build) are unaffected; prod serves it same-origin (D-042). `VJA_FRONTEND_DIST`
    (set in the container, where the non-editable install moves the package out of the repo
    layout) wins; else the repo-layout default. (9.5b)"""
    override = os.environ.get("VJA_FRONTEND_DIST")
    return Path(override) if override else Path(__file__).resolve().parents[3] / "frontend" / "dist"


# Dev-server origins allowed by CORS. Prod is same-origin (static mount), so this is the Vite
# dev server by default; override with `VJA_CORS_ORIGINS` (comma-separated). (D-042)
_DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

# Upload ceiling for the résumé write endpoint (D-057) — a real résumé is small; this caps the
# in-memory read before the adapter runs. The adapter re-checks as defense in depth.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


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
    comp_min: int | None
    comp_max: int | None
    comp_raw: str | None
    verdict: str | None
    score: int | None
    fits: list[str] | None
    gaps: list[str] | None
    rationale: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def comp_display(self) -> str | None:
        """The formatted annual-USD range, or `None` when the extracted integers aren't
        corroborated as annual USD by `comp_raw` (`vja.comp` owns that judgment — see its module
        docstring for why the raw string, not the integers, is the anchor). The SPA renders this
        when present and falls back to `comp_raw` verbatim, so the decision stays server-side and
        testable (F2 Phase A, D-087)."""
        return annual_usd_display(self.comp_min, self.comp_max, self.comp_raw)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def location_display(self) -> str | None:
        """The stored ATS location rendered in one consistent US form, or `None` when there is
        nothing to improve (`vja.location`, D-106). The stored `location` stays L1-authoritative
        (D-043) and is still served beside this; the SPA renders this when present and falls back
        to `location` verbatim."""
        return us_location_display(self.location)


class PublicPostingRow(BaseModel):
    """One row on the login-free demo board (D-105) — **the second structural anti-leak layer.**

    This is `PostingRow` minus every match field, and the omission is the point: it does not
    *declare* `verdict`/`score`/`fits`/`gaps`/`rationale`, so even a query that wrongly selected
    them could not serialize them to an anonymous caller. Match text is résumé-derived commentary
    about named beta users; D-067 turned `VJA_AUTH_REQUIRED` on and this PR does not weaken it.
    The first layer is `db.postings.dashboard_statement`, which never joins `matches` without a
    profile.

    `comp_display` is kept, so the `vja.comp` corroboration guard (D-087/D-095) still decides
    server-side whether a salary is safe to render. A stranger sees exactly the same salary
    judgment a logged-in user does.
    """

    model_config = ConfigDict(from_attributes=True)

    posting_id: int
    company: str
    title: str | None
    location: str | None
    apply_url: str | None
    first_seen_at: datetime
    source_updated_at: datetime | None
    comp_min: int | None
    comp_max: int | None
    comp_raw: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def comp_display(self) -> str | None:
        """The guarded annual-USD range — see `PostingRow.comp_display`."""
        return annual_usd_display(self.comp_min, self.comp_max, self.comp_raw)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def location_display(self) -> str | None:
        """The normalized location — see `PostingRow.location_display`. Posting data, not
        résumé-derived, so it belongs on the public board (D-106/D-105)."""
        return us_location_display(self.location)


class PublicPostingsResponse(BaseModel):
    """`GET /api/public/postings` — the whole in-scope open set for one vertical.

    No `view` axis and no `profile_id`: without a résumé there is nothing to be matched against, so
    the public board is always the objective universe (the *All in-scope* set, D-045). The demo
    ships it whole — ~250 rows a vertical measured against Neon, well under the point where a cap
    would earn its complexity.
    """

    vertical: str
    window: Window
    count: int
    postings: list[PublicPostingRow]


class PublicVerticalRow(BaseModel):
    """One entry in the demo's vertical toggle: the key plus how many roles stand behind it."""

    vertical: str
    count: int


class PostingDetailRow(BaseModel):
    """`GET /api/postings/{id}` — the posting body, fetched only when a panel opens (D-095).

    Its own endpoint rather than a field on `PostingRow`: bodies average ~3 KB of text, so putting
    them on the list would cost megabytes per dashboard load to show a handful. `description` is
    `null` for a row whose body hasn't been captured yet; the SPA renders nothing in that case."""

    model_config = ConfigDict(from_attributes=True)

    posting_id: int
    description: str | None


class ProfileCreated(BaseModel):
    """The 202 response to a résumé upload — the new/updated profile, before the backfill runs."""

    profile_id: int
    vertical: str
    resume_version: str


class MeUser(BaseModel):
    """The authed identity in the `/api/me` payload. `digest_paused` is the D-094 email flag —
    the settings page reads it here and flips it via `PATCH /api/me`."""

    email: str
    name: str | None
    digest_paused: bool


class MeSettingsUpdate(BaseModel):
    """`PATCH /api/me` body — the settings surface (D-094), now a true partial update: send only
    the fields that change, and an empty body is a 422 rather than a silent no-op.

    `digest_paused` is D-094's email flag. `vertical` is the self-serve vertical switch: it re-files
    the user's *existing* résumé under a different vertical and schedules a backfill (no re-upload
    — `resume_text` already lives on the profile row)."""

    digest_paused: bool | None = None
    vertical: str | None = None


class MeSettings(BaseModel):
    """`PATCH /api/me` response: the applied settings state, including the fields this request
    did not touch, so the client never has to guess what it now holds. `vertical` is null for a
    signed-in user with no profile."""

    digest_paused: bool
    vertical: str | None = None


class FeedbackIn(BaseModel):
    """`POST /api/feedback` body (D-100). Only these three fields come from the client — identity,
    vertical, and user agent are resolved server-side, so nobody can report as someone else.

    The length cap is the abuse guard: `require_user` already limits this to signed-in beta
    accounts, so a per-user throttle (a `users` column, hence a migration) buys nothing yet."""

    category: FeedbackCategory
    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=FEEDBACK_MAX_CHARS),
    ]
    # The SPA route the dialog was opened from, for reproducing the report.
    page: Annotated[str, StringConstraints(max_length=200)] | None = None


class FeedbackAccepted(BaseModel):
    """`POST /api/feedback` response: the report reached the mail provider."""

    status: str


class MeProfile(BaseModel):
    """The user's one active profile (D-064), or `None` in `MeResponse` when not yet onboarded.

    `backfill_status` (D-082) is derived server-side from the profile's backfill stamps —
    `running` while the signup/reupload catch-up computes (drives the dashboard's progress
    banner + poll), `done` once it finished (or went stale — the crash guard), `null` for rows
    that never had a stamped backfill (pre-D-082 / CLI-seeded)."""

    vertical: str
    resume_version: str
    backfill_status: BackfillStatus | None


class MeResponse(BaseModel):
    """`GET /api/me` — the single source of truth the SPA routes on (D-065): who you are + your one
    vertical (or `profile: null` ⇒ signed in but not onboarded → send to onboarding, not a 404)."""

    user: MeUser
    profile: MeProfile | None


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


# The public board's cache header (D-105). `max-age` is the browser's copy, `s-maxage` the shared
# edge's — Cloudflare holds it for 15 minutes, which is well inside the four-hour pipeline cadence
# (D-103) and is what stops a link going round LinkedIn from reaching Neon once per reader.
# NB the `s-maxage` half only does anything while the zone is proxied (orange-cloud), not DNS-only.
_PUBLIC_CACHE_CONTROL = "public, max-age=300, s-maxage=900"


def _require_configured_vertical(vertical: str) -> None:
    """404 a vertical that has no config — the public endpoints' only input validation.

    Without it, `vertical` is an unvalidated string on an unauthenticated endpoint: harmless to the
    query (it would simply return nothing) but a free existence oracle and an unbounded cache key.
    """
    if vertical not in set(available_verticals()):
        raise HTTPException(404, f"unknown vertical {vertical!r}")


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


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA same-origin (D-042): real assets verbatim, plus a trailing catch-all that
    returns `index.html` for the SPA's client routes so a hard-refresh / deep-link of `/upload` or
    `/login` doesn't 404 (the 9.5a fix, D-059). Registered last so every `/api/*` and `/auth/*`
    route wins; unknown API paths explicitly 404 rather than being masked with `index.html`."""
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "auth/")):
            raise HTTPException(404, "not found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)  # a real static file (favicon, etc.)
        return FileResponse(index)  # an SPA client route


def _unsubscribe_page(title: str, body: str) -> str:
    """A minimal standalone HTML page for the no-login unsubscribe flow (D-094). The SPA isn't
    involved: this must render for a logged-out email click, and mail-client webviews."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)} — Rolefeed</title></head>"
        "<body style='font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;"
        "padding:0 1rem;color:#222'>"
        "<h1 style='font-size:1.3rem'>Rolefeed</h1>"
        f"<h2 style='font-size:1.1rem'>{escape(title)}</h2>"
        f"{body}"
        "</body></html>"
    )


def _resolve_unsubscribe_claim(engine: Engine, token: str | None) -> User | None:
    """Token → the live `users` row it authorizes, or None. Requires id AND email to match the
    current row (stale-token defense); callers answer None with a generic 400 — never revealing
    whether a user exists."""
    if not token:
        return None
    claim = parse_unsubscribe_token(token)
    if claim is None:
        return None
    user = get_user(engine, claim.user_id)
    if user is None or user.email != claim.email:
        return None
    return user


def _get_engine(request: Request) -> Engine:
    return cast("Engine", request.app.state.engine)


def _cors_origins() -> list[str]:
    """Allowed CORS origins: `VJA_CORS_ORIGINS` (comma-separated) or the Vite dev defaults. Prod is
    same-origin (the SPA is served by FastAPI), so CORS is unused there; an off-origin frontend must
    set explicit origins — `*` is disallowed with `allow_credentials=True`, which we rely on."""
    raw = os.environ.get("VJA_CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_CORS_ORIGINS)


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the read-only dashboard API. Pass `engine` in tests; defaults to `get_engine()`."""
    resolved_engine = engine if engine is not None else get_engine()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # D-083: fail readiness before Cloud Run sends traffic when code is ahead of the DB.
        # Unknown/newer DB revisions remain allowed so an old image can still cold-start on
        # rollback.
        ensure_configured_schema_ready(resolved_engine)
        yield

    app = FastAPI(title="VJA dashboard API", version="0.1.0", lifespan=lifespan)
    app.state.engine = resolved_engine
    # Per-app rather than module-level, so each test's app starts cold and one test's rows can
    # never be served to another (D-105).
    _public_postings_cache: TTLCache[list[PublicPostingRow]] = TTLCache()
    _public_verticals_cache: TTLCache[dict[str, int]] = TTLCache()
    app.state.public_caches = (_public_postings_cache, _public_verticals_cache)
    # OAuth registry (None until GOOGLE_CLIENT_* are set); the login routes report 503 when absent.
    app.state.oauth = build_oauth()

    # Signed-cookie session carrying `user_id` (D-055). Added before CORS so it wraps every request.
    # Cookie hardening is env-gated (9.5a, D-059): `Secure` in prod (VJA_COOKIE_SECURE),
    # `SameSite=Lax` always (Strict breaks Google's OAuth redirect), max_age from the env knob.
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(),
        https_only=cookie_https_only(),
        same_site="lax",
        max_age=session_max_age(),
    )
    # Dev serves the SPA from a separate Vite origin → CORS; prod is same-origin (mount below).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
        redirect_uri = oauth_redirect_uri(request)
        # prompt=select_account: force Google's account chooser so a shared browser can't silently
        # log the wrong Google session back in (D-065). Authlib forwards it as an auth param.
        resp = await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")
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
    def me(
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User | None, Depends(get_current_user)],
    ) -> MeResponse:
        """The authed user + their one profile (or null) — the SPA routes on this (D-065).

        No session → 401 (auth is required in prod). `profile` is null when the user has signed in
        but not yet onboarded (picked a vertical + uploaded a résumé), so the SPA sends them to
        onboarding instead of a 404ing dashboard (the D-064 fix)."""
        if user is None:
            raise HTTPException(401, "not authenticated")
        me_user = MeUser(email=user.email, name=user.name, digest_paused=user.digest_paused)
        profile = active_profile_for_user(engine, user.email)
        if profile is None:
            return MeResponse(user=me_user, profile=None)
        started, completed = backfill_stamps(engine, profile.id)
        return MeResponse(
            user=me_user,
            profile=MeProfile(
                vertical=profile.vertical,
                resume_version=profile.resume_version,
                backfill_status=derive_backfill_status(started, completed, now=datetime.now(UTC)),
            ),
        )

    @app.patch("/api/me")
    def update_me(
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User, Depends(require_user)],
        background: BackgroundTasks,
        body: MeSettingsUpdate,
    ) -> MeSettings:
        """Update the authed user's settings: the digest pause flag (D-094) and/or their vertical.

        `digest_paused` reuses the unsubscribe path's `set_digest_paused` (idempotent; the email
        predicate is the same stale-identity defense). A vanished row → 404.

        `vertical` is the self-serve switch that replaced D-064's support-only vertical change. It
        runs *first* when both fields are sent, because it is the half that can fail — a rejected
        switch then leaves nothing applied. Work-producing switches pass the same global daily
        ceiling as a signup (`check_backfill_budget`) before committing and schedule the same
        background `run_backfill`; the per-user rolling clock lives in `switch_vertical` and is
        charged only when the switch actually creates matching work."""
        if body.digest_paused is None and body.vertical is None:
            raise HTTPException(422, "no settings supplied")

        if body.vertical is not None:
            try:
                cfg = load_vertical_config(body.vertical)
            except ConfigError as exc:
                raise HTTPException(404, f"unknown vertical {body.vertical!r}") from exc
            stamp = datetime.now(UTC)
            try:
                switched = switch_vertical(
                    engine,
                    user_id=user.id,
                    user_email=user.email,
                    target_vertical=body.vertical,
                    domain_vocabulary=cfg.domain_vocabulary,
                    before_backfill=lambda: check_backfill_budget(engine, now=stamp),
                    now=stamp,
                )
            except NoActiveProfile as exc:
                raise HTTPException(
                    409, "no active profile to switch; upload a résumé first"
                ) from exc
            except VerticalSwitchLimited as exc:
                raise HTTPException(
                    429,
                    "vertical switches are limited to one per user every 24 hours",
                    headers={"Retry-After": str(exc.retry_after)},
                ) from exc
            except BackfillBudgetExceeded as exc:
                raise HTTPException(429, str(exc)) from exc
            if switched.backfill_required:
                background.add_task(
                    run_backfill, engine, body.vertical, switched.profile, config=cfg
                )

        paused = user.digest_paused
        if body.digest_paused is not None:
            updated = set_digest_paused(
                engine, user_id=user.id, email=user.email, paused=body.digest_paused
            )
            if not updated:
                raise HTTPException(404, "user not found")
            paused = body.digest_paused

        profile = active_profile_for_user(engine, user.email)
        return MeSettings(
            digest_paused=paused, vertical=profile.vertical if profile is not None else None
        )

    @app.delete("/api/me", status_code=204)
    def delete_me(
        request: Request,
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User, Depends(require_user)],
    ) -> None:
        """Hard account deletion (D-094): user + profiles + matches + digest rows, one transaction;
        postings/employers are shared corpus and survive (D-009 covers postings, not user PII).

        The session is popped here so the cookie dies with the account; a stale cookie elsewhere
        already resolves to None → 401. An in-flight backfill can't resurrect rows: its inserts
        either land before the atomic delete (removed) or FK-fail after it (logged, harmless)."""
        delete_user_account(engine, user_id=user.id, email=user.email)
        request.session.pop("user_id", None)

    @app.get("/api/verticals")
    def verticals() -> list[str]:
        """Configured verticals available to join — the onboarding picker's source (D-064/D-065).

        Config-driven, not active-profile-driven: a vertical must stay joinable even with zero
        profiles in it, else B-4 (deactivating the aviation seed) would hide aviation from a new
        aviation user. The dashboard routes on `/api/me`, not on this list (the D-064 fix)."""
        return available_verticals()

    # ---- the public demo board (D-105) -------------------------------------------------------
    # Three unauthenticated endpoints, and the only ones in this file that never call
    # `_resolve_profile` or touch `get_current_user`. They exist because login + a résumé upload
    # sat in front of every job we have: 5,000 launch views produced 10 uploads, so ~99.9% of
    # interest never saw the product's actual claim. Nothing here relaxes the authenticated path —
    # `/api/postings` still 401s anonymously and is untouched.
    @app.get("/api/public/verticals")
    def public_verticals(
        engine: Annotated[Engine, Depends(_get_engine)], response: Response
    ) -> list[PublicVerticalRow]:
        """Verticals with something to show, newest-universe-first, for the demo's toggle.

        Not `/api/verticals`, which is the onboarding picker's config-driven list and must stay
        joinable at zero rows (the B-4 fix). This is the mirror image: a vertical with no in-scope
        open roles is omitted, because a toggle that opens onto an empty table reads as breakage.
        """
        response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL
        counts = _public_verticals_cache.get_or_compute(
            "all", lambda: open_posting_counts_by_vertical(engine)
        )
        configured = set(available_verticals())
        return [
            PublicVerticalRow(vertical=vertical, count=count)
            for vertical, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            # A vertical whose config was retired keeps its rows in the DB (D-009 never deletes),
            # but it is not something we can send a visitor to sign up for.
            if count > 0 and vertical in configured
        ]

    @app.get("/api/public/postings")
    def public_postings(
        engine: Annotated[Engine, Depends(_get_engine)],
        response: Response,
        vertical: str,
        window: Window = Window.ALL,
    ) -> PublicPostingsResponse:
        """The in-scope open set for one vertical, with no match data of any kind.

        `profile_id=None` is what makes that structural rather than careful: the statement never
        references `matches` (`db.postings.dashboard_statement`), and `PublicPostingRow` does not
        declare the match fields. `_window_cutoff` and the `Window` enum are shared with the
        authenticated dashboard, so the recency toggle means exactly the same thing on both.
        """
        _require_configured_vertical(vertical)
        response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL

        def load() -> list[PublicPostingRow]:
            cutoff, by_first_seen = _window_cutoff(window, datetime.now(UTC))
            rows = open_postings_with_match_quality(
                engine,
                vertical,
                None,
                None,
                cutoff=cutoff,
                by_first_seen=by_first_seen,
                cleaned=True,
            )
            return [PublicPostingRow.model_validate(r) for r in rows]

        postings_out = _public_postings_cache.get_or_compute((vertical, window), load)
        return PublicPostingsResponse(
            vertical=vertical,
            window=window,
            count=len(postings_out),
            postings=postings_out,
        )

    @app.get("/api/public/postings/{posting_id}")
    def public_posting_detail(
        engine: Annotated[Engine, Depends(_get_engine)],
        response: Response,
        posting_id: int,
        vertical: str,
    ) -> PostingDetailRow:
        """One posting's body, for the demo panel — the same `posting_description` the dashboard
        uses, which needs no profile and already 404s an id from another vertical.

        Uncached: the key space is one entry per posting and each open is a single indexed lookup,
        so an in-process cache would trade memory for nothing. The HTTP header still lets the edge
        hold it.
        """
        _require_configured_vertical(vertical)
        response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL
        detail = posting_description(engine, posting_id, vertical)
        if detail is None:
            raise HTTPException(404, f"no posting {posting_id} in {vertical!r}")
        return PostingDetailRow.model_validate(detail)

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

    @app.get("/api/postings/{posting_id}")
    def posting_detail(
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User | None, Depends(get_current_user)],
        posting_id: int,
        vertical: str,
    ) -> PostingDetailRow:
        """One posting's body, fetched when the dashboard panel opens (D-095).

        Same visibility gate as the list — `_resolve_profile` applies the auth rule (401 with
        `VJA_AUTH_REQUIRED`, and a caller can only read the vertical they have a profile in), and
        the query itself is floored on that vertical's in-scope set. A posting id from another
        vertical is a 404, not a body. Read-only (D-005).
        """
        _resolve_profile(engine, vertical, None, user)
        detail = posting_description(engine, posting_id, vertical)
        if detail is None:
            raise HTTPException(404, f"no posting {posting_id} in {vertical!r}")
        return PostingDetailRow.model_validate(detail)

    @app.post("/api/profiles", status_code=202)
    async def create_profile(
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User, Depends(require_user)],
        background: BackgroundTasks,
        vertical: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
    ) -> ProfileCreated:
        """Upload a résumé → create/update this user's profile → kick off the signup backfill.

        The first write path (9.3, D-057). Behind `require_user` (401 without a session). The
        résumé adapter (D-033) turns the file into `resume_text`; `upload_profile` atomically
        applies the one-vertical rule, profile versioning, and D-085's rolling reupload guard.
        Identical content is a 202 no-op with no backfill. Work-producing uploads run D-057's
        global daily ceiling before committing, then `run_backfill` (the D-039 5-day catch-up)
        runs in the background. PII discipline: the résumé text is never logged.
        """
        data = await file.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"file too large (max {_MAX_UPLOAD_BYTES} bytes)")
        try:
            resume_text = extract_resume_text(file.filename, data)
        except ResumeError as exc:
            raise HTTPException(422, str(exc)) from exc

        try:
            cfg = load_vertical_config(vertical)
        except ConfigError as exc:
            raise HTTPException(404, f"unknown vertical {vertical!r}") from exc

        stamp = datetime.now(UTC)
        try:
            upload = upload_profile(
                engine,
                user_id=user.id,
                user_email=user.email,
                vertical=vertical,
                resume_text=resume_text,
                domain_vocabulary=cfg.domain_vocabulary,
                before_backfill=lambda: check_backfill_budget(engine, now=stamp),
                now=stamp,
            )
        except ProfileVerticalConflict as exc:
            # Still a hard 409: this is the résumé form, and silently moving someone's vertical
            # from a file upload is worse than an error. The switch has its own deliberate
            # surface now (`PATCH /api/me`), so the message points there instead of at support.
            raise HTTPException(
                409,
                f"already onboarded to {exc.vertical!r}; one vertical per user "
                f"(change it in Settings)",
            ) from exc
        except ResumeReuploadLimited as exc:
            raise HTTPException(
                429,
                "changed résumé uploads are limited to one per user every 24 hours",
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except BackfillBudgetExceeded as exc:
            raise HTTPException(429, str(exc)) from exc

        profile = upload.profile
        if upload.backfill_required:
            background.add_task(run_backfill, engine, vertical, profile, config=cfg)
        return ProfileCreated(
            profile_id=profile.id, vertical=vertical, resume_version=profile.resume_version
        )

    @app.post("/api/feedback", status_code=202)
    def submit_feedback(
        request: Request,
        engine: Annotated[Engine, Depends(_get_engine)],
        user: Annotated[User, Depends(require_user)],
        body: FeedbackIn,
    ) -> FeedbackAccepted:
        """In-app feedback → one email to the ops recipient (D-100). The third write surface.

        **Nothing is persisted** — no table, no migration, and the report therefore sits outside
        the D-094 deletion promise (the privacy notice says so). Behind `require_user`, so an
        invite-only beta needs no throttle beyond the model's length cap. The vertical and user
        agent are read server-side rather than trusted from the client.

        Guards: unconfigured mail (dev without `RESEND_API_KEY`) is a 503, a provider failure a
        502 — both retryable, and the SPA keeps the typed text either way. PII discipline: the
        message body is never logged.
        """
        profile = active_profile_for_user(engine, user.email)
        report = FeedbackReport(
            category=body.category,
            message=body.message,
            user_email=user.email,
            user_name=user.name,
            vertical=profile.vertical if profile is not None else None,
            page=body.page,
            user_agent=request.headers.get("user-agent"),
            submitted_at=datetime.now(UTC),
        )
        try:
            send_feedback(load_config(), report)
        except SendConfigError as exc:
            logger.error("feedback send is not configured: %s", exc)
            raise HTTPException(503, "Feedback is not configured on this server.") from exc
        except SendError as exc:
            logger.error("feedback send failed for user %s: %s", user.id, exc)
            raise HTTPException(502, "Couldn't send your feedback. Please try again.") from exc
        logger.info("feedback sent: category=%s user=%s", body.category.value, user.id)
        return FeedbackAccepted(status="sent")

    # No-login digest unsubscribe (D-094). GET = confirm page only (mail scanners prefetch GETs;
    # a prefetch must never change state); POST = the actual pause. The same POST serves the
    # confirm form and RFC-8058 one-click (providers POST `List-Unsubscribe=One-Click` to the
    # List-Unsubscribe URL) — the body is never read; the signed query token is identity + authz,
    # so no session/CSRF machinery applies. Registered before the SPA mount so the catch-all
    # can't shadow it.
    _invalid_unsub = _unsubscribe_page(
        "Link not valid",
        "<p>This unsubscribe link isn't valid. It may have been truncated by your mail client — "
        "try copying the full link, or manage email in your dashboard.</p>",
    )

    @app.get("/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
    def unsubscribe_confirm(
        engine: Annotated[Engine, Depends(_get_engine)],
        token: str | None = None,
    ) -> HTMLResponse:
        user = _resolve_unsubscribe_claim(engine, token)
        if user is None:
            return HTMLResponse(_invalid_unsub, status_code=400)
        action = f"/unsubscribe?token={quote(token or '', safe='')}"
        page = _unsubscribe_page(
            "Pause digest emails?",
            f"<p>Stop the daily digest for <strong>{escape(user.email)}</strong>? "
            "Matching and your dashboard keep running; only the email stops.</p>"
            f"<form method='post' action='{escape(action, quote=True)}'>"
            "<button type='submit' style='padding:.5rem 1rem'>Pause digest emails</button>"
            "</form>",
        )
        return HTMLResponse(page)

    @app.post("/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
    def unsubscribe_apply(
        engine: Annotated[Engine, Depends(_get_engine)],
        token: str | None = None,
    ) -> HTMLResponse:
        user = _resolve_unsubscribe_claim(engine, token)
        if user is None:
            return HTMLResponse(_invalid_unsub, status_code=400)
        set_digest_paused(engine, user_id=user.id, email=user.email, paused=True)
        page = _unsubscribe_page(
            "You're unsubscribed",
            f"<p>Digest emails to <strong>{escape(user.email)}</strong> are paused. "
            "Matching and your dashboard keep running.</p>",
        )
        return HTMLResponse(page)

    # Serve the built SPA same-origin in prod, if a real build exists (D-042/D-059). Gated on
    # index.html (not just the dir) so a stale/empty `dist/` doesn't mount a broken catch-all.
    # Registered last so `/api/*` and `/auth/*` win; the catch-all keeps deep-links off a 404.
    dist = frontend_dist_dir()
    if (dist / "index.html").is_file():
        _mount_spa(app, dist)

    return app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse `vja-api` args. Host/port default from env so the container honours Cloud Run's
    injected `$PORT` and binds `0.0.0.0` (via `VJA_API_HOST`), while local dev stays 127.0.0.1:8000.
    Explicit flags still override. (9.5a, D-059)"""
    parser = argparse.ArgumentParser(
        prog="vja-api", description="Serve the read-only dashboard API."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("VJA_API_HOST", "127.0.0.1"),
        help="bind host (default: $VJA_API_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="bind port (default: $PORT or 8000)",
    )
    return parser.parse_args(argv)


def api_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-api [--host H] [--port P]` — serve the read-only dashboard API via uvicorn."""
    import uvicorn

    load_dotenv()  # before _parse_args so .env-provided VJA_API_HOST/PORT feed the defaults
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # proxy_headers/forwarded_allow_ips: honour `X-Forwarded-Proto: https` behind Cloud Run's TLS
    # terminator so url_for() yields https (a backstop to VJA_PUBLIC_BASE_URL). 9.5a, D-059.
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(api_main())
