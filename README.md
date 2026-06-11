# Vertical Job Intelligence Agent

A scheduled pipeline that achieves **total coverage of a small, bounded employer universe**
(~40 companies per vertical), diffs postings daily, and delivers a digest of new/closed roles
with an LLM-written, reasoned match against the user's resume.

Not a live chat agent. Not a horizontal job board. **The diff is the product.**

> Status: **planning / pre-build.** Architecture and data model are specified; the seed universe
> for the first vertical is curated. No pipeline code is written yet — Layer 1 is next.

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

## Build sequence

- **Weeks 1–2:** Layer 1 skeleton, grid vertical only — employer table, Greenhouse/Lever/Ashby
  fetchers, postings table, diff job, bare daily email. No LLM yet. First diff in the inbox = proof of loop.
- **Week 3:** LLM extraction + matching (with negative-case rationale + verification) and a minimal dashboard.
- **Week 4:** Add the aviation vertical — the architecture test (config + curation only).
- **After:** Workday/known-ATS fetchers, HN extraction, discovery agent, dashboard polish.

## Documentation discipline

This project documents as it builds. Every session updates `WORKLOG.md`; every re-litigable decision lands
in `DECISIONS.md`; build specs in `docs/04+` are the source of truth. See `CLAUDE.md` for the full doc map
and order of authority.
