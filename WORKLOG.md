# Work Log

Append-only record of working sessions — a narrative backup to git history.
Newest entry on top. One entry per working session. Keep it terse: what changed, why, what's next.

---

## 2026-06-15 — Chunk 1b: CI workflow + pre-commit (gates machine-enforced)

**Did:** Made the D-021 gate suite enforceable, not just locally runnable. Bundled with Chunk 1 as one
"project setup" change (CI has nothing to gate until the scaffold exists).
- `.github/workflows/ci.yml`: two jobs on `pull_request` + push-to-`main` — `gates` (`uv lock --check` →
  `uv sync --locked` → ruff format/check → mypy → pytest) and `secrets` (gitleaks, full-history). Pinned actions
  (`checkout@v4`, `astral-sh/setup-uv@v5` w/ cache, `gitleaks-action@v2`); `concurrency` cancels superseded runs.
- `.pre-commit-config.yaml`: local-repo hooks that shell out to `uv run` (single source of truth for tool versions)
  — ruff format, ruff check, mypy, pytest. Mirrors CI (`docs/09` "same checks, two moments").
- Added `pre-commit` to the dev group; re-locked.

**Deferred on purpose:** the path-filtered `eval` gate (D-020/D-021) — no prompt/matching code exists to evaluate
yet; it lands with the Week-3 matching engine, the change it actually guards.

**Gates:** `uv lock --check`, ruff format/check, mypy (strict), pytest all green; `pre-commit run --all-files`
passes all four hooks; both YAML files parse. CI's own proof is the first PR running green on GitHub.

**Next:** push this branch → open the "project setup" PR (scaffold + CI) → confirm CI green. Then resume
branch-per-chunk with **Chunk 2** (domain models + Fetcher contract) on a fresh `feat/domain-models`.

---

## 2026-06-15 — Chunk 1: uv scaffold + tooling (first code)

**Did:** Stood up the Python project. Code starts here.
- Installed `uv` (0.11.21) via the standalone installer — Homebrew couldn't resolve `formulae.brew.sh` in this env; the standalone installer worked. uv lives at `~/.local/bin` (D-014).
- `pyproject.toml`: package `vja` (src layout, hatchling build), runtime dep `httpx`; dev group `pytest`/`ruff`/`mypy`/`respx`/`freezegun`. Ruff (E,F,I,UP,B,SIM, line-length 100), `mypy --strict`, pytest config with the opt-in markers `live`/`e2e`/`eval` excluded from the default run (D-020/`docs/08`).
- `src/vja/__init__.py` (carries the D-004 "no vertical-specific code" rule as a module docstring), `tests/unit/test_scaffold.py` smoke test, `uv.lock` committed.

**Gates:** `ruff format --check`, `ruff check`, `mypy` (strict), `pytest` all green off a clean tree.

**Decisions:** none re-litigable; import package named `vja` (Hayden-approved). No DECISIONS entry needed.

**Next:** Chunk 2 — freeze the domain models + Fetcher contract (`models.py`: `RawPosting`/`Employer`/enums per `docs/05`; `fetchers/base.py`: `Fetcher` Protocol + `FetchError`), with a `RawPosting` immutability unit test. Pause for diff review before Chunk 3.

---

## 2026-06-11 (end of day) — corrected vertical order + logged two-stage filter

**Did:** Two small but real corrections before code starts.
- **Energy is the first-built vertical, not aviation (D-022).** The repo was quietly contradicting itself — CLAUDE.md's
  build sequence said "weeks 1–2 aviation / week-4 energy" while the seed data is grid/power and `docs/06` already
  treated *aviation* as the week-4 add. Hayden confirmed energy-first. Fixed CLAUDE.md (build sequence + verticals
  intro), the stray "week-4 energy" references in `docs/08`/`docs/09`, and the D-002 why-line.
- **Logged the two-stage cheap filter (D-023).** Hayden flagged that the LLM resume-match should sit on top of a
  cheaper, free filtering layer. Captured the shape: **Stage A** = free scope/relevance gate on the L1 title
  (in-scope role/geo/level at all) *before any LLM extraction*; **Stage B** = the existing cheap level/location/
  work-auth pre-filter → `matches.score`; only Stage-B survivors reach the strong rationale model. The concept was
  already implied (CLAUDE.md pre-filter, `04.score`, `08` unit test) but the *free title-level Stage A* wasn't
  specified. Full mechanics deferred to the week-3 matching spec. Updated CLAUDE.md execution model to match.

**Readiness check:** confirmed nothing blocks code. The Greenhouse fetcher's inputs are fully specced (`05` contract +
endpoint, `04` schema + diff lifecycle, D-019 fixtures). Open: aviation seed (week-4), and the eval/matching specs
(week-3) — neither blocks week-1.

**Next session:** start building. Scaffold the uv project → freeze `Fetcher`/`RawPosting` from `docs/05` → capture one
real Greenhouse response into `tests/fixtures/` → write the mapping + its unit test. First fetch runs over the verified
**grid/power** Greenhouse slugs (`amperon`, `camusenergy`, `janestreet`, `yesenergy`).

---

## 2026-06-11 (later still) — testing strategy + dev workflow docs

**Context:** Hayden verified most seed links (a few problematic ones to filter later) and flagged that since
~all code here is Claude-written, testing must be rigorous. Asked for testing docs (unit→integration→system→e2e),
a when-to-use protocol, and any other standard dev protocols worth adopting.

**Wrote:**
- `docs/08-testing-strategy.md` — the four levels in this project's own terms (fetcher mapping + `content_hash`
  + diff arithmetic as units; fetch→diff→persist, the **no-mass-close-on-failure** guard, extraction-cache reuse,
  `matches` versioning as integration; whole-pipeline run + idempotency + verification gate as system; live ATS
  smoke + full real send as opt-in e2e). Plus a dedicated **LLM-as-evals** section (mock the SDK in L1–3; pin model
  behavior with property assertions + an "obvious no" case, graded with tolerance, metered) and a when-to-write
  table. Builds on D-019, doesn't contradict it.
- `docs/09-dev-workflow.md` — Definition of Done, branch/small-PR flow, the human-read-the-diff review gate,
  CI+pre-commit gates (ruff/mypy/pytest/secret-scan/uv-lock), config-not-code as a checkable rule, and an explicit
  "what we deliberately skip for now" list.

**Decisions:** D-020 (four-level taxonomy; fast/offline default suite; regression-test-first; LLM evals as a
**path-filtered merge gate** — structural props block hard, behavioral "obvious-no" cases gate on a threshold, and
the whole eval job only runs in CI when a PR touches prompt/matching/extraction code), D-021 (DoD + automated gates +
mandatory human diff review; **mypy** chosen over pyright). Updated CLAUDE.md doc map + a testing/DoD policy bullet.

**Hayden's calls this session:** fine with evals as a real merge gate (token cost ≈ one normal query, worth it to
catch a prompt regression before it ships in a digest); picked mypy. Design answer to the flake worry = path-filter
the gate + threshold/majority on behavioral cases, not weaken it.

**Next:** unchanged from prior session — scaffold the uv project and freeze the `Fetcher` interface; first real tests
land with the GH/Lever/Ashby fetchers (unit mapping tests against captured fixtures = the first thing built under D-020).

---

## 2026-06-11 (later) — ATS-identification pass

**Did:** Classified all 54 grid/power employers by ATS platform (live endpoint probes → careers-page signature
detection → web-search reading ATS domains from result URLs → live endpoint verification incl. the Workday `cxs` API).

**Result — 22 verified / 16 detected / 16 layer2:**
- **Workday is dominant (15).** The generic `cxs` POST API is **live-verified** for 12 (AES 111, Vistra 193, S&P 234,
  Shell 174, Duke 96, Xcel 123, CME 69, Trafigura 97, Wood Mac 68, Macquarie 25, PJM 13, Stem 12). One generic fetcher.
- **Greenhouse 5** (incl. DRW slug `drweng`=147), **Lever 3** (Kraken/Octopus slug `octoenergy`=162, corrects earlier suspect),
  **Ashby 1** — all verified.
- **Tier B:** iCIMS 4, Workable 2 (Energy Aspects API valid), Oracle HCM 2, SmartRecruiters 1.
- **Tier C singletons:** Jobvite, SuccessFactors, Avature, UKG, Eightfold (1 each).
- **Layer 2 (16):** 3 Radancy/Phenom enterprise portals + 13 custom sites.
- **Deterministic ceiling ≈ 70%** via ~8 platform fetchers; ~30% → Layer 2. Vindicates "no per-company scrapers."

**Wrote:** `docs/07-ats-routing.md` (distribution + build priority); rewrote `employers_seed.csv` with full
classification (Workday endpoints encoded as `tenant:dc:site` + full cxs URL); updated seed README, CLAUDE.md doc map,
and DECISIONS (D-017 no-custom-scrapers, D-018 build order, D-019 fixture-based tests).

**Open fixups:** GE Vernova / BP Workday site-path; Castleton tenant prefix; Vortexa Workable slug; double-check
Fluence/Enverus/Aurora before defaulting them to Layer 2.

**Next:** scaffold uv project, freeze the `Fetcher` interface, build GH/Lever/Ashby with captured fixtures.

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
