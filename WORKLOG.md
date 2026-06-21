# Work Log

Append-only record of working sessions — a narrative backup to git history.
Newest entry on top. One entry per working session. Keep it terse: what changed, why, what's next.

---

## 2026-06-21 — Phase 6 · Block A2: recency-window query + index + signup backfill (D-039)

**Did:** Consumed A1's `source_updated_at` to build the dashboard's recency prerequisite + the D-024
signup backfill — the two consumers D-030 said would share one date predicate.
- `db/postings.py`: `activity_window_clause(cutoff)` (the one home for
  `COALESCE(source_updated_at, first_seen_at) >= cutoff`), `OpenPosting` dataclass (match-free
  dashboard row), and `open_postings_in_window(vertical, *, cutoff, by_first_seen)` — open postings
  in a window, newest-activity-first, no match join. `cutoff=None` → all open; `by_first_seen=True`
  → the "new today" basis (first_seen only = calendar midnight UTC, so it equals the digest); else
  the activity predicate (week/2-week toggles + backfill).
- `db/matches.py`: `postings_needing_match` gains a keyword-only `since=` that ANDs in
  `activity_window_clause` (default `None` = nightly, byte-identical). This is what bounds backfill.
- `db/schema.py` + migration `f7164d547f15`: `ix_postings_status_source_updated` on
  `(status, source_updated_at)`. Applied + round-tripped on local `vja.db`.
- `match.py`: extracted `run_matching`'s per-profile loop into shared `_match_profile`
  (`since`/`trigger` params); added `run_backfill(vertical, profile)` (5-day cap,
  `trigger=backfill`, idempotent) + `vja-backfill --vertical V [--email X]` CLI (registered in
  pyproject). Nightly matching behavior unchanged.

**Decisions:** D-039. Per Hayden's sign-off: (1) **match-free shared primitive** (dashboard layers
verdict/score in B1, keeping the docs/11 `(vertical, profile_id)` seam in the API layer; backfill
reuses the bare window); (2) **flexible cutoff, not a rigid 4-toggle enum** (backfill's 5d isn't a
toggle value); (3) **backfill = 5 days, not 14** — **amends D-024** and decouples it from the
dashboard's 14d "Two weeks" toggle (they share only the predicate now); (4) **nightly stays
uncapped** — the digest's `first_seen_at` window already keeps old backlog out of the inbox, so the
cap is the backfill's job alone; (5) **"new today" = calendar midnight UTC**.

**Tests:** +9 (202→211). `test_postings_window.py` (activity basis + fallback, new-today first_seen
basis, all-open, newest-first order, vertical scoping, open-only, dashboard columns).
`test_backfill.py` (5d-window matching, `trigger=backfill`, idempotency, + a direct
`postings_needing_match(since=)` repo test). `test_matching_run.py` unchanged + green (pins the
`_match_profile` refactor preserved nightly behavior).

**Verified:** ruff + format + mypy(strict) clean; **211 passed, 8 deselected**; `alembic check`
clean + `downgrade -1`/`upgrade head` round-trip. Smoke on local `vja.db`: window sizes monotonic
(all_open 2175 → last_1d 4 → new_today 4); `vja-backfill --help` wired.

**Next:** Phase 6 **B1** — FastAPI read API (`(vertical, profile_id)`-parameterized per docs/11),
mapping the recency toggles → `open_postings_in_window` cutoffs + LEFT-joining match quality; then
**B2** — the Vite/React/TS table served by FastAPI.

---

## 2026-06-21 — Phase 6 · Block A1: ATS date normalizer + `postings.source_updated_at`

**Did:** Built the deferred D-030/D-024 date infra — one normalized, queryable ATS activity date, the
dashboard recency toggles' (A2/B) backend prerequisite.
- `src/vja/dates.py` (new): `normalize_ats_date(str|None) → datetime|None`. ISO 8601 (offset/`Z`/naive→UTC/
  date-only) + epoch sec/millis digit-strings (Lever) → tz-aware UTC; unparseable → `None`, never raises.
  Resolves the parked DRW malformed-`posted_at` row (it now normalizes to `None`).
- `db/schema.py` + migration `13c2203d963b`: new nullable `postings.source_updated_at` (`UTCDateTime`).
  Hand-fixed the autogen to render the custom type as `sa.DateTime(timezone=True)` (matches the initial
  migration; the autogen emitted an un-imported `vja.db.schema.UTCDateTime` ref). Applied to local `vja.db`.
- `db/postings.py`: `insert_posting`/`bump_last_seen`/`update_changed` take a keyword-only
  `source_updated_at` (bump/update write it only when non-None — never null a good value);
  `save_extraction` fills it via `CASE WHEN source_updated_at IS NULL` (L1-authoritative).
- `pipeline.py`: normalizes `posting.updated_at` and passes it to all three L1 write paths (so the unchanged
  `bump` path refreshes it too — self-heals the existing GH/Lever/Ashby corpus next run).
- `extract.py`: passes `normalize_ats_date(fields.posted_at)` to `save_extraction` (fills Workday's date).

**Decisions:** D-038. Per Hayden's sign-off: (1) **L1 `updated_at` authoritative, L2 `posted_at` fills only
when NULL** (vs literal "most recent" — better data quality, dialect-portable); (2) **refresh on every
sighting** incl. the unchanged path, guarded non-NULL, which also self-heals the corpus. Accepted limitation:
existing Workday rows (already extracted, no L1 date) stay NULL → dashboard falls back to `first_seen_at`
(the documented Workday weak spot).

**Bug found + fixed (probe before sign-off):** a bare digit string like `"2026"` (a plausible LLM
`posted_at`) was parsed as epoch-seconds → **1970** — a garbage date is worse than NULL (NULL falls back to
`first_seen_at`; 1970 reads as ancient and drops out of every recency window). Fixed with a posting-era
sanity guard in `_from_epoch` (reject if the resolved year ∉ [2000, 2100]) + a regression test.

**Tests:** +26 (176→202). `test_dates.py` (ISO offset/`Z`/naive/date-only, Lever ms + epoch sec, empty,
malformed/DRW regression, **implausible-epoch guard**, surrounding whitespace). `test_pipeline.py` (insert
persists normalized date; no-date→NULL; bump self-heal/backfill; content-change refresh; later-null never
clobbers). `test_extraction_run.py` (extraction fills only when NULL; never overrides an L1 date).

**Verified:** ruff + format + mypy(strict) clean; **202 passed, 8 deselected**; `alembic check` clean.

**Next:** A2 — `open_postings_in_window` query helper (D-030 criterion: `source_updated_at` in-window OR
`first_seen_at` fallback; *new today* = `first_seen_at`) + its `(status, source_updated_at)` index, then the
onboarding backfill (D-024, `trigger=backfill`, ≤14d cap). Then Phase 6 B1 (FastAPI read API) / B2 (React).

---

## 2026-06-20 — Phase 6 prep · multi-user & hosting migration ledger (doc-only)

**Did:** Added `docs/11-multi-user-and-hosting.md` — a *living checklist* (not a design doc) for the
eventual D-025 hosting/Postgres + multi-user cutover. Three working sections: (1) **already portable** (DB
D-025, runtime D-031, cost model D-005, matching D-006, identity/resume seams D-027/D-033 — linked so they
aren't re-derived under cutover pressure); (2) **seams to preserve** — chiefly the rule that the **Phase-6
dashboard API is `(vertical, profile_id)`-parameterized**, so adding auth later is a filter, not a rewrite;
(3) **deferred work enumerated** — security/PII (flagged highest-stakes), auth/identity, cost/abuse guards
(signup backfill is the first place user action drives LLM spend), email deliverability, live
migrations/observability. Added it to the CLAUDE.md doc map.

**Why:** Hayden flagged that lots of design is deferred to an approaching cloud migration with no written
plan. Turning "a lot goes into it" into an enumerated, trackable ledger is cheap and prevents single-user
assumptions from hardening silently — discipline is *document the seams now, build the machinery at the
trigger*; kept honest with the kill criterion (no speculative scaffolding).

**Decisions:** none new (no ADR — this is a ledger over existing decisions). Adopted-but-unrecorded
convention surfaced for Phase 6: the read API is `(vertical, profile_id)`-parameterized (will land with B1).

**Tests:** none (doc-only).

**Next:** in-depth plan of **A1** (normalize → persist the ATS activity date: `postings.source_updated_at`
+ migration + per-ATS normalizer; closes the parked DRW malformed-`posted_at` fix), then code.

---

## 2026-06-19 — Phase 5 · Block 4: digest rationale + nightly extract→match→send + recipient→profiles

**Did:** Composed the Layer-2 pieces (5.1–5.3) into the nightly loop and put the match rationale in the
inbox — Phase 5 is now end-to-end. Three wiring seams (D-037):
- `digest/assembly.py`: `build_digest` is now per **(vertical, profile)** — INNER-JOINs `matches` on
  (posting, profile, resume_version) gated to verdict ∈ {strong_yes, yes, maybe}, ordered by `score`
  desc. `DigestPosting` gains verdict/score/rationale/fits/gaps; `DigestContents` gains `recipient`.
  `last_sent_at` now keys on (vertical, **recipient**) so each profile's window is independent.
- `digest/render.py`: new-role lines render `[verdict · score]` + the one-line `rationale` (text + HTML);
  `fits`/`gaps` go into the `contents` audit JSON but **not** the body (D-037 scannability).
- `digest/send.py`: `send_digest(engine, vertical, profile, …)` → recipient = `profile.user_email`;
  `send_main` loops verticals → `active_profiles`. `send_email` takes an explicit recipient (alert path
  still uses `config.recipient`). `DigestConfig.recipient` redocumented as the **ops/alert** address.
- `nightly.py`: `run_nightly` = pipeline → per config-vertical `run_extraction`+`run_matching`
  (`_default_layer2`, injectable as `run_layer2` for offline tests; one Anthropic client shared) →
  `send_digest` per active profile. Per-vertical isolation around the Layer-2 pass; LLM totals written to
  the run row via `update_llm_metrics`; `NightlyResult` + the printed summary carry extracted/matched/cost.
- `db/pipeline_runs.py`: `update_llm_metrics` (the columns `finish_run` had stubbed at 0).

**Decisions:** D-037. Resolved with Hayden: (1) digest hides `no` + unmatched, sorts by score; (2) body
carries verdict+score+one-liner (fits/gaps audit-only); (3) **three wiring items only** — `posted_at`
normalization (D-030) + new-user backfill (D-024) stay deferred to the backfill block (docs peg that work
to Phase 5 *because backfill needs it*; the nightly digest is a diff and reads no `posted_at`). DRW
malformed-date fix stays parked there too.

**Tests:** +5 net (172→176) — `test_digest_render.py` (verdict/score/rationale in body; fits/gaps
audit-only; closures carry no match fields), `test_digest_assembly.py` (match-gating drops `no`/unmatched;
score-desc order; per-recipient `last_sent_at`; window/closures), `test_digest_send.py` (recipient =
profile email; per-profile rows), `test_nightly.py` (composition via injected `run_layer2`; rationale in
the delivered body; LLM totals on the run row), `test_nightly_alert.py`/`test_digest_send_e2e.py` updated
for the new signatures.

**Verified:** ruff + format + mypy(strict) clean; **176 passed, 8 deselected**; `alembic check` clean
(no DDL); eval still collects (2 match evals). Live `vja-nightly` smoke pending (Hayden).

**Next:** Phase 6 — dashboard (read-only FastAPI + React table with recency toggles, D-030). Still open:
record the deferred onboarding-backfill decision + build it (with the D-030 `posted_at` normalize→persist,
which the backfill needs first) and the parked DRW date fix; consider the Batches API for the backfill burst.

---

## 2026-06-19 — Phase 5 · Block 3: Stage-B pre-filter + LLM matching (Sonnet, fits/gaps/verdict)

**Did:** Closed the two-stage filter (D-023) and wrote the first `matches` rows — the product's
actual output, a resume-match rationale per posting.
- `src/vja/prefilter.py`: `passes_prefilter(level, location, cfg)` — Stage B, pure/deterministic,
  no LLM. Drops only *confirmed* out-of-range postings (concrete `mid`/`senior` level, clearly
  non-US location); `unknown`/null/`remote` pass (coarse gate, the LLM refines — same philosophy as
  Stage A). Geo = US-signal allowlist (postal codes + full state names + `United States`/`USA`/
  `America`/`remote`), whole-word + case-insensitive. `work_auth` is **not** gated (no config
  values, candidate auth not encoded) — passed to the matcher as a signal.
- `src/vja/match.py`: `MatchResult` (pydantic: verdict/score/fits/gaps/rationale) →
  `client.messages.parse(model="claude-sonnet-4-6", thinking=adaptive)`; `match_posting`
  (returns rationale + cache-aware metered cost), `run_matching` (per active profile: Stage A
  `in_scope` on title ∧ Stage B over extracted fields ∧ not-yet-matched → strong model → persist;
  per-posting isolation, cost summed), `vja-match` CLI. **Resume + instructions are the cached
  prefix** (`cache_control` ephemeral); only the per-posting structured fields are volatile.
- `src/vja/db/matches.py`: `postings_needing_match` (open ∧ extracted ∧ no `matches` row for
  (posting, profile, resume_version) — idempotency) + `save_match`. No DDL — `matches` pre-existed.
- Added `vja-match` script; `load_dotenv()` in `match_main` before the client (the 5.2 lesson).

**Decisions:** D-036 (Stage-B prefilter + Sonnet matching, fits/gaps/verdict/score, prompt-cached
resume, eval-gated). Resolved with Hayden: **Sonnet not Haiku** — matching is judgment / the
user-visible trust-critical output, extraction is mechanical (D-005 tiering); cost is bounded by
the gates (~$2 one-time backfill + pennies/night), so it's a quality call, not a cost one. Stage-B
+ matching ship as **one block**. Clarifies D-023's "Stage B writes `matches.score`": Stage B is an
**in-memory filter** (no row for non-survivors, since `verdict` is NOT NULL); **`score` is the LLM's
0–100 output**, persisted with the rest of the rationale.

**Tests:** +15 — `test_prefilter.py` (unit: early-career/US passes; senior/mid/non-US drop;
unknown/remote pass; config-driven levels), `test_match.py` (unit, faked client: result→column
mapping, cache-aware cost math, cached-prefix shape, no-parse failure), `test_matching_run.py`
(integration: selects only open+extracted+Stage-A+Stage-B+unmatched; skips out-of-scope/unextracted/
senior/non-US/other-vertical/already-matched; idempotent; per-posting isolation; multi-profile),
opt-in `eval` (`test_match_eval.py`, real Sonnet: structural + obvious-yes + obvious-no — D-020 gate).

**Verified:** ruff + format + mypy(strict) clean; **172 passed, 8 deselected**; `alembic check` clean
(no DDL); eval collects (2 new match evals). Live smoke (Hayden runs `vja-match`) pending.

**Next:** P5.4 — wire the rationale into the digest (verdict/fits/gaps per new posting) and compose
extract + match into `vja-nightly` (D-027 recipient → profiles rides along).

---

## 2026-06-19 — Phase 5 · Block 2: LLM extraction (Haiku), cached by content_hash

**Did:** First LLM code in the system — Layer-2 extraction of structured fields from in-scope postings.
- `src/vja/extract.py`: `ExtractedFields` (pydantic) → `client.messages.parse(model="claude-haiku-4-5")`;
  `extract_posting` (returns fields + metered cost from `usage`), `run_extraction` (selects in-scope
  unextracted, per-posting isolation, persists, sums cost), `vja-extract` CLI. **All-LLM**, **synchronous**.
- `src/vja/db/postings.py`: `postings_needing_extraction` (open ∧ `extracted_at IS NULL`; in-scope filtered
  by the caller), `save_extraction`; **`update_changed` now nulls `extracted_at`** on a content change
  (cache invalidation). Added `ExtractionCandidate`.
- `src/vja/fetchers/workday.py`: `fetch_detail` — pulls a posting's cxs detail (`jobDescription` + real
  `startDate` + structured `country`) so Workday gets full extraction (the lazy Layer-2 fetch D-032 named).
- Added `anthropic` dep; `vja-extract` script; `ANTHROPIC_API_KEY` in `.env.example`.

**Decisions:** D-035 (Haiku cheap tier, all-LLM, sync, cached by content_hash, Workday descriptions via
cxs detail, geo filtering deferred to Stage B). Resolved with Hayden: all-LLM (hybrid saves rounding-error
since the description is sent either way); sync (latency in-process, batch discount not worth polling);
**pull Workday descriptions** after confirming the cxs detail endpoint live — scoped to in-scope + cached
it's ~500 one-time GETs, not the Layer-1 storm.

**Tests:** +12 — `test_extract.py` (unit, faked client: mapping, cost math, Workday-vs-raw source, no-parse
failure), `test_extraction_run.py` (integration: selects only in-scope-unextracted; out-of-scope/
already-extracted/other-vertical skipped; idempotent; content-change re-opens), opt-in `eval`
(`tests/eval/test_extract_eval.py`, real Haiku on a senior/US fixture — the D-020 gate).

**Verified:** ruff + format + mypy(strict) clean; **157 passed, 6 deselected**; `alembic check` clean (no
DDL — Layer-2 columns pre-existed); eval collects.

**Live run:** Hayden added `ANTHROPIC_API_KEY` and ran `vja-extract --vertical grid_power_software`.
First attempt failed 422/422 (`Anthropic()` auth resolves at construction time, and `extract_main` never
called `load_dotenv()` — every other CLI entrypoint does this inside its own `load_config()`/`main()`,
this one was missed). Fixed: `load_dotenv()` added to `extract_main` before `get_engine()`, matching the
`digest/send.py::load_config()` pattern. Re-run: **420/422 extracted, 2 failed, est_cost=$1.65** (in-scope
backlog was 422, not the ~1k originally estimated — Stage-A cuts harder than guessed; cost ran ~3x the
$0.55 estimate, worth re-baselining per-posting cost next time payload sizes are this large). The 2
failures are Layer-1 Workday `cxs` detail-fetch errors (403 on one tenant, 404 — posting likely closed
between list and detail fetch), not extraction bugs; per-posting isolation worked as designed. `pytest -m
eval` (1 passed) and full suite (157 passed) green post-fix.

**Spot-checked** extracted rows: Workday `stack` values (e.g. `Allen-Bradley`, `Triconex`, `RSLogix`)
prove the cxs detail fetch is feeding real description text, not just the list payload; `level` varies
sensibly; comp fields populate correctly when the posting states a range (Greenhouse/Lever ~33-50%, Workday
~12%) and stay null otherwise. **Known minor issue (logged, not fixed):** one row (DRW posting id 6) has a
malformed `posted_at` — Haiku appended a leaked `location` JSON fragment after the date
(`"...T12:24:44-04:00\n\n{\"location\": \"New York City\"}"`). 1/420 (0.24%), cosmetic today since
`posted_at` isn't parsed/joined anywhere yet — defer the fix to the Phase-6 date-normalization work (D-024),
which will need to sanitize/parse this field for the dashboard recency toggles anyway.

**Next:** P5.3 — Stage-B cheap pre-filter (level/location/work-auth + the geo filter) → strong-tier
matching/rationale (fits/gaps/verdict, Option 4) → `matches` rows + the matching eval gate.

---

## 2026-06-18 — Phase 5 · Block 1: profiles + vertical config + Stage-A scope gate (NO LLM)

**Did:** The deterministic foundation for Layer 2 — zero LLM cost, no schema change.
- `config/verticals/grid_power_software.yaml` — the first "a vertical is config" file (D-004):
  matching_profile (user_email + resume path + domain_vocabulary), the new `scope` section (Stage-A
  keyword lists), and `prefilter` knobs (consumed in 5.3). `config/verticals/profiles/hayden_grid_resume.md`
  (Hayden's real resume).
- `src/vja/verticals.py` — `load_vertical_config(key)` → validated `VerticalConfig` (resolves + reads
  the resume); `vja-load-profiles` CLI loads every `config/verticals/*.yaml`. Added `pyyaml` + `types-pyyaml`.
- `src/vja/scope.py` — `in_scope(title, scope)`: balanced whole-word, case-insensitive gate (≥1
  role_include AND no exclude), regex cached by keyword tuple. Pure; computed on-the-fly (no column).
- `src/vja/db/profiles.py` — `upsert_profile` (idempotent; `resume_version = sha256(text)[:12]`,
  new version → new active row, prior deactivated) + `active_profiles`. `docs/06` documents the `scope` section.

**Decisions:** D-034 (Stage-A = config-driven whole-word keyword gate, computed on-the-fly, no migration).
Resolved with Hayden: build the YAML loader (not a minimal bootstrap); balanced include+exclude gate;
on-the-fly (no `in_scope` column); real resume supplied now. Also D-033 (resume input abstracts to
`resume_text`; PDF = a future signup-flow adapter) — landed on a separate `docs/` branch from main.

**Tests:** +20 — `test_scope.py` (balanced/whole-word/none/role-required), `test_vertical_config.py`
(real config loads; missing-file/field/resume + key-mismatch errors), `test_profiles.py` (idempotent
upsert; versioning; vertical isolation).

**Verified:** ruff + format + mypy(strict) clean; **149 passed, 5 deselected**; `alembic check` clean
(no DDL — schema pre-provisioned Layer 2). `vja-load-profiles` created Hayden's active profile.
**Empirical Stage-A check** over the real grid universe: **400 of 1697 open postings in-scope (23%)**,
drops correct (senior/HR/ops) — a 77% cut to Layer-2 cost before any token is spent.

**Next:** P5.2 — LLM extraction (cheap tier, cached by `content_hash`) over Stage-A survivors + cost
metering + extraction evals (first Anthropic SDK code; model IDs via the `claude-api` skill).

---

## 2026-06-18 — Phase 4 · Block 2: onboard the verified Workday tenants (coverage 21 → 24)

**Did:** Config-only block — no new fetcher logic (D-004 again). Hayden pulled the real board URLs; I
live-verified the derived cxs endpoints, then updated the seed:
- **GE Vernova** activated — `Vernova_ExternalSite` (~2381 open, whole-company board).
- **BP** activated — `bpCareers` (~414); its board is slow, so bumped Workday `_TIMEOUT` 20 → 30s (generic).
- **Fluence** reclassified custom → Workday — `fluenceenergy:wd12:fluenceenergy-jobs` (~108); was a bonus 4th find.
- **Castleton** → custom/Layer 2: the `osv-cci.wd1` Workday proxy 422s the cxs API (board renders, no clean JSON).
- **Enverus** → jobvite (powered-by tag; Tier-C, no fetcher yet); **Aurora** unidentified → stays Layer 2.

**Decisions:** D-032 extended with the P4.2 onboarding + the reusable finding that `osv-` Workday hosts don't
expose the cxs API (→ Layer 2). Coverage now **24/54 fetchable** (9 Tier-A + 15 Workday).

**Tests:** updated `test_employers_import` fetchable 21 → 24, Workday 12 → 15. Existing Workday unit/live tests
unchanged (no fetcher-logic change).

**Verified:** ruff + format + mypy(strict) clean; **126 passed, 5 deselected**; `alembic check` clean. Live re-verify
through the real fetcher (GE Vernova 2381 paginated fully, Fluence 109; URLs well-formed). **End-to-end on a throwaway
DB** (kept prod's baseline clean): import → `vja-run` = **24 employers, 0 failures, 4597 postings, 1:47** (BP's slow
board fine under 30s; GE Vernova's 120 pages + completeness guard held). Re-imported seed into **prod** (config only,
no fetch) so the next scheduled nightly picks up the 3 new tenants.

**Heads-up:** that next nightly's `vja-run` will add ~2900 postings (GE Vernova 2381 + BP 414 + Fluence 108) to the
one-time Workday baseline digest; steady state after is small diffs. **Next:** P4.3 — generic pipeline-level
mass-closure guard (defense-in-depth on top of the fetcher's paginate-or-fail).

---

## 2026-06-17 (later still) — Phase 4 · Block 1: generic Workday `cxs` fetcher (coverage 9 → 21)

**Did:** Built the one generic Workday fetcher that lights up the 12 verified Workday tenants — the biggest
single coverage win.
- Probed PJM live first to capture the real cxs response → fixture `tests/fixtures/workday_pjm_jobs.json`,
  and confirmed the public apply-URL form (`{host}/{site}{externalPath}`, no locale segment) resolves.
- `src/vja/fetchers/workday.py` — `WorkdayFetcher`: **POST** the cxs `/jobs` endpoint, **paginate by offset
  until `total` is reached, fail (never return partial) on any page error or short tally** (fetcher-level
  false-closure guard). **List-only** mapping (`description=None`; deferred to a lazy Layer-2 fetch):
  `external_id = externalPath`, `apply_url` built from the cxs host+site+path, `location = locationsText`,
  `updated_at = None` (Workday's `postedOn` is relative text). Registered `AtsType.WORKDAY` in the registry.
- Parked the 3 `detected` tenants (BP, GE Vernova `SITE_TBD`; Castleton prefix) → `status=proposed` in the
  seed until P4.2 verifies their endpoints, so only the 12 verified tenants fetch.

**Decisions:** D-032 (Workday list-only + paginate-or-fail; the 3 detected parked). Confirmed with Hayden:
list-only (defer description cost to where Layer 2 uses it; accept that description-only edits aren't tracked);
park the unverified tenants for a clean nightly run.

**Tests:** +12 — `tests/unit/test_workday.py` (fixture mapping incl. derived apply_url; multi-page pagination
assembles all pages; truncated fetch → `FetchError` not partial; mid-pagination error → raise; empty board → [];
500/non-JSON/missing-`jobPostings`/missing-`total`/missing-`externalPath`/non-cxs-endpoint all → `FetchError`),
registry test extended (WORKDAY resolves; unsupported case moved to iCIMS), `test_employers_import` fetchable
count 9 → 21 (12 Workday). Opt-in `tests/live/test_workday_live.py` (PJM shape).

**Verified:** ruff + format + mypy(strict) clean; **126 passed, 5 deselected**; live Workday smoke passed;
`alembic check` clean (no DDL). **End-to-end:** re-imported seed → `vja-run` = 21 employers, **0 failures,
1131 new postings**, 44s; stored Workday apply URLs well-formed (e.g. Vistra `…/vistra_careers/job/…`).

**Next:** P4.2 — onboard the 3 detected tenants (live-probe BP/GE Vernova/Castleton endpoints + revisit
Fluence/Enverus/Aurora) → coverage 21 → 24; then P4.3 — generic pipeline-level mass-closure guard.

---

## 2026-06-17 (later) — Phase 3 · Block 3: nightly scheduling (launchd) + `vja-nightly` (Phase 3 complete)

**Did:** Made the loop run unattended — the last Phase-3 piece.
- `src/vja/nightly.py`: `run_nightly(engine, *, now, config, resolve_fetcher, verify)` composes
  `run_pipeline(vertical=None)` (all verticals, one pass) then `send_digest` per
  `distinct_active_verticals`, aggregates a status, and on a **hard failure** emails an alert.
  `NightlyResult{status, run, digests, alerted}`. `_send_failure_alert` reuses `send_email` (a
  `SendError` there is logged, not raised — can't alert if Resend is down). `nightly_main` →
  `vja-nightly` console script; logs to stdout/stderr, exits 1 on hard failure.
- **Hard-failure trigger:** pipeline `failed`, or any digest send `failed`. Partial fetch failures
  are logged + in the alert body but don't themselves alert (anti-noise, same logic as D-028).
- `deploy/launchd/`: `com.vja.nightly.plist.template` (StartCalendarInterval 06:00, absolute
  `.venv/bin/vja-nightly`, `WorkingDirectory` = repo root so `.env`/`data/vja.db` resolve, logs →
  `logs/`), idempotent `install.sh`/`uninstall.sh` (sed-substitute `__WORKDIR__`, load/unload), and a
  README (prereqs, baseline-first note, install/verify/uninstall, failure behavior). Added `.env.example`.
- `pyproject.toml`: `vja-nightly` entry point.

**Decisions:** D-031 — launchd over cron (runs a job missed during sleep on wake; cron silently skips);
one-process `vja-nightly`; alert-email-on-hard-failure + logs; 06:00. Recorded the **portability**
principle (scheduler = swappable trigger; portable core = the command + env config + `VJA_DATABASE_URL`;
app logs to stdout/stderr so the trigger routes them; cloud cutover swaps `deploy/<platform>/`, not code).

**Tests:** +7 — `test_nightly.py` (integration: happy→sent+no-alert; failed send→`failed`+alert, 2 Resend
calls; pipeline failure→alert even when digest skips; empty universe→nothing sent) + `test_nightly_alert.py`
(unit: `_failure_summary` content; alert subject carries counts; alert swallows a `SendError`).

**Verified:** ruff + ruff-format + mypy(strict) clean; **115 passed, 4 deselected**; `alembic check` clean
(no DDL). Plist renders to absolute paths; scripts `chmod +x`; `.env.example` is tracked (not git-ignored).

**Phase 3 complete** (assemble → verify → send → schedule). **Next:** Phase 4 — generic Workday `cxs`
fetcher (D-026), ~9→24 of 54 employers. (Operational: run `vja-nightly` by hand once to absorb the 581-role
baseline, then `bash deploy/launchd/install.sh`.)

---

## 2026-06-17 — Phase 3 · Block 2: render + Resend send + `digests` row lifecycle

**Did:** Closed the loop downstream of P3B1's `DigestContents` — the bare digest now actually sends.
- `src/vja/digest/render.py`: `render_digest(contents) -> RenderedEmail{subject, html, text}` +
  `contents_to_dict` (JSON-safe audit blob for the `contents` column). Body shows **new** roles
  (company · title · location · verified apply link) and **closed** roles; **quarantined** postings
  are kept out of the user-facing body but recorded in the audit JSON. Vertical slug is humanized
  generically (`grid_power_software` → "Grid Power Software") — no per-vertical code (CLAUDE rule).
- `src/vja/db/digests.py`: `create_pending` / `mark_sent` / `mark_failed` — mirrors the
  `pipeline_runs` repo (open `Connection`, caller commits per-txn). `pending` row carries full
  contents *before* the send; finalize flips to `sent` (+`sent_at`) or `failed` (+`error`).
- `src/vja/digest/send.py`: `send_email` (one `httpx.post` to Resend, `raise_for_status`, errors →
  `SendError`), `send_digest` orchestrator (build → skip-if-empty → render → pending row → send →
  finalize; `verify`/`config` injectable for offline tests), `load_config` (`.env` via python-dotenv;
  `RESEND_API_KEY`/`resend-api-key`, `VJA_DIGEST_FROM` default sandbox, `VJA_DIGEST_RECIPIENT`), and
  the `vja-digest` console script (`--vertical`, default = all active verticals via new
  `distinct_active_verticals`). Added `python-dotenv` dep.

**Decisions:** D-027 (recipient = env var now → `profiles` at Phase 5), D-028 (empty digest = skip,
no email/row; protects the kill criterion), D-029 (Resend via raw httpx + sandbox sender; pending-row-
before-send lifecycle). Resolved with Hayden: env var bridge (not a new users table — `profiles`
already models a user); sandbox `onboarding@resend.dev`; standalone `vja-digest` (matching slots
between diff and digest at Phase 5, so send stays separate).

**A successful send auto-advances the diff window** — `assembly.last_sent_at` keys the next digest off
`digests.sent_at`, so `mark_sent` needs no extra wiring (pinned by a test).

**Tests:** +18 — `test_digest_render.py` (unit: subject counts, links present, quarantine hidden,
JSON round-trip), `test_digests_repo.py` (lifecycle), `test_digest_send.py` (respx: sent-row+payload,
Resend 4xx & transport-error → failed row, empty → no send/no row, window-advance), and an opt-in
`e2e` real-send (`tests/e2e/`, skipped unless `RESEND_API_KEY`+recipient set — the proof-of-loop test).

**Verified:** ruff + ruff-format + mypy(strict) clean; **108 passed, 4 deselected**; `alembic check`
clean against a fresh migrated DB (no DDL change). Hayden put the Resend key in `.env`. Confirmed end-to-end:
the opt-in `e2e` test sent a real email through Resend.

**Also decided this session (planning, no code):** D-030 — the v1 **dashboard includes recency toggles** (new today /
updated within a week / within two weeks / all open) over the full open set; this is what makes the pull surface worth
opening beside the push digest. Freshness keys on the **ATS posted/updated date** ("posted or updated within the
window"). Surfaced the shared dependency: persisting+normalizing that ATS date is one piece of infra that powers the
Phase-5 backfill cap (D-024), the dashboard toggles (D-030), and apply-speed signals — it rides into Phase 5, toggles
consume it in Phase 6, nothing reorders. Held the 2-week baseline/freshness filter where it is (new users ~2 weeks out).

**Next:** the live proof-of-loop send (needs `VJA_DIGEST_RECIPIENT` = Hayden's Resend account email,
since the sandbox sender only delivers to the account owner), then Phase 4 — the generic Workday
`cxs` fetcher (D-026), the biggest coverage win (~9→24 of 54).

---

## 2026-06-16 — Fix: UTCDateTime type (tz-aware timestamps on every dialect)

**Did:** Replaced the localized `last_sent_at` tz patch (P3B1) with a root-cause fix. Added `UTCDateTime`
(a `TypeDecorator` over `DateTime(timezone=True)`) in `src/vja/db/schema.py` and swapped it onto all 12 timestamp
columns. It normalizes both ends — inbound datetimes → UTC; outbound naive values (SQLite drops tzinfo on read) →
UTC re-attached — so app code never juggles naive-vs-aware datetimes. Removed the now-redundant patch in
`digest/assembly.py`.

**Why:** SQLite returns naive datetimes, Postgres returns aware — same code, different type. Harmless until Python
does datetime math (Phase-5 freshness/age, D-024) or the Postgres cutover, where `naive vs aware` raises/compares
wrong. Fixing at the column type kills the whole class of bug in one place.

**No migration:** underlying DDL is unchanged (`DateTime(timezone=True)`), so `alembic check` reports no drift.

**Tests:** +2 — `test_utc_datetime.py`: a stored timestamp round-trips tz-aware UTC on SQLite; a non-UTC aware input
is normalized to UTC on write.

**Verified:** ruff + mypy(strict) clean; **94 passed, 3 deselected**; `alembic check` clean.

**Next:** Phase 3 · Block 2 — render + Resend send + the `digests` row lifecycle.

---

## 2026-06-16 — Phase 3 · Block 1: digest assembly + verification gate

**Did:** Built the *contents* of the digest + the trust gate in front of it — no sending yet (that's P3B2).
- `src/vja/digest/verification.py`: `verify_apply_url(url, client)` — HEAD (follow redirects) → GET fallback on
  405/501 → pass if final status < 400; any httpx error/timeout = fail (D-008: don't ship a link you can't resolve).
- `src/vja/digest/assembly.py`: `build_digest(engine, vertical, *, now, since, verify) -> DigestContents`
  (`new`/`closed`/`quarantined` lists of `DigestPosting`). Window = `since` last successfully-sent digest
  (`last_sent_at`, normalized to aware UTC); first digest (`since is None`) = baseline (all open → `new`, `closed`
  empty). New postings run the verification gate; dead/missing links → `quarantined`, never shipped. `verify`
  injected (default builds an httpx client) so tests are offline.

**Decisions (this session):** window = since-last-sent-digest (robust to a missed run / failed send); first digest =
baseline of all currently-open. Verification stateless (re-checked each digest; no schema change) — known limitation
logged in the plan (a transient-dead link past the window won't reappear; revisit with a retry flag if it bites).

**Tests:** +12 — `test_verification.py` (respx: HEAD200, HEAD405→GET, redirect, 404, conn-error, 500) and
`test_digest_assembly.py` (baseline; window boundary; auto-resolve `since` from a seeded sent digest; dead-link
quarantine; vertical isolation; `last_sent_at` ignores pending/other-vertical).

**Verified:** ruff + mypy(strict) clean; **92 passed, 3 deselected**. Live e2e: real Camus fetch (3 postings) →
`build_digest` with the **real** verifier → new=3, quarantined=0 (all links resolved live).

**Next:** Phase 3 · Block 2 — render (HTML/text) + Resend send + the `digests` row lifecycle (pending→sent/failed).

---

## 2026-06-16 — Phase 2 · Block 3: orchestration loop + pipeline_runs (Phase 2 complete)

**Did:** Ran `sync_employer` over the whole universe and recorded a run summary — the nightly diff job as one pass.
- `src/vja/db/pipeline_runs.py`: `start_run` (insert `running` + `started_at`) / `finish_run` (finalize status +
  counts + `finished_at`). Written in separate committed transactions so a `running` row is durable before the loop.
- `src/vja/pipeline.py`: `RunSummary` + `run_pipeline(engine, vertical=None, *, now, resolve_fetcher=get_fetcher)`.
  Writes the `running` tombstone → loops `active_fetchable_employers` → per-employer **broad try/except isolation**
  (records `{employer_id,name,error}` in `pipeline_runs.errors`, continues) → finalizes. Status: `ok`/`partial`/
  `failed` (`failed` only if all attempted failed; zero employers = `ok`). `resolve_fetcher` injected for testability.
  Console script **`vja-run`** added (`--vertical`).
- Test fixtures: promoted `migrated_engine`/`alembic_config` to root `tests/conftest.py` (shared by integration +
  the new system tier); fixed the one import.

**Decisions (this session):** running-row-then-finalize (traceable failures — a crash leaves a `running` tombstone);
isolate every employer (one bad employer can't abort the night). Both recorded in the plan; no new D-xxx (they
implement the `docs/04` §7 / `docs/05` health-check / `docs/08` system-tier specs).

**Tests:** +7 — `test_pipeline_runs.py` (running tombstone, finalize) and **system tier** `tests/system/
test_run_pipeline.py` (all-ok; partial on FetchError + run-level no-close guard; partial on *unexpected* exception
isolation; all-failed; idempotent + one run row per run).

**Verified:** ruff + mypy(strict) clean; **80 passed, 3 deselected**. Live e2e: import seed → `vja-run` over the 9
real GH/Lever/Ashby employers → **586 postings persisted, status ok**; re-run → 0 new (idempotent); 2 `pipeline_runs`
rows. The full fetch→diff→persist machine works against real ATS data end-to-end.

**Phase 2 complete.** Next: **Phase 3 — bare digest (proof of loop)**: assemble what changed → verify apply links
(D-008) → email via Resend → schedule. Plan-mode it. (Phase 4 = Workday, per D-026.)

---

## 2026-06-16 — Phase 2 · Block 2: fetch → diff → persist (per-employer) + no-mass-close guard

**Did:** Wired the existing fetchers (Ch 4–5) + `compute_diff` (Ch 6) + `content_hash` (Ch 3) to the DB so one
employer's postings get stored, refreshed, and closed each run. Modular by design: single employer only; the
all-employer loop + `pipeline_runs` summary is Block 3.
- `RawPosting.description` added (last field, default None); each fetcher populates it — Greenhouse `content`,
  Lever `descriptionPlain`→`description`, Ashby `descriptionPlain`→`descriptionHtml` (verified present across all
  fixtures; format may be plain/HTML — fine, the hash compares a posting to its own past).
- `src/vja/fetchers/registry.py`: `get_fetcher(ats_type)` for the 3 Layer-1 ATSs + `SUPPORTED_ATS_TYPES`.
- `src/vja/db/employers.py`: `active_fetchable_employers()` — active GH/Lever/Ashby rows as lean `Employer`s.
- `src/vja/db/postings.py`: repo on a `Connection` — `open_index` (`{external_id: content_hash}`), `insert_posting`,
  `bump_last_seen`, `update_changed`, `close_posting` (never delete — D-009).
- `src/vja/pipeline.py`: `sync_employer(engine, employer, fetcher) -> SyncResult`. Fetch → on `FetchError` return
  `failed` **touching nothing** (THE GUARD) → else `compute_diff` → in one txn: insert new (hash from
  title+location+description), update-or-bump still-present, close vanished.

**Tests:** +11 (registry ×3; Lever description-fallback; `active_fetchable_employers`=9; pipeline ×6 incl. insert/
idempotent/close-not-delete/content-change/hash-includes-description/**the guard: FetchError → 0 closed**). Fetcher
unit tests extended to assert `description`.

**Verified:** ruff+mypy(strict) clean; **73 passed, 3 deselected**. Live e2e: synced real `camusenergy` → 3 postings
persisted with hashes + apply_urls; re-run → 0 new / 3 unchanged (idempotent).

**Docs:** `docs/05` RawPosting contract updated (+`description`). No new DECISIONS (settled-spec implementation).

**Next:** Phase 2 · Block 3 — orchestrate the loop over all active employers (per-employer failure isolation) +
write the `pipeline_runs` run-summary. Plan-mode it.

---

## 2026-06-15 — Phase 2 · Block 1: DB foundation + employer seed import

**Did:** First persistence. Stood up the database so later blocks can store postings + run the diff against state.
Plan-mode decisions this session: **SQLAlchemy Core + Alembic** (D-025), **full 7-table schema now**, **Block 1 =
foundation + employer importer**. Driver: 2 demo users in ~2 weeks → hosting → Postgres soon, so build portable now.
- `src/vja/db/engine.py`: `get_engine` (env URL `VJA_DATABASE_URL`, default local SQLite) + `PRAGMA foreign_keys=ON`
  listener (SQLite ignores FKs otherwise) + `begin()` txn helper.
- `src/vja/db/schema.py`: all 7 `docs/04` tables as Core metadata. Enums = `VARCHAR`+`CHECK` on both dialects
  (`native_enum=False`, keyed to `StrEnum.value`); owned `*_at` = `DateTime(timezone=True)`; `posted_at` stays Text;
  JSON via `sa.JSON`; the spec's uniques/indexes + a posting `CHECK` that exactly one of employer/source is set.
- `src/vja/models.py`: added the remaining schema enums (`Verification` = **verified/detected/layer2**, resolving the
  Chunk-2 drift; `EmployerStatus`/`EmployerSource`/`PostingStatus`/`SourceKind`/`MatchTrigger`/`DigestStatus`/
  `PipelineRunStatus`).
- `migrations/` (Alembic): `env.py` wired to `vja.db` metadata + env URL + SQLite batch mode; autogenerated
  `0001 initial schema`.
- `src/vja/db/employers.py`: idempotent `import_employers_from_csv` (upsert on vertical+name; enum coercion; unknown
  ats_type → UNKNOWN counted; `ImportResult`), `count_employers`, and `main()` → console script `vja-import-employers`.
- `pyproject.toml`: +sqlalchemy/alembic, console script, `migrations/` excluded from ruff+mypy (generated).

**Tests (integration, real SQLite built from the migrations per `docs/08`):** migrations create all 7 tables +
`alembic check` no-drift; FK pragma actually enforced (bad employer_id → IntegrityError); real-seed import (54 rows,
ats distribution matches `docs/07`), known-row spot check, idempotency, verification-enum validity, unknown-ats coercion.

**Verified:** ruff + mypy(strict) clean; **62 passed, 3 deselected**. Manual e2e: `alembic upgrade head` +
`vja-import-employers data/seed/employers_seed.csv` → 54 inserted / 0 unresolved; re-run → 0 inserted / 54 updated.

**Docs:** D-025 (DB stack + Postgres trigger); `docs/04` reconciled (verification enum + SQLAlchemy type notes).

**Next:** Phase 2 · Block 2 — fetch → diff → **persist** postings, with the no-mass-close-on-failure guard as the
headline integration test. Fresh branch.

---

## 2026-06-15 — Chunk 6: diff set arithmetic (last pure-logic piece)

**Did:** Built the daily diff — pure set logic over `external_id`s (`docs/04` lifecycle, D-016/D-009).
- `src/vja/diff.py`: `compute_diff(fetched_ids, stored_open_ids) -> DiffResult(new, still_present, closed)`.
  `new = fetched − stored`, `still_present = fetched ∩ stored`, `closed = stored − fetched`. Accepts any
  iterables (dedups via set semantics); returns `frozenset`s in a frozen `DiffResult`.
- The docstring pins the **no-mass-close guard** as a *caller* responsibility: `compute_diff` can't tell a
  genuinely-empty board from a failed fetch, so the pipeline must skip the diff when a fetch raised `FetchError`.
  (Enforcing that is a Chunk-7+ integration test; here we just compute correctly.)
- `tests/unit/test_diff.py`: 8 units — typical mix, all-new, all-closed (the dangerous empty-fetch case),
  both-empty, no-change, fully-disjoint, iterable/dedup input, and a disjoint-partitions + full-coverage invariant.

**Verified:** default suite **54 passed, 3 deselected**; mypy strict clean; ruff clean (caught a pointless
duplicate set literal `{"b","b"}` → switched to a list to actually test input dedup).

**Milestone:** all pure-logic primitives done (models, content_hash, fetchers ×3, diff). Next chunks introduce I/O
(SQLite) — per the plan, this is where we drop into **plan mode** first to settle DB-access design before coding.

**Next:** Chunk 7 — DB schema + migrations + employer seed-CSV import (the first integration-tested chunk). Will
plan-mode the DB-access approach (raw SQL vs. thin query module vs. SQLAlchemy) before writing. Fresh
`feat/db-schema` branch.

---

## 2026-06-15 — Chunk 5: Lever + Ashby fetchers (Tier-A complete)

**Did:** Added the two remaining clean-JSON fetchers, same pattern as Greenhouse — completing all 9 verified
GH/Lever/Ashby companies.
- `src/vja/fetchers/lever.py`: `LeverFetcher`. Lever returns a bare JSON **array** (no wrapper). Mapping
  (`docs/05`): `external_id = id`, `title = text`, `apply_url = applyUrl or hostedUrl`,
  `location = categories.location`. `createdAt` is epoch-millis (int) → stringified into `updated_at` to keep the
  `RawPosting` type contract. Loud `FetchError` on non-array / no apply link / the usual transport+parse paths.
- `src/vja/fetchers/ashby.py`: `AshbyFetcher`. Returns `{"jobs":[…]}`. Mapping: `external_id = id`,
  `title = title`, `apply_url = applyUrl or jobUrl`, `location = location` (non-string → None),
  `updated_at = publishedAt`.
- Both reuse `build_endpoint` (added in Chunk 4) — no new endpoint code.
- Fixtures: real captures trimmed to 3 jobs each — `tests/fixtures/lever.json` (`voltus`),
  `tests/fixtures/ashby.json` (`weave-grid`) (D-019).
- Tests: 7 Lever + 7 Ashby units via respx (mapping, apply-URL fallback, missing-location → None, empty board,
  shape-mismatch + transport + no-apply-link FetchError paths); 2 opt-in `-m live` smokes.

**Verified:** default suite **46 passed, 3 deselected**; mypy strict clean; ruff clean. Ran `-m live` —
**all 3 fetchers (GH/Lever/Ashby) pass against real endpoints.**

**Next:** Chunk 6 — diff set arithmetic (pure `compute_diff(fetched_ids, stored_open_ids) → new/still_present/closed`,
all empty cases), the last pure-logic piece before DB/persist. Fresh `feat/diff-arithmetic` branch.

---

## 2026-06-15 — Chunk 4: endpoint construction + Greenhouse fetcher (first real fetch)

**Did:** Stood up the first Layer-1 fetcher — the loop now pulls real postings.
- `src/vja/fetchers/endpoints.py`: `build_endpoint(employer)` — derives the URL from `ats_slug` for
  Greenhouse/Lever/Ashby; uses the explicit `endpoint` column for Workday/others; raises `ValueError`
  (a *config* defect, distinct from a runtime `FetchError`) when neither is possible.
- `src/vja/fetchers/greenhouse.py`: `GreenhouseFetcher` (satisfies the `Fetcher` Protocol). GET
  `…/boards/{slug}/jobs?content=true`, maps each job per `docs/05` (`external_id = str(id)` — D-016 string
  key; `title`; `apply_url = absolute_url`; `location = location.name`; `updated_at`; full job → `raw`).
  Every failure mode is loud: non-200, network error, non-JSON, missing `jobs` list, non-object job, and
  missing required field all raise `FetchError` — never a silent empty/garbage result. Injectable httpx
  client; identifiable User-Agent (politeness, `docs/05`).
- `tests/fixtures/greenhouse.json`: captured real `camusenergy` response (3 jobs, full structure — D-019 golden).
- Tests: 6 endpoint-construction units (each ATS + the two raise paths); 9 Greenhouse units via respx against the
  fixture (mapping, int→str id, missing location → None, empty board → `[]`, + 5 FetchError paths); 1 opt-in
  `-m live` smoke that pins Greenhouse's *response shape* (catches ATS drift), in new `tests/live/`.

**Verified:** default suite **32 passed, 1 deselected**; mypy strict clean; ruff clean. Ran `-m live` once —
real fetch against camusenergy **passed** (first proof the fetch path works end-to-end).

**Note:** wiring `content_hash` (Chunk 3) to the Greenhouse description (`content`) happens at persist time, not in
the fetcher — comes with the diff/persist chunk.

**Next:** Chunk 5 — Lever + Ashby fetchers (same pattern, fixtures from `voltus` / `weave-grid`), completing the 9
verified GH/Lever/Ashby companies. Fresh `feat/lever-ashby-fetchers` branch.

---

## 2026-06-15 — Chunk 3: content_hash canonicalization

**Did:** Built the extraction cache's correctness primitive (`docs/04` §3).
- `src/vja/hashing.py`: `content_hash(*, title, location, description) -> str` — hex SHA-256 over a canonical,
  sorted-key JSON object of the **stable fields only**. `_normalize` collapses whitespace runs + strips (so reflowed
  HTML / trailing newlines don't churn the hash) while keeping case. Volatile junk (view counts, "updated X ago",
  tracking params, request timestamps) is excluded *by construction* — it's never passed in.
- `tests/unit/test_hashing.py`: 9 unit tests — determinism + 64-char hex shape; a **golden-value regression lock** on
  the canonical form (so any normalization change is a deliberate, reviewed decision rather than a silent cache-wide
  invalidation); whitespace-invariance; None≡empty; sensitivity to each of title/location/description; case-significance;
  and a volatile-payload-exclusion test documenting intended caller usage.

**Note:** `content_hash` is the pure function only. Wiring it to each ATS's description field (Greenhouse `content`,
Lever/Ashby `descriptionPlain`) lives in the fetcher/persist chunks — `RawPosting` carries the description inside
`raw`, so extraction of the stable description is per-ATS and comes later.

**Gates:** ruff format/check, mypy (strict), pytest (**17 passed**) all green.

**Next:** Chunk 4 — endpoint construction + the Greenhouse fetcher + a captured fixture (`tests/fixtures/greenhouse.json`)
+ mapping unit test + opt-in `-m live` smoke. On a fresh `feat/greenhouse-fetcher` branch.

---

## 2026-06-15 — Chunk 2: domain models + Fetcher contract

**Did:** Froze the contract everything builds on (`docs/04`/`05`).
- `src/vja/models.py`: `RawPosting` and `Employer` as frozen, slotted dataclasses (value objects — a fetcher is a
  pure read and never mutates them); schema enums `AtsType`, `Level`, `RemoteType`, `Verdict` as `StrEnum` so a
  member's `.value` is exactly the string the DB stores. `RawPosting.external_id` documented as THE diff key (D-016),
  never synthesized from the title.
- `src/vja/fetchers/base.py`: the `Fetcher` `Protocol` (`runtime_checkable`) + `FetchError`, whose docstring pins the
  highest-stakes rule — a raised `FetchError` must never be read as "zero open jobs" (no mass-close on failure).
- `tests/unit/test_models.py`: 7 unit tests — field mapping, `None`-optionals, immutability (frozen raises), enum
  `.value` strings + value→member round-trip (used by the later seed import), Protocol conformance, `FetchError` type.

**Spec reconciliation:** `docs/04` §1's `ats_type` list was narrower than the seed CSV (missing `icims`, `radancy`,
`custom`, etc.). Modeled `AtsType` as the full superset (grouped by build tier per `docs/07`) and updated `docs/04`
to match, naming `vja.models.AtsType` as the enum source of truth. **Open:** the `verification` enum has the same
drift (`docs/04` says verified/suspect/unverified; seed uses verified/detected/layer2) — defer to the DB-import chunk
where it's consumed.

**Gates:** ruff format/check, mypy (strict), pytest (8 passed) all green.

**Next:** Chunk 3 — `content_hash` canonicalization (pure fn + hard unit tests: invariant under volatile junk + key
order; changes with description). On a fresh `feat/content-hash` branch.

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
