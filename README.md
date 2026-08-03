# Vertical Job Intelligence Agent — Rolefeed

A scheduled pipeline that achieves **total coverage of a small, bounded employer universe**
(~40 companies per vertical), diffs postings every four hours, and delivers a daily digest of
new/closed roles with an LLM-written, reasoned match against the user's résumé.

Not a live chat agent. Not a horizontal job board. **The diff is the product.**

> ## Status: **live in production** at **[role-feed.com](https://role-feed.com)** — public beta.
>
> Shipped 2026-07-28. Real users are signed up, receiving digests, and reading the dashboard.
> Four verticals are configured, **167 employers curated / 115 on a supported ATS fetcher**, and the
> pipeline runs every four hours against Postgres on Neon behind Cloud Run. Anyone can browse the
> live job universe without an account at **[role-feed.com/demo](https://role-feed.com/demo)**.
>
> Current release: **[Update 1.1](docs/updates/1.1.md)** — the funnel update.
> The codebase is `vja`; the user-facing brand is **Rolefeed**.

## What a user gets

1. **Sign in with Google, upload a résumé, pick a vertical.** Matching starts immediately against the
   whole open universe (the signup backfill), typically finishing in 6-25 minutes.
2. **A daily email digest** of what changed — new roles with a written match rationale (what fits,
   what does not, a verdict and a score), plus closures rolled up by company. Empty digest, no email.
3. **A read-only dashboard** over the same precomputed data: *Matched for you* (the AI's recommended
   subset) or *All in-scope* (the objective, résumé-independent job list), across recency windows of
   new today / 1 week / 2 weeks / all open. Salary shows only when the posting's own text corroborates
   it; the detail panel carries the full posting body and the apply link.
4. **Self-serve control** — switch vertical, pause the digest, unsubscribe in one click from any email,
   or delete the account outright (one transaction, everything user-owned goes).

Nothing is fetched live at read time. Every surface is a window onto what the pipeline already computed.

## How it works (three layers, cheap deterministic path first)

1. **Layer 1 — ATS spine.** Deterministic fetchers against public ATS endpoints. **Fourteen platforms
   supported**: Greenhouse, Lever, Ashby, Workday, iCIMS, Workable, SmartRecruiters, Oracle HCM,
   Radancy, Paylocity, Phenom, BambooHR, Pinpoint, Rippling. No per-company scrapers — an employer
   either routes to a generic platform fetcher or it is Layer 2.
2. **Layer 2 — LLM extraction & matching.** Runs only on what the Layer-1 diff flags as new or changed,
   and only after two free deterministic gates (a title scope gate, then a level/location/work-auth
   prefilter). Extraction is cached by `content_hash`; matching is idempotent per
   `(posting, profile, resume_version)`.
3. **Layer 3 — agentic discovery (manual/on demand).** `vja-discover` finds new *employers*, not
   postings — capital portfolios, industry lists, market adjacency — validates each by actually
   fetching it, and writes `proposed` rows into a review queue. A human promotes them with `vja-review`.

A **vertical is configuration, not code**: an employer list + niche sources + a matching profile.
Adding one costs curation and a YAML file. This has now been proven three times (aviation, robotics,
trading) — the trading vertical needed **zero** `src/` changes.

## Verticals

| Vertical | Employers | On a supported fetcher | Shape |
|---|---:|---:|---|
| **Grid / power software** | 56 | 38 | ISOs/RTOs, utilities/IPPs, grid software, storage/DER, power trading and analytics |
| **Trading software** | 44 | 36 | Market makers, quant funds, exchanges and market infrastructure, crypto, prediction markets |
| **Aviation software** | 37 | 17 | Airline ops/tech arms, platforms, flight-data companies, startups |
| **Robotics software** | 30 | 24 | Humanoid/embodied AI, warehouse/logistics, industrial, field/agriculture, medical |

Deliberately **not** broad "climate tech" or a generic tech board. A user holds one vertical at a time
and can switch it themselves.

## Stack

Python 3 · `uv` toolchain · FastAPI (read API + serves the SPA same-origin) · SQLAlchemy Core + Alembic ·
**Postgres on Neon** (SQLite for local dev, CI verifies both dialects) · **Vite + React + TypeScript**
SPA · embedded **LiteLLM** behind the typed `vja.llm` boundary (extraction `anthropic/claude-haiku-4-5`,
matching `openai/gpt-5.6-luna` at low effort) · direct OpenAI SDK for discovery · **Resend** for email ·
**Google Cloud Run** (one service + two Jobs) with **Cloud Scheduler** triggers and Cloud Monitoring
alert pairs · Cloudflare in front · GitHub Actions CI/CD with keyless Workload Identity Federation.

## Production shape

One multi-stage image, two run targets, two schedules:

| Thing | What it is | Cadence |
|---|---|---|
| `vja-api` | Cloud Run **service** — read API + the built SPA, CPU always allocated | always on |
| `vja-nightly --no-digest` | Cloud Run **Job** — fetch → diff → extract → match | every 4h, `0 1,5,9,13,17,21` CT |
| `vja-digest` | Cloud Run **Job** — assemble → verify links → render → send | daily, `0 6` CT |

Both Jobs run with **zero retries** and cadence-sized task timeouts. Each has its own *execution failed*
and *did not run* alert policy. A pipeline run that finds another still `running` skips rather than
racing it. `main` auto-deploys after every gate goes green, with smoke + auto-rollback; **migrations
stay manual** by design.

## Repository layout

```
CLAUDE.md                     # working spec for the AI agent + doc map / order of authority
README.md                     # you are here
DECISIONS.md                  # decision log (ADRs, D-001…)
WORKLOG.md                    # append-only session log, newest on top
docs/
  INVARIANTS.md               # READ FIRST — the cross-cutting rules that are true right now
  01-03                       # planning memos (business, technical, open questions)
  04-data-model-spec.md       # concrete schema (diff keys on external_id)
  05-fetcher-interface-spec.md# common Fetcher contract + per-ATS modules
  06-vertical-config-spec.md  # "a vertical is config"
  07-ats-routing.md           # ATS distribution + fetcher build priority
  08 / 09                     # testing strategy · dev workflow + Definition of Done
  11 – 20                     # hosting, deploy, onboarding, UI, LLM cost, feature roadmap
  updates/                    # per-release update docs (1.1 = the funnel update)
src/vja/                      # the package: fetchers/ db/ api/ digest/ + pipeline, extract, match…
frontend/                     # the Vite/React/TS SPA
config/verticals/             # one YAML per vertical + matching profiles
data/seed/employers_seed.csv  # the curated employer universe (+ README: columns, verification)
deploy/gcp/                   # ship.sh (break-glass deploy), alerts.sh, cutover runbook
migrations/                   # Alembic
tests/                        # unit / integration / system (+ opt-in live, e2e, eval markers)
```

## Running it locally

```sh
uv sync
uv run alembic upgrade head          # local SQLite at data/vja.db
uv run vja-import-employers          # load the curated seed
uv run vja-run                       # fetch → diff → persist
uv run vja-extract && uv run vja-match
uv run vja-api                       # serve the API + built SPA
```

The whole loop is one command — `vja-nightly` composes fetch/diff/persist → extract → match → build
and send the digest, and emails an alert if it hard-fails:

```sh
uv run vja-nightly                   # the full loop
uv run vja-nightly --no-digest       # what production runs every 4h
uv run vja-digest                    # what production runs each morning
```

Frontend:

```sh
cd frontend && npm install && npm run dev    # Vite dev server on :5173, CORS to the API
```

Config comes from the environment (a git-ignored local `.env`, loaded automatically by the application
CLIs — never commit secrets; see `.env.example`):

| var | purpose |
|---|---|
| `VJA_DATABASE_URL` | DB URL; defaults to local SQLite `sqlite:///data/vja.db` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Layer-2 model calls (extraction / matching) |
| `VJA_EXTRACT_MODEL` / `VJA_MATCH_MODEL` | model routes; provider-neutral through LiteLLM |
| `RESEND_API_KEY` | Resend API key (required to send) |
| `VJA_DIGEST_FROM` | sender; defaults to the Resend sandbox `onboarding@resend.dev` |
| `VJA_DIGEST_RECIPIENT` | **ops/alert** recipient — *not* the digest recipient, which is the matched profile's own email |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth; login routes are inert (503) until both are set |
| `VJA_SESSION_SECRET` | signs the session cookie and the unsubscribe tokens |
| `VJA_AUTH_REQUIRED` | hard-gates the read API. **On in production**, off for local dev |

Application commands load `.env`; **Alembic intentionally does not.** For migrations, export
`VJA_DATABASE_URL` explicitly (production sequence: `deploy/gcp/README.md`) or a bare
`uv run alembic upgrade head` will target the default local SQLite database.

An empty digest (nothing new or closed) sends no email by design.

## Gates

```sh
uv run pytest                        # unit + integration + system — fast, offline, free
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run lint-imports                  # the layering rule is machine-enforced
cd frontend && npm run lint && npx tsc -b --noEmit && npm test    # eslint + tsc + vitest
```

`live` / `e2e` / `eval` are opt-in markers; the default suite never touches a real ATS or a paid model.
Pre-commit and CI run the same checks. **Definition of Done:** green tests + lint/format/types +
import-linter + a human-read diff + updated docs, before merge.

## Documentation discipline

This project documents as it builds, and the discipline is not optional.

- **`docs/INVARIANTS.md` is read first** — the derived, always-current registry of cross-cutting rules,
  each pointing at its backing ADR. The fastest way to avoid acting on a stale rule.
- Every session updates **`WORKLOG.md`**; every re-litigable decision lands in **`DECISIONS.md`** as an
  ADR (supersede, never delete); every group of shipped work gets an entry in **`docs/updates/`**.
- When an ADR changes a live rule, `INVARIANTS.md` is edited *in the same session* — replaced, not
  appended.
- Order of authority when docs disagree: build specs (`docs/04+`) > `CLAUDE.md` > planning memos.

See `CLAUDE.md` for the full doc map.

## Kill criterion

If the builder stops reading his own digest by week three, the product hypothesis is falsified. The
project still wins as a portfolio piece and an interview story.
