# Data Model Spec

*Build spec — concrete schema for Layer 1+. Supersedes the prose entity sketches in CLAUDE.md / Memo 02 where they differ.*

SQLite dialect (week 1), written to migrate cleanly to Postgres. Conventions: integer surrogate `id` PKs,
`*_at` columns are ISO-8601 UTC text in SQLite / `timestamptz` in Postgres. All times UTC.

**Implementation (Block 1):** the schema is SQLAlchemy Core in `vja.db.schema`, managed by Alembic (D-025). Concrete
type choices: enums are portable `VARCHAR` on **both** dialects (`native_enum=False`, keyed to and validated against
the `StrEnum` `.value`s in `vja.models` at the SQLAlchemy boundary; the initial migration created no DB CHECKs);
owned `*_at` columns are `DateTime(timezone=True)`; source-provided date strings
(`postings.posted_at`) stay text since ATS formats vary. The seed CSV is loaded by `vja.db.employers`.

## The two identity concepts (read this first)

The single most important modeling decision (see **D-016**):

- **`external_id`** answers *"is this the same posting as before?"* — a stable id issued by the ATS, unique per employer.
  **The daily diff keys on this.** Greenhouse/Lever/Ashby all return a stable job id.
- **`content_hash`** answers *"did this posting's content change since we last saw it?"* — drives the L2 extraction cache.
- **Fuzzy match** (normalized title+company+location) answers *"are these two different sources describing one role?"* —
  cross-source **dedup only**, invoked later, never used for the daily diff.

Do not conflate them. The diff is `external_id` set arithmetic per employer; nothing fuzzy happens in the diff.

---

## 1. `employers`

The curated universe. One row per company. Mirrors `data/seed/employers_seed.csv` (the seed CSV is the import source).

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `vertical` | TEXT NOT NULL | `aviation_software` \| `grid_power_software` |
| `name` | TEXT NOT NULL | display name |
| `tier` | TEXT | `Tier 1`…`Tier 5` \| `Bonus` — crawl-priority signal |
| `category` | TEXT | e.g. Utility / IPP, Quant Fund |
| `key_cities` | TEXT | US hubs (location pre-filter hint) |
| `role_tilt` | TEXT | expected role flavor |
| `ats_type` | TEXT NOT NULL | Layer-1 providers include `greenhouse`, `lever`, `ashby`, `workday`, `icims`, `workable`, `oracle_hcm`, `smartrecruiters`, `radancy`, `paylocity`, and `phenom`; unsupported/future and Layer-2 values remain in `vja.models.AtsType`, the source of truth. Mirrors the seed CSV + `docs/07`. |
| `ats_slug` | TEXT | company token for GH/Lever/Ashby; NULL otherwise |
| `careers_url` | TEXT | for workday/raw_html (and human reference) |
| `endpoint` | TEXT | constructed from type+slug for GH/Lever/Ashby; hand-set for workday |
| `source` | TEXT NOT NULL DEFAULT `'manual'` | `manual` \| `agent_discovered` |
| `status` | TEXT NOT NULL DEFAULT `'active'` | `proposed` \| `approved` \| `active` \| `retired` |
| `verification` | TEXT | `verified` \| `detected` \| `layer2` (ATS-resolution confidence — values used by the seed + `docs/07`; enum `vja.models.Verification`) |
| `early_career_volume_estimate` | INTEGER | optional |
| `notes` | TEXT | |
| `created_at` / `updated_at` | TEXT NOT NULL | |

Constraints: `UNIQUE(vertical, name)`. Index on `(vertical, status)`.
Only `status = 'active'` employers are fetched nightly. `proposed` = discovery-agent output awaiting human approval.

## 2. `sources`

Non-employer feeds (HN Who's-Hiring thread, niche boards, newsletters).

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `vertical` | TEXT NOT NULL | |
| `name` | TEXT NOT NULL | |
| `kind` | TEXT NOT NULL | `hn_whoishiring` \| `niche_board` \| `newsletter` |
| `url` | TEXT | |
| `ingestion_method` | TEXT NOT NULL | typed by how it's read (e.g. `llm_extract`) |
| `status` | TEXT NOT NULL DEFAULT `'active'` | |
| `created_at` | TEXT NOT NULL | |

## 3. `postings`

The heart of the diff. A posting belongs to **either** an employer **or** a source.

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `employer_id` | INTEGER FK→employers | nullable (NULL if from a source) |
| `source_id` | INTEGER FK→sources | nullable |
| `external_id` | TEXT NOT NULL | **diff key** — stable ATS job id (scoped per employer/source) |
| `content_hash` | TEXT NOT NULL | sha256 over canonical content (see below); drives extraction cache |
| `raw_payload` | TEXT NOT NULL | JSON as fetched (audit + re-extraction) |
| `apply_url` | TEXT | the link the digest sends users to; must pass verification |
| `status` | TEXT NOT NULL DEFAULT `'open'` | `open` \| `closed` |
| `first_seen_at` | TEXT NOT NULL | when first observed |
| `last_seen_at` | TEXT NOT NULL | bumped every fetch the posting is still present |
| `closed_at` | TEXT | set when it vanishes from the source |
| `source_updated_at` | TIMESTAMP | normalized "best-available ATS activity date" (D-038): the L1 `updated_at` when present (refreshed every sighting), else the extraction-filled `posted_at`; queries (D-030 windows / D-024 cap) fall back to `first_seen_at` when NULL |
| **extracted fields** (L2 fills these; NULL until extracted) | | |
| `title` | TEXT | |
| `level` | TEXT | `intern` \| `new_grad` \| `early_career` \| `mid` \| `senior` \| `unknown` |
| `location` | TEXT | |
| `remote` | TEXT | `onsite` \| `hybrid` \| `remote` \| `unknown` |
| `work_auth` | TEXT | visa/citizenship notes if stated |
| `stack` | TEXT | JSON array of technologies |
| `comp_min` / `comp_max` | INTEGER | if listed |
| `comp_raw` | TEXT | original comp string |
| `posted_at` | TEXT | source's posting date if available (raw, unnormalized string; normalized form lands in `source_updated_at`) |
| `extraction_model` | TEXT | model id used |
| `extracted_at` | TEXT | |

Constraints: `UNIQUE(employer_id, external_id)` (and a parallel uniqueness for source-based postings).
Index on `(employer_id, status)`, `(status, first_seen_at)`.

**`content_hash` definition (must be deterministic):**
`sha256` of a canonical JSON object built from the **stable content fields only** — for ATS sources that is
`{title, location, normalized_description_text}`. Explicitly **exclude** volatile junk: view counts, "updated X ago"
strings, tracking query params, request timestamps, and field ordering (sort keys before hashing).
Same `external_id` + changed `content_hash` ⇒ re-run extraction. Same hash ⇒ reuse cached extraction (free).

## 4. `profiles`

A matching profile = a resume + the vertical's domain vocabulary. Stored so matches can record which version they used.

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `user_email` | TEXT NOT NULL | |
| `vertical` | TEXT NOT NULL | a profile is per (user, vertical) |
| `resume_version` | TEXT NOT NULL | bump on every resume edit; matches reference this |
| `resume_text` | TEXT NOT NULL | |
| `domain_vocabulary` | TEXT | JSON array (steer matching prompt) — may come from vertical config |
| `active` | INTEGER NOT NULL DEFAULT 1 | |
| `created_at` | TEXT NOT NULL | |

## 5. `matches`

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `posting_id` | INTEGER FK→postings NOT NULL | |
| `profile_id` | INTEGER FK→profiles NOT NULL | |
| `resume_version` | TEXT NOT NULL | snapshot of the version matched against |
| `score` | INTEGER | cheap pre-filter / model score (0–100) |
| `verdict` | TEXT NOT NULL | `strong_yes` \| `yes` \| `maybe` \| `no` |
| `fits` | TEXT | what fits (required) |
| `gaps` | TEXT | what does NOT fit (required — D-007) |
| `rationale` | TEXT | full written argument |
| `model_version` | TEXT NOT NULL | |
| `trigger` | TEXT NOT NULL | `nightly` \| `backfill` \| `refresh` |
| `created_at` | TEXT NOT NULL | |

Constraints: `UNIQUE(posting_id, profile_id, resume_version)` — re-matching a new resume version makes a new row, not an overwrite.

## 6. `digests`

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `recipient` | TEXT NOT NULL | |
| `vertical` | TEXT NOT NULL | |
| `sent_at` | TEXT | NULL until sent |
| `status` | TEXT NOT NULL DEFAULT `'pending'` | `pending` \| `sent` \| `failed` |
| `contents` | TEXT NOT NULL | JSON: `{new:[...], closed:[...], trends:[...]}` — auditable record of exactly what shipped |
| `error` | TEXT | populated on failure (a failed send is itself an alert) |

## 7. `pipeline_runs`  (operational / observability)

Not in the original five, but required by the "every run writes a summary record" rule. A run that fails to send a
digest must leave a loud record here.

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | |
| `started_at` / `finished_at` | TEXT | |
| `status` | TEXT NOT NULL | `running` \| `ok` \| `partial` \| `failed` |
| `employers_fetched` | INTEGER | |
| `fetch_failures` | INTEGER | per-fetcher failures (loud-alert trigger) |
| `postings_new` / `postings_closed` | INTEGER | |
| `extraction_calls` / `match_calls` | INTEGER | |
| `llm_cost_usd` | REAL | metered from day one (D-005 cost discipline) |
| `errors` | TEXT | JSON list of structured errors |
| `notes` | TEXT | |

---

## Posting lifecycle (the diff, precisely)

For each active employer, per nightly fetch:
1. Fetch current postings → set of `external_id`s with payloads.
2. `new = fetched_ids − stored_open_ids` → insert as `open`, `first_seen = last_seen = now`. Flag for L2 extraction.
3. `still_present = fetched_ids ∩ stored_open_ids` → bump `last_seen = now`. If `content_hash` changed, re-flag for extraction.
4. `closed = stored_open_ids − fetched_ids` → set `status = closed`, `closed_at = now`. **Never delete.**
5. Only `new` + content-changed postings enter Layer 2. Everything else is free.

Lifespan stat per company = `closed_at − first_seen_at`, aggregated. This is the "how fast must I apply" dataset.
