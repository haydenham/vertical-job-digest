# Work Log

Append-only record of working sessions — a narrative backup to git history.
Newest entry on top. One entry per working session. Keep it terse: what changed, why, what's next.

---

## 2026-06-11 — Planning kickoff + grid/power seed data

**Decided (see DECISIONS.md for the durable record):**
- Pipeline runtime: **local machine** (cron/launchd) for week 1; documented path to a small VPS later.
- Transactional email: **Resend**.
- Python toolchain: **uv**.
- Seed-data split: Hayden curates company names + priority columns; Claude resolves ATS by probing live endpoints.

**Did:**
- Read all four planning docs (CLAUDE.md + docs/01–03). Confirmed the spec is settled; this phase is build-prep, not re-planning.
- Created `data/seed/` with `employers_seed.csv` + a column/workflow `README.md`.
- Ingested Hayden's 54-company **grid/power** list (from `data1.xlsx`), preserving his curation columns (tier, category, key_cities, role_tilt).
- Resolved ATS by probing live Greenhouse/Lever/Ashby JSON endpoints:
  - **7 verified** (live, jobs > 0): Amperon, Arcadia, Camus Energy, Jane Street, Voltus, Yes Energy, WeaveGrid.
  - **3 suspect** (slug resolved but board looks wrong): Constellation Energy, Koch Industries, Kraken (Octopus).
  - **44 unverified** (Workday/custom best-guesses): utilities, banks, quant funds, exchanges, a few startups.
- Added build-spec docs: `04-data-model-spec.md`, `05-fetcher-interface-spec.md`, `06-vertical-config-spec.md`; started `DECISIONS.md`; appended a documentation-discipline section to CLAUDE.md.
- Prepped repo for GitHub: `git init` (branch `main`) at the project root (`vertical-job-agent-starter/`), added `.gitignore` (Python/uv/env/db/OS) and a root `README.md`. Not committed — Hayden does add/commit/push.
- Reasoned through the custom/Workday scraper question: conclusion is *don't write N per-company scrapers* — bucket the 47 into Workday (one generic fetcher + per-tenant config), other known ATSs (a few generic fetchers), and a small truly-bespoke tail (default to Layer 2 LLM-read). Next step proposed: an ATS-identification pass to get the real distribution.

**Open threads / next:**
- Aviation vertical not yet seeded.
- The 44 unverified + 3 suspect rows need ATS confirmation (web research or just let the Layer 1 fetcher 404-test the guesses).
- Net code written so far: none. Next build step = Layer 1 skeleton (repo scaffold with uv, employers table, Greenhouse/Lever/Ashby fetchers, postings table, diff job, bare email).
