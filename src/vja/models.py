"""Core domain models + the enums that are the schema's source of truth.

Mirrors `docs/04` (data model) and `docs/05` (fetcher contract). Vertical-agnostic
by rule (D-004): no company or vertical names appear in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AtsType(StrEnum):
    """The applicant-tracking system a fetcher (or Layer 2) handles for an employer.

    Reconciles `docs/04` §1's short list with the values actually present in
    `data/seed/employers_seed.csv` + the seed README, grouped by build tier (`docs/07`).
    """

    # Layer 1 deterministic fetchers — Tier A (weeks 1–2 / next)
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    # Tier B/C platforms — future generic fetchers (docs/07)
    ICIMS = "icims"
    WORKABLE = "workable"
    ORACLE_HCM = "oracle_hcm"
    SMARTRECRUITERS = "smartrecruiters"
    JOBVITE = "jobvite"
    SUCCESSFACTORS = "successfactors"
    AVATURE = "avature"
    UKG = "ukg"
    EIGHTFOLD = "eightfold"
    # Layer 2 LLM-read (no clean API) + placeholders
    RADANCY = "radancy"
    CUSTOM = "custom"
    RAW_HTML = "raw_html"
    UNKNOWN = "unknown"


class Level(StrEnum):
    """Career level (Layer 2 extracts this; `docs/04` postings.level)."""

    INTERN = "intern"
    NEW_GRAD = "new_grad"
    EARLY_CAREER = "early_career"
    MID = "mid"
    SENIOR = "senior"
    UNKNOWN = "unknown"


class RemoteType(StrEnum):
    """Work arrangement (`docs/04` postings.remote)."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class Verdict(StrEnum):
    """Match verdict — willingness to say `no` is a product requirement (D-007)."""

    STRONG_YES = "strong_yes"
    YES = "yes"
    MAYBE = "maybe"
    NO = "no"


class Verification(StrEnum):
    """Confidence in an employer's ATS resolution (`docs/04` §1, seed README, `docs/07`).

    Note: these are the values actually used by the seed CSV + the ATS-identification pass
    (`detected`/`layer2`), reconciling `docs/04`'s earlier verified/suspect/unverified wording.
    """

    VERIFIED = "verified"  # endpoint hit live and returned jobs / a valid API
    DETECTED = "detected"  # platform known, endpoint not yet live-confirmed
    LAYER2 = "layer2"  # no clean API → routed to Layer-2 LLM-read


class EmployerStatus(StrEnum):
    """Lifecycle of an employer in the universe (`docs/04` §1). Only `active` is fetched."""

    PROPOSED = "proposed"  # discovery-agent output awaiting human approval
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"


class EmployerSource(StrEnum):
    """How an employer entered the universe (`docs/04` §1)."""

    MANUAL = "manual"
    AGENT_DISCOVERED = "agent_discovered"


class PostingStatus(StrEnum):
    """Posting lifecycle — vanished postings go `closed`, never deleted (D-009)."""

    OPEN = "open"
    CLOSED = "closed"


class SourceKind(StrEnum):
    """Type of a non-employer feed (`docs/04` §2)."""

    HN_WHOISHIRING = "hn_whoishiring"
    NICHE_BOARD = "niche_board"
    NEWSLETTER = "newsletter"


class MatchTrigger(StrEnum):
    """What caused a match to be computed (`docs/04` §5, D-006)."""

    NIGHTLY = "nightly"
    BACKFILL = "backfill"
    REFRESH = "refresh"


class DigestStatus(StrEnum):
    """Delivery state of a digest — a failed send is itself an alert (`docs/04` §6)."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class PipelineRunStatus(StrEnum):
    """Outcome of a nightly run (`docs/04` §7)."""

    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Employer:
    """The fetch-facing view of an employer row (`docs/04` §1).

    Only the fields a fetcher reads to locate + identify postings live here. The full
    DB mapping (tier, status, verification, timestamps, …) is added in the DB-import
    chunk. Frozen: a fetcher is a pure read (`docs/05`) and never mutates its input.
    """

    id: int
    vertical: str
    name: str
    ats_type: AtsType
    ats_slug: str | None = None
    endpoint: str | None = None
    careers_url: str | None = None


@dataclass(frozen=True, slots=True)
class RawPosting:
    """A single posting exactly as a Layer-1 fetcher produces it (`docs/05`).

    The fetcher does NOT extract structured fields (level, stack, comp) — that is
    Layer 2's job. `external_id` is the ATS's own stable id and is THE diff key
    (D-016); it is never synthesized from the title.

    `raw` is a dict, so `frozen=True` prevents rebinding the attribute but not deep
    mutation of the payload — treat `raw` as read-only by convention.
    """

    external_id: str
    title: str
    apply_url: str
    location: str | None
    updated_at: str | None
    raw: dict[str, Any]
