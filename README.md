# Vertical Job Intelligence Agent

A scheduled pipeline that achieves **total coverage of a small, bounded employer universe**
(~40 companies per vertical), diffs postings daily, and delivers a digest of new/closed roles
with an LLM-written, reasoned match against the user's resume.

Not a live chat agent. Not a horizontal job board. **The diff is the product.**

> Status: **building Phase 3 (bare digest).** Phases 0–2 are done (data model, Layer-1 GH/Lever/Ashby
> fetchers, fetch→diff→persist, orchestration). The diff now renders + sends as an email via Resend;
> matching (Layer 2) and the Workday fetcher are next.

## How it works (three layers, cheap deterministic path first)

1. **Layer 1 — ATS spine.** Deterministic fetchers against public ATS JSON endpoints
   (Greenhouse, Lever, Ashby; Workday later). Cheap, reliable, covers most of the universe.
2. **Layer 2 — LLM extraction & matching.** Runs only on items the Layer 1 diff flags as new/changed.
   Normalizes unstructured postings; writes match rationale (what fits, what doesn't, a verdict).
3. **Layer 3 — agentic discovery (later).** Weekly agent that finds new *employers*, not postings.

A **vertical is configuration, not code**: an employer list + niche sources + a matching profile.
Adding a vertical should cost only curation + a config file.

## Launch verticals

- **Grid / power software** — utilities/IPPs, power trading, quant funds, energy-data SaaS, grid-tech
  startups, ISOs/RTOs. (54 employers seeded.)
- **Aviation software** — airline ops/tech, platforms, flight-data companies, startups. (Not yet seeded.)

## Repository layout

```
CLAUDE.md                     # working spec for the AI agent + doc map / order of authority
README.md                     # you are here
DECISIONS.md                  # decision log (ADRs)
WORKLOG.md                    # append-only session log
docs/
  01-business-concept-white-paper.md
  02-technical-high-level-write-up.md
  03-future-and-open-questions.md
  04-data-model-spec.md       # concrete schema (diff keys on external_id)
  05-fetcher-interface-spec.md# common Fetcher contract + per-ATS modules
  06-vertical-config-spec.md  # "a vertical is config"
data/
  seed/
    employers_seed.csv        # the curated employer universe
    README.md                 # CSV column + verification guide
```

## Stack

Python pipeline · `uv` toolchain · FastAPI (read-only dashboard API) · SQLite → Postgres ·
Anthropic SDK for model calls · Resend for the email digest · cron/launchd scheduling (local, week 1) · React dashboard (later).

## Running the pipeline

The nightly job is two commands — fetch/diff/persist, then build/send the digest:

```sh
vja-run      --vertical grid_power_software   # fetch → diff → persist (writes a pipeline_runs row)
vja-digest   --vertical grid_power_software   # build → verify links → render → send via Resend
```

Omit `--vertical` to process all active verticals. Config comes from the environment (a local `.env`
is loaded automatically — it is git-ignored, never commit secrets):

| var | purpose |
|---|---|
| `RESEND_API_KEY` | Resend API key (required to send; `resend-api-key` also accepted) |
| `VJA_DIGEST_RECIPIENT` | digest recipient. With the sandbox sender this must be your Resend account email |
| `VJA_DIGEST_FROM` | sender; defaults to the Resend sandbox `onboarding@resend.dev` (set a verified domain to send anywhere) |
| `VJA_DATABASE_URL` | DB URL; defaults to local SQLite `sqlite:///data/vja.db` |

An empty digest (nothing new or closed) sends no email by design (D-028).

## Build sequence (phases)

A **phase** is a milestone; a **block** is one PR-sized unit inside it. Order set by D-026 (Workday pulled ahead of
matching/dashboard — biggest coverage win, and pure Layer 1). Phases 0–2 are built; 2 is finishing.

1. **Phase 0–1:** docs/prep, then core logic (models, `content_hash`, GH/Lever/Ashby fetchers, diff). ✅
2. **Phase 2:** persistence + Layer-1 implementation — DB, fetch→diff→persist, orchestration.
3. **Phase 3:** bare daily digest (no LLM) — verify links, email via Resend, schedule. *First diff in the inbox = proof of loop.*
4. **Phase 4:** Workday fetcher — coverage ~9→24 of 54 (the high-volume employers).
5. **Phase 5:** LLM extraction + matching (negative-case rationale + verification; two-stage cheap filter).
6. **Phase 6:** read-only dashboard — match table with recency toggles (new today / week / 2 weeks / all open), keyed on ATS posting dates (D-030).
7. **Phase 7:** aviation vertical — the architecture test (config + curation only).
8. **Phase 8+:** remaining ATS coverage (Tier-B, HN/niche), then the discovery agent. Postgres/host cutover when demo users land.

## Documentation discipline

This project documents as it builds. Every session updates `WORKLOG.md`; every re-litigable decision lands
in `DECISIONS.md`; build specs in `docs/04+` are the source of truth. See `CLAUDE.md` for the full doc map
and order of authority.
