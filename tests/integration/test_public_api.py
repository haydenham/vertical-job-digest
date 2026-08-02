"""Integration tests for the login-free demo board (`/api/public/*`, D-105).

Two things are being pinned here, and only one of them is ordinary plumbing.

The ordinary half is the shape: window mapping, the vertical toggle's counts, 404s, cache headers.

The half that matters is **that no match text can reach an anonymous caller**. Match rationale is
résumé-derived commentary about named beta users, and D-067 turned `VJA_AUTH_REQUIRED` on precisely
so it could not be read without a session. The demo board is defended structurally at two layers —
a statement that never joins `matches`, and a response model that does not declare the match fields
— and both layers are asserted below, along with the fact that the *authenticated* endpoint still
401s anonymously. A regression in any of those is a data leak, not a bug.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import Engine

from vja.api.app import create_app
from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.postings import dashboard_statement, open_posting_counts_by_vertical
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import employers, postings

_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
_VERTICAL = "grid_power_software"
_OTHER_VERTICAL = "aviation_software"

_MATCH_FIELDS = ("verdict", "score", "fits", "gaps", "rationale")


def _client(engine: Engine) -> TestClient:
    return TestClient(create_app(engine))


def _employer(engine: Engine, *, vertical: str = _VERTICAL, name: str = "GridCo") -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type="greenhouse",
                ats_slug=name.lower(),
                source="manual",
                status="active",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _posting(
    engine: Engine,
    employer_id: int,
    title: str,
    *,
    first_seen: datetime = _NOW,
    in_scope: bool = True,
    status: str = "open",
    description: str | None = None,
    comp_min: int | None = None,
    comp_max: int | None = None,
    comp_raw: str | None = None,
) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=title,
                content_hash=f"h-{title}",
                raw_payload={},
                title=title,
                apply_url=f"https://example.com/{title}",
                status=status,
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                extracted_at=first_seen,
                in_scope=in_scope,
                description=description,
                comp_min=comp_min,
                comp_max=comp_max,
                comp_raw=comp_raw,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _profile(engine: Engine, *, email: str = "beta-user@example.com") -> Profile:
    upsert_profile(
        engine, user_email=email, vertical=_VERTICAL, resume_text=email, domain_vocabulary=[]
    )
    return next(p for p in active_profiles(engine, _VERTICAL) if p.user_email == email)


def _match(engine: Engine, posting_id: int, profile: Profile) -> None:
    """A real match row, with the kind of personal text the public board must never expose."""
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {
                "verdict": "strong_yes",
                "score": 91,
                "fits": '["five years of grid telemetry work"]',
                "gaps": '["no Rust in the r\\u00e9sum\\u00e9"]',
                "rationale": "Their SCADA background maps directly onto this team.",
            },
            model="claude-sonnet-4-6",
            trigger="nightly",
            now=_NOW,
        )


# ---- the anti-leak contract ------------------------------------------------------------------


def test_public_postings_carry_no_match_fields_even_when_matches_exist(
    migrated_engine: Engine,
) -> None:
    """The whole point of the demo board: real rows, zero résumé commentary.

    A match row exists for this exact posting, so a query that merely forgot to filter would
    happily serve someone else's rationale. Asserting on *keys* rather than values is deliberate —
    a `null` verdict would still tell a stranger the field exists and invite the next mistake.
    """
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    posting_id = _posting(migrated_engine, emp, "Grid Software Engineer")
    _match(migrated_engine, posting_id, prof)

    body = (
        _client(migrated_engine).get("/api/public/postings", params={"vertical": _VERTICAL}).json()
    )

    assert body["count"] == 1
    row = body["postings"][0]
    assert row["title"] == "Grid Software Engineer"
    for field in _MATCH_FIELDS:
        assert field not in row
    # Belt and braces: the personal text is nowhere in the serialized payload at all.
    assert "SCADA" not in str(body)


def test_anonymous_statement_never_references_the_matches_table() -> None:
    """Layer 1, asserted at the SQL level (D-105).

    The response model omitting the fields is not enough on its own — this pins that the anonymous
    query cannot even *read* them, so the protection survives someone later adding fields to the
    model.
    """
    sql = str(dashboard_statement(_VERTICAL, None, None, cutoff=None, cleaned=True))
    assert "matches" not in sql

    authed = str(dashboard_statement(_VERTICAL, 1, "v1", cutoff=None, cleaned=True))
    assert "matches" in authed  # the control: the join is real on the authenticated path


def test_matched_view_without_a_profile_is_a_programming_error() -> None:
    """ "Matched" means "against this résumé". Without one the request is malformed, not empty."""
    with pytest.raises(ValueError, match="requires a profile_id"):
        dashboard_statement(_VERTICAL, None, None, cutoff=None, cleaned=False)


def test_public_endpoints_are_open_while_the_private_one_still_401s(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demo must not have been bought by weakening D-067's auth guard."""
    monkeypatch.setenv("VJA_AUTH_REQUIRED", "1")
    emp = _employer(migrated_engine)
    posting_id = _posting(migrated_engine, emp, "Grid Software Engineer")
    client = _client(migrated_engine)

    assert client.get("/api/public/verticals").status_code == 200
    assert client.get("/api/public/postings", params={"vertical": _VERTICAL}).status_code == 200
    detail = client.get(f"/api/public/postings/{posting_id}", params={"vertical": _VERTICAL})
    assert detail.status_code == 200

    assert client.get("/api/postings", params={"vertical": _VERTICAL}).status_code == 401


# ---- the board itself ------------------------------------------------------------------------


def test_public_postings_is_the_whole_in_scope_open_set(migrated_engine: Engine) -> None:
    """No `view` axis: unassessed rows are the norm here, and out-of-scope/closed never show."""
    emp = _employer(migrated_engine)
    _posting(migrated_engine, emp, "in-scope open")
    _posting(migrated_engine, emp, "out-of-scope", in_scope=False)
    _posting(migrated_engine, emp, "closed", status="closed")

    body = (
        _client(migrated_engine).get("/api/public/postings", params={"vertical": _VERTICAL}).json()
    )

    assert [p["title"] for p in body["postings"]] == ["in-scope open"]
    assert body["vertical"] == _VERTICAL
    assert body["window"] == "all"


@freeze_time(_NOW)
def test_window_maps_the_same_way_as_the_authenticated_dashboard(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    _posting(migrated_engine, emp, "today", first_seen=_NOW)
    _posting(migrated_engine, emp, "old", first_seen=_NOW - timedelta(days=30))
    client = _client(migrated_engine)

    all_open = client.get("/api/public/postings", params={"vertical": _VERTICAL}).json()
    assert sorted(p["title"] for p in all_open["postings"]) == ["old", "today"]

    week = client.get(
        "/api/public/postings", params={"vertical": _VERTICAL, "window": "week"}
    ).json()
    assert [p["title"] for p in week["postings"]] == ["today"]
    assert week["window"] == "week"


def test_salary_judgment_stays_server_side(migrated_engine: Engine) -> None:
    """`comp_display` is the `vja.comp` guard's answer (D-087/D-095) — a stranger gets the same
    judgment a logged-in user does, never the raw integers to format themselves."""
    emp = _employer(migrated_engine)
    _posting(
        migrated_engine,
        emp,
        "paid",
        comp_min=150_000,
        comp_max=180_000,
        comp_raw="$150,000 - $180,000 per year",
    )
    _posting(migrated_engine, emp, "hourly", comp_min=60, comp_max=80, comp_raw="$60-$80 per hour")

    body = (
        _client(migrated_engine).get("/api/public/postings", params={"vertical": _VERTICAL}).json()
    )
    rows = {p["title"]: p for p in body["postings"]}

    assert rows["paid"]["comp_display"] == "$150,000 – $180,000"
    assert rows["hourly"]["comp_display"] is None  # not annual → suppressed, never fabricated


def test_public_detail_returns_the_body_and_404s_across_verticals(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    mine = _posting(migrated_engine, emp, "mine", description="The role body.")
    other_emp = _employer(migrated_engine, vertical=_OTHER_VERTICAL, name="AirCo")
    theirs = _posting(migrated_engine, other_emp, "theirs", description="Another vertical.")
    client = _client(migrated_engine)

    ok = client.get(f"/api/public/postings/{mine}", params={"vertical": _VERTICAL})
    assert ok.status_code == 200
    assert ok.json() == {"posting_id": mine, "description": "The role body."}

    # An id from another vertical is not readable by asking for the wrong vertical.
    assert (
        client.get(f"/api/public/postings/{theirs}", params={"vertical": _VERTICAL}).status_code
        == 404
    )


def test_unknown_vertical_is_404_on_every_public_endpoint(migrated_engine: Engine) -> None:
    """Unvalidated, `vertical` would be a free existence oracle and an unbounded cache key."""
    client = _client(migrated_engine)
    assert (
        client.get("/api/public/postings", params={"vertical": "crypto_rugpulls"}).status_code
        == 404
    )
    assert (
        client.get("/api/public/postings/1", params={"vertical": "crypto_rugpulls"}).status_code
        == 404
    )


# ---- the toggle's source ---------------------------------------------------------------------


def test_public_verticals_lists_only_verticals_with_roles(migrated_engine: Engine) -> None:
    """The mirror image of `/api/verticals` (which must stay joinable at zero rows, the B-4 fix):
    a demo toggle that opens onto an empty table reads as a broken product."""
    grid = _employer(migrated_engine)
    _posting(migrated_engine, grid, "grid one")
    _posting(migrated_engine, grid, "grid two")
    air = _employer(migrated_engine, vertical=_OTHER_VERTICAL, name="AirCo")
    _posting(migrated_engine, air, "air one")
    _posting(migrated_engine, air, "air hidden", in_scope=False)

    got = _client(migrated_engine).get("/api/public/verticals").json()

    # Biggest universe first, so the demo's default lands on the fullest board.
    assert got == [
        {"vertical": _VERTICAL, "count": 2},
        {"vertical": _OTHER_VERTICAL, "count": 1},
    ]


def test_counts_exclude_closed_and_out_of_scope(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    _posting(migrated_engine, emp, "open in scope")
    _posting(migrated_engine, emp, "closed", status="closed")
    _posting(migrated_engine, emp, "not in scope", in_scope=False)

    assert open_posting_counts_by_vertical(migrated_engine) == {_VERTICAL: 1}


# ---- caching, the abuse guard ----------------------------------------------------------------


def test_public_responses_carry_the_edge_cache_header(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    posting_id = _posting(migrated_engine, emp, "cached")
    client = _client(migrated_engine)
    expected = "public, max-age=300, s-maxage=900"

    assert client.get("/api/public/verticals").headers["cache-control"] == expected
    listing = client.get("/api/public/postings", params={"vertical": _VERTICAL})
    assert listing.headers["cache-control"] == expected
    detail = client.get(f"/api/public/postings/{posting_id}", params={"vertical": _VERTICAL})
    assert detail.headers["cache-control"] == expected


@freeze_time(_NOW)
def test_repeat_requests_are_served_from_cache_per_vertical_and_window(
    migrated_engine: Engine,
) -> None:
    """There is no rate limiting anywhere in the app, so this cache is the abuse guard (D-105).

    A row inserted between two identical requests must NOT appear in the second — that staleness is
    the evidence the second request never reached the database. It is also harmless: the pipeline
    only moves these rows every four hours (D-103).
    """
    emp = _employer(migrated_engine)
    _posting(migrated_engine, emp, "first")
    client = _client(migrated_engine)

    assert client.get("/api/public/postings", params={"vertical": _VERTICAL}).json()["count"] == 1
    _posting(migrated_engine, emp, "second")
    assert client.get("/api/public/postings", params={"vertical": _VERTICAL}).json()["count"] == 1

    # A different window is a different key, so it recomputes and sees both rows.
    fresh = client.get("/api/public/postings", params={"vertical": _VERTICAL, "window": "all"})
    assert fresh.json()["count"] == 1  # same (vertical, window) key as the default
    other = client.get(
        "/api/public/postings", params={"vertical": _VERTICAL, "window": "two_weeks"}
    )
    assert other.json()["count"] == 2
