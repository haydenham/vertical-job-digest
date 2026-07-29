"""SQLAlchemy Core schema — the canonical translation of `docs/04`.

One `MetaData` holding all seven tables. Alembic autogenerates migrations from this,
and `docs/08` integration tests build their DB from those migrations. Conventions:

- Enums are stored as portable VARCHAR columns on **both** dialects (`native_enum=False`),
  keyed to the `.value`s of the `StrEnum`s in `vja.models`. SQLAlchemy validates values at
  the application boundary; the database has no native enum or CHECK to migrate when a
  provider is added (the initial schema's longest ATS value fixes this column at VARCHAR(15)).
- Timestamps we own are `UTCDateTime()` (UTC). Source-provided date strings
  (`postings.posted_at`) stay `Text` — ATS formats vary; don't fail on them.
- JSON payloads use `sa.JSON` (portable across SQLite/Postgres).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

from vja.models import (
    AtsType,
    DigestStatus,
    EmployerSource,
    EmployerStatus,
    Level,
    MatchTrigger,
    PipelineRunStatus,
    PostingStatus,
    RemoteType,
    SourceKind,
    Verdict,
    Verification,
)


class UTCDateTime(TypeDecorator[datetime]):
    """A `DateTime` that always stores/returns tz-aware UTC, on every dialect.

    SQLite has no real datetime type and drops `tzinfo` on read (returning naive values);
    Postgres' `timestamptz` keeps it. This normalizes both ends — inbound values are
    converted to UTC, outbound naive values get UTC re-attached — so application code never
    juggles naive-vs-aware datetimes. The underlying column type is unchanged
    (`DateTime(timezone=True)`), so there's no DDL/migration change.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


def _enum(py_enum: type[StrEnum], name: str) -> SAEnum:
    """A portable VARCHAR+CHECK enum keyed to the StrEnum's `.value`s (not member names)."""
    return SAEnum(
        py_enum,
        native_enum=False,
        validate_strings=True,
        values_callable=_enum_values,
        name=name,
    )


metadata = MetaData()


employers = Table(
    "employers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("vertical", String, nullable=False),
    Column("name", String, nullable=False),
    Column("tier", String),
    Column("category", String),
    Column("key_cities", String),
    Column("role_tilt", String),
    Column("ats_type", _enum(AtsType, "ats_type"), nullable=False),
    Column("ats_slug", String),
    Column("careers_url", String),
    Column("endpoint", String),
    Column(
        "source",
        _enum(EmployerSource, "employer_source"),
        nullable=False,
        server_default=EmployerSource.MANUAL.value,
    ),
    Column(
        "status",
        _enum(EmployerStatus, "employer_status"),
        nullable=False,
        server_default=EmployerStatus.ACTIVE.value,
    ),
    Column("verification", _enum(Verification, "verification")),
    Column("early_career_volume_estimate", Integer),
    Column("notes", Text),
    Column("created_at", UTCDateTime(), nullable=False),
    Column("updated_at", UTCDateTime(), nullable=False),
    UniqueConstraint("vertical", "name", name="uq_employers_vertical_name"),
    Index("ix_employers_vertical_status", "vertical", "status"),
)


sources = Table(
    "sources",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("vertical", String, nullable=False),
    Column("name", String, nullable=False),
    Column("kind", _enum(SourceKind, "source_kind"), nullable=False),
    Column("url", String),
    Column("ingestion_method", String, nullable=False),
    Column("status", String, nullable=False, server_default=EmployerStatus.ACTIVE.value),
    Column("created_at", UTCDateTime(), nullable=False),
)


postings = Table(
    "postings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employer_id", Integer, ForeignKey("employers.id")),
    Column("source_id", Integer, ForeignKey("sources.id")),
    Column("external_id", String, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("raw_payload", JSON, nullable=False),
    Column("apply_url", String),
    # The posting body as readable plain text (`vja.text.html_to_text`), for the dashboard's
    # detail panel. L1-authoritative like `location`: written from the fetcher's description at
    # insert/update, and filled at extraction *only when still NULL* — which is how the list-only
    # ATSs (whose list endpoint omits the body) get one, from the detail they already fetch.
    # NOT part of `content_hash`, which keys on the fetcher's raw string. (D-095)
    Column("description", Text),
    Column(
        "status",
        _enum(PostingStatus, "posting_status"),
        nullable=False,
        server_default=PostingStatus.OPEN.value,
    ),
    Column("first_seen_at", UTCDateTime(), nullable=False),
    Column("last_seen_at", UTCDateTime(), nullable=False),
    Column("closed_at", UTCDateTime()),
    # Normalized "best-available ATS activity date" (D-038): the L1 `updated_at` when present,
    # else the extraction-filled `posted_at`. Queries (D-030 windows / D-024 cap) fall back to
    # `first_seen_at` when NULL. The raw `posted_at` (below) stays the unnormalized source string.
    Column("source_updated_at", UTCDateTime()),
    # --- extracted fields (Layer 2 fills these; NULL until extracted) ---
    Column("title", String),
    Column("level", _enum(Level, "level")),
    Column("location", String),
    Column("remote", _enum(RemoteType, "remote_type")),
    Column("work_auth", String),
    Column("stack", JSON),
    Column("comp_min", Integer),
    Column("comp_max", Integer),
    Column("comp_raw", String),
    Column("posted_at", Text),
    # Durable Stage-A+B in-scope marker (computed at extraction from `passes_prefilter`): the
    # "cleaned" dashboard tier floors on this instead of re-deriving the geo/level gate in SQL.
    # NULL until extracted; the gates are vertical config, so it's resume-independent. (D-043)
    Column("in_scope", Boolean),
    Column("extraction_model", String),
    Column("extracted_at", UTCDateTime()),
    UniqueConstraint("employer_id", "external_id", name="uq_postings_employer_external"),
    UniqueConstraint("source_id", "external_id", name="uq_postings_source_external"),
    # A posting belongs to exactly one of employer / source.
    CheckConstraint(
        "(employer_id IS NULL) <> (source_id IS NULL)",
        name="ck_postings_employer_xor_source",
    ),
    Index("ix_postings_employer_status", "employer_id", "status"),
    Index("ix_postings_status_first_seen", "status", "first_seen_at"),
    # Recency-window queries (D-030 dashboard toggles / D-024 backfill cap) filter open postings
    # by `source_updated_at`; the existing `status_first_seen` index covers the COALESCE fallback.
    Index("ix_postings_status_source_updated", "status", "source_updated_at"),
)


# The authenticated identity (Phase 9.2, D-055). One row per person; `google_sub` is the stable
# Google account id, set at first OIDC login (nullable so a seed/email identity can pre-exist and be
# adopted on login). PII tier alongside profiles/matches/digests (docs/11 §2) — never denormalized
# into the shared employers/postings tables.
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("google_sub", String, unique=True),
    Column("email", String, nullable=False, unique=True),
    Column("name", String),
    Column("created_at", UTCDateTime(), nullable=False),
    # D-085: the first profile upload does not consume this clock. Each accepted changed-résumé
    # upload advances it atomically, enforcing one reupload per user per rolling 24 hours.
    Column("last_resume_reupload_at", UTCDateTime()),
    # D-094: pauses the digest *email* only (matching + dashboard continue). Lives on `users`,
    # not the versioned `profiles`, so a résumé reupload can't reset it.
    Column("digest_paused", Boolean, nullable=False, server_default=false()),
)


profiles = Table(
    "profiles",
    metadata,
    Column("id", Integer, primary_key=True),
    # Identity still anchors on email (D-027); `user_id` is the FK to the authenticated `users` row,
    # backfilled by email on first login (D-055). Nullable: a profile can pre-exist login (seed).
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("user_email", String, nullable=False),
    Column("vertical", String, nullable=False),
    Column("resume_version", String, nullable=False),
    Column("resume_text", Text, nullable=False),
    Column("domain_vocabulary", JSON),
    Column("active", Integer, nullable=False, server_default="1"),
    Column("created_at", UTCDateTime(), nullable=False),
    # Backfill status stamps (D-082): the upload endpoint stamps `started` before scheduling the
    # background backfill (so the SPA's immediate /api/me probe already sees it); `run_backfill`
    # stamps `completed` on exit. `/api/me` derives running/done from their ordering + staleness.
    Column("backfill_started_at", UTCDateTime()),
    Column("backfill_completed_at", UTCDateTime()),
)


matches = Table(
    "matches",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("posting_id", Integer, ForeignKey("postings.id"), nullable=False),
    Column("profile_id", Integer, ForeignKey("profiles.id"), nullable=False),
    Column("resume_version", String, nullable=False),
    Column("score", Integer),
    Column("verdict", _enum(Verdict, "verdict"), nullable=False),
    Column("fits", Text),
    Column("gaps", Text),
    Column("rationale", Text),
    Column("model_version", String, nullable=False),
    Column("trigger", _enum(MatchTrigger, "match_trigger"), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    UniqueConstraint(
        "posting_id",
        "profile_id",
        "resume_version",
        name="uq_matches_posting_profile_version",
    ),
)


digests = Table(
    "digests",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("recipient", String, nullable=False),
    Column("vertical", String, nullable=False),
    Column("sent_at", UTCDateTime()),
    Column(
        "status",
        _enum(DigestStatus, "digest_status"),
        nullable=False,
        server_default=DigestStatus.PENDING.value,
    ),
    Column("contents", JSON, nullable=False),
    Column("error", Text),
)


pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("started_at", UTCDateTime()),
    Column("finished_at", UTCDateTime()),
    Column("status", _enum(PipelineRunStatus, "pipeline_run_status"), nullable=False),
    Column("employers_fetched", Integer),
    Column("fetch_failures", Integer),
    Column("postings_new", Integer),
    # Persisted as of D-103: `reopen_posting` overwrites `first_seen_at` and nulls `closed_at`, so
    # a reopen leaves no trace on the posting row itself. Without this column the only durable
    # record of close/reopen churn was Cloud Logging, which ages out.
    Column("postings_reopened", Integer),
    Column("postings_closed", Integer),
    Column("extraction_calls", Integer),
    Column("match_calls", Integer),
    Column("llm_cost_usd", Float),
    # Real per-run token accounting (D-069) survives when the best-effort catalog estimate is NULL,
    # so cached-vs-uncached and input-vs-output behavior remains queryable (D-090).
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cache_read_tokens", Integer),
    Column("cache_write_tokens", Integer),
    Column("errors", JSON),
    Column("notes", Text),
)
