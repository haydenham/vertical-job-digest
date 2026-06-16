"""SQLAlchemy Core schema — the canonical translation of `docs/04`.

One `MetaData` holding all seven tables. Alembic autogenerates migrations from this,
and `docs/08` integration tests build their DB from those migrations. Conventions:

- Enums are stored as VARCHAR + CHECK on **both** dialects (`native_enum=False`),
  keyed to the `.value`s of the `StrEnum`s in `vja.models` — no Postgres native-enum
  migration pain, and the DB CHECK always matches the code enum.
- Timestamps we own are `DateTime(timezone=True)` (UTC). Source-provided date strings
  (`postings.posted_at`) stay `Text` — ATS formats vary; don't fail on them.
- JSON payloads use `sa.JSON` (portable across SQLite/Postgres).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import (
    JSON,
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
)
from sqlalchemy import (
    Enum as SAEnum,
)

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
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
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
    Column("created_at", DateTime(timezone=True), nullable=False),
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
    Column(
        "status",
        _enum(PostingStatus, "posting_status"),
        nullable=False,
        server_default=PostingStatus.OPEN.value,
    ),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("closed_at", DateTime(timezone=True)),
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
    Column("extraction_model", String),
    Column("extracted_at", DateTime(timezone=True)),
    UniqueConstraint("employer_id", "external_id", name="uq_postings_employer_external"),
    UniqueConstraint("source_id", "external_id", name="uq_postings_source_external"),
    # A posting belongs to exactly one of employer / source.
    CheckConstraint(
        "(employer_id IS NULL) <> (source_id IS NULL)",
        name="ck_postings_employer_xor_source",
    ),
    Index("ix_postings_employer_status", "employer_id", "status"),
    Index("ix_postings_status_first_seen", "status", "first_seen_at"),
)


profiles = Table(
    "profiles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_email", String, nullable=False),
    Column("vertical", String, nullable=False),
    Column("resume_version", String, nullable=False),
    Column("resume_text", Text, nullable=False),
    Column("domain_vocabulary", JSON),
    Column("active", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
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
    Column("created_at", DateTime(timezone=True), nullable=False),
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
    Column("sent_at", DateTime(timezone=True)),
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
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", _enum(PipelineRunStatus, "pipeline_run_status"), nullable=False),
    Column("employers_fetched", Integer),
    Column("fetch_failures", Integer),
    Column("postings_new", Integer),
    Column("postings_closed", Integer),
    Column("extraction_calls", Integer),
    Column("match_calls", Integer),
    Column("llm_cost_usd", Float),
    Column("errors", JSON),
    Column("notes", Text),
)
