# Codebase audit — 2026-09-15

**Scope:** local code at `b7f08e9` (PR #128), existing offline checks, and current official
analytics documentation. Recommendations only; no application behavior or production settings
changed. Production DB, billing, Cloudflare configuration, live provider behavior, and current
production deployment were not re-audited. August's production numbers remain historical evidence.

**Readback:** Rolefeed is live; 1.2 is closed and 1.3 contains the extraction recovery and Scheduler
retry fixes. WORKLOG's August 22 top entry is complete but 24 days stale. This audit identifies
fixes, visitor measurement, and a coherent next update.

## Findings, ranked

P1 = fix in the next update; P2 = bounded correctness or resilience improvement. These are code
defects or known design limitations, not claims that a production incident is occurring today.

### A1 · P1 · Layer-2 failure still reports a successful job

**Evidence:** `src/vja/nightly.py:175` catches a failed vertical and replaces its result with zero
work and zero cost. An extraction circuit-breaker abort only logs an error (`:189`). Final status
at `:242` considers Layer 1 and digest failures, excluding both Layer-2 cases. `_default_layer2`
also discards matching's failed count. `nightly_main` returns exit 0 for this outcome. The policies
in `deploy/gcp/alerts.sh` watch task results/absence, not these application errors.

**Reproduced:** injected `Layer2Summary(extract_aborted=True)` into the real orchestrator with a
throwaway SQLite database: `status=ok`, `alerted=False`.

**Fix:** carry attempted/succeeded/failed/aborted counts through each stage; persist a failed or
degraded outcome and alert on systemic failure, while continuing independent verticals. Keep
isolated provider failures from producing an alert per posting. Add a separate no-progress alert:
eligible work after Stage A + attempts + no successful progress, rather than raw backlog size.
Zero eligible work must remain a healthy outcome. Check extraction and matching independently.

**Acceptance:** an aborted stage and an exception each produce durable failure evidence and an
operator notification; healthy empty runs do not. Also test attempted-but-all-failed batches below
the 20-failure breaker. D-112/D-101; this extends the known alert-on-silence backlog.

### A2 · P1 · The overlap guard ends before the expensive work starts

**Evidence:** `src/vja/pipeline.py:318` finalizes `pipeline_runs` after fetch/diff. Only then does
`run_nightly` begin extraction/matching (`src/vja/nightly.py:175`). The overlap check only searches
for `status=running`. A second invocation during Layer 2 therefore passes, even without the
already-documented simultaneous-start race. Duplicate model calls can precede a match uniqueness
failure; a killed Layer-2 process leaves an apparently finished row.

**Reproduced:** called `_recent_run_in_flight` from inside the injected Layer-2 runner. It returned
`False`; the database row was already `ok`.

**Fix:** give the full orchestrator ownership of the run lifecycle, retaining sensible standalone
`vja-run` behavior. Hold an atomic, expiring run claim through all stages and release/finalize it on
exit. A read-then-insert check alone still has the simultaneous-start race. Checkpoint stage metrics
so a process kill does not erase all accumulated usage.

**Acceptance:** a second run started during extraction or matching does no fetching or paid work;
simultaneous acquisition admits one owner; a crashed owner eventually expires. D-103/D-113.

**Related small fix:** `pipeline.py:315` uses the injected start timestamp as finish time, because
`run_nightly` always supplies `now=stamp`. Reproduction recorded duration **0 seconds**. Separate the
selection clock from completion timestamps and record both stage and total duration.

### A3 · P1 · Late matches can still be permanently omitted from the digest

**Evidence:** `src/vja/match.py:414` writes the run's original `now` as each match's creation time;
`src/vja/db/matches.py::save_match` persists it literally. D-108's eligibility predicate in
`src/vja/digest/assembly.py:149` relies on that column representing when a match became available.

**Example:** pipeline starts at 05:00, digest sends at 06:00, match finishes at 06:20. The match is
stored as 05:00. If the posting also predates 06:00 and that digest sent other content, both sides
of the next digest's eligibility test are false. The dashboard can show a role the inbox never gets.

**Reproduced:** froze wall time 80 minutes after the supplied run timestamp, ran the actual matcher
with a fake model, and built a later digest with a watermark at +60 minutes. The stored match time
was the run start and the next digest returned **0 new roles**.

**Fix:** retain the run timestamp for stable candidate selection, but use a fresh, injectable clock
at match persistence. Preserve D-108's nightly-trigger gate, reopen behavior, and no historical
redelivery decision. Pin the interaction through matcher → persisted row → subsequent digest, not
only a hand-seeded `created_at` fixture. D-108/D-103.

### A4 · P1 · Matching still drops billed failures from the meter

**Evidence:** `src/vja/match.py:400` catches every exception and continues before adding usage/cost.
D-112 added `StructuredOutputError` accounting to extraction, but matching never consumes it.
There is also no systemic matching-failure breaker; the cap is per profile, not a run-wide budget.

**Reproduced:** one fake billed schema failure carrying 900 input tokens, 150 output tokens and
$0.25 produced `failed=1`, **0 metered input tokens and $0.00 cost**.

**Fix:** meter billed failures on both paths, propagate failed/attempted counts, and bound systemic
matching failures across profiles. Keep successful rows idempotent and retry unfinished work on a
later run. Distinguish successful records from actual provider-call counts: the current
`extraction_calls`/`match_calls` fields count successful records. Persist partial usage before a
later stage or database exception can replace it with zero. D-112/D-090/D-101.

### A5 · P1 · Digest retry safety depends on an unbounded timing assumption

**Evidence:** `src/vja/digest/send.py:215` follows create-pending → external send → mark-sent. It
has neither a durable delivery claim nor a provider idempotency key. A lost response or crash
after provider acceptance can leave a sent email locally failed/pending. Two concurrent sends can
both read the old watermark. This is a known deferred risk, not a newly discovered incident.

D-113's measured three-minute run does not establish a maximum: the configured digest timeout is
one hour, longer than the ten-minute retry backoff. The statement that retries are *strictly*
outside a live execution is therefore too strong. The ADR itself acknowledges ambiguous API
acceptance despite initially saying retries only create an execution when none was created.

**Fix:** durable per-recipient delivery identity/claim plus provider idempotency using that same
identity. Retrying must reuse the persisted payload; a bare unique row or a new key each attempt
does not close the send/commit gap. Define how legitimate later same-day digests work before
choosing a date-only uniqueness key. Keep task retries disabled until this is verified.

**Acceptance:** simultaneous workers, provider acceptance followed by a lost response, and a
crash before local mark-sent produce one delivery. Migration and a focused design are likely.
D-086/D-113/D-028. Correct the present-tense safety wording when implementing the decision.

### A6 · P2 · Dashboard responses can overwrite newer filter selections

**Evidence:** `frontend/src/pages/Dashboard.tsx:44` starts a request on every filter/poll change
without cancellation or a generation guard. A slow previous response can replace the rows for the
currently selected filter; its error/finally handlers can also replace newer state. The public
demo already passes an AbortSignal, while `fetchPostings` does not expose one.

**Fix/acceptance:** cancel superseded requests and guard all response handlers. A test resolving
two requests in reverse order must preserve the second selection and its rows. Code-inspected;
not reproduced in a live browser in this audit.

### A7 · P2 · An empty demo universe never finishes loading

**Evidence:** `frontend/src/pages/Demo.tsx:54` accepts an empty vertical list, leaves `vertical=null`
and `loading=true`. Its postings effect returns immediately at `:76`, so no success path clears
loading. The API intentionally returns an empty list when no vertical has displayable rows.

**Fix/acceptance:** explicitly render an empty-board state on `[]`, with a retry action. Add a
component test for the successful-but-empty response. Code-inspected. Also clear or associate rows
with their vertical while switching, so an old board is not temporarily labeled as the new one.

### A8 · P2 · The upload ceiling runs after the whole file is read

**Evidence:** `src/vja/api/app.py:866` calls `await file.read()` and only then checks 5 MB. The
constant's comment claims the in-memory read is capped, but this implementation is not bounded.
PDF parsing also runs synchronously inside the async endpoint.

**Fix/acceptance:** reject known oversize uploads before reading, otherwise read at most limit+1;
also bound incoming multipart/body handling and move CPU-heavy parsing off the event loop. A
bounded-read test should prove an oversize file is not fully copied before rejection. The actual
external request ceiling depends on deployed infrastructure, which was not checked here.

## Important follow-ups and new product improvements

- **Durable onboarding work and honest status.** `run_backfill` marks completion in `finally`
  (`match.py:508`), even on failure; stale unfinished work becomes `done`
  (`db/profiles.py:467`). These are accepted current policies, not accidental regressions. Move to
  resumable queued work and distinguish queued/running/succeeded/failed. Then users can leave the
  tab safely and retry a failed backfill. Requires amending D-082/D-101; keep separate from small fixes.
- **Freshness visibility.** Show last successful pipeline update and a degraded-data message when
  appropriate. An always-OK `/api/health` is liveness, not evidence of fresh data. Build the reliable
  stage signals first; do not infer freshness from re-dated posting rows.
- **Cheaper extraction selection.** `db/postings.py:308` loads `raw_payload` for every unextracted
  candidate before Python rejects titles. Select lightweight identities/titles first, apply the
  existing scope function, then fetch payloads in batches for survivors. Preserve re-evaluation
  after config changes. Avoid rewriting the scope semantics in a second SQL implementation.
- **Operational checks still owed.** Verify current GCP budget alerts, provider balances, email
  capacity, OAuth publishing status and post-D-112 extraction health. Their old worklog statuses
  are not current measurements. Budget alerts notify; an enforced spending cap is separate work.
- **Match-quality review remains open.** D-111's human review of real advice is not replaced by
  passing schema tests. No new prompt or model change is recommended without that evidence.
- **Later product work:** saved/dismissed roles or application status could help returning users,
  but first measure whether people reach and reuse the board. Instant alerts and additional
  employers should follow delivery reliability and current coverage measurements.

## Visitor tracking recommendation

There is **no analytics integration in the checked-in frontend**: no pageview/event module,
tracker script or analytics dependency. The database tracks accounts/profiles, not anonymous
visits. Edge-injected tracking could exist independently; Cloudflare settings were not inspected.
The old “5,000 views → 10 uploads” comments are not an instrumented conversion funnel in this code.

### Choose one primary audience tool

| Option | What it answers | Fit |
|---|---|---|
| **Plausible, recommended** | Estimated unique visitors, pageviews, acquisition sources, custom conversion events; richer funnel analysis on an appropriate plan | Best for “how many people visit, and do they get value?” |
| **Cloudflare Web Analytics** | Visits, pageviews, performance and source/page breakdowns | Good minimal traffic baseline if avoiding another paid service; visits are not distinct people |

Plausible supports SPA navigation and explicit custom events. Its pricing page currently lists
Starter with goals/events, while custom properties and funnel analysis are Business features;
choose the tier deliberately and check the billing interval at signup. Basic event totals do not
require purchasing full funnel analysis. [SPA support](https://plausible.io/docs/spa-support),
[custom events](https://plausible.io/docs/custom-event-goals), [plans](https://plausible.io/#pricing).

Cloudflare is available on all plans and handles SPA navigation. Its definition of a visit uses
the referring hostname, so label that chart **visits**, not **unique people**.
[Overview](https://developers.cloudflare.com/web-analytics/),
[metrics](https://developers.cloudflare.com/web-analytics/data-metrics/high-level-metrics/),
[SPA support](https://developers.cloudflare.com/web-analytics/get-started/web-analytics-spa/).

### Initial measurement contract

1. **Traffic:** daily/weekly estimated visitors (where supported), visits, pageviews, top entry
   pages, referrers and campaign sources. Keep time windows/timezone explicit. A person on multiple
   devices or days is not a provably distinct human; blockers and bots also affect measurements.
2. **Milestones:** `Demo Viewed`, `Sign In Clicked`, `Resume Accepted`, `Matches Viewed`,
   `Apply Clicked`. Count résumé acceptance after HTTP 202, not merely form submission; distinguish
   first onboarding from reuploads. “Matches viewed” requires actual matched rows on screen.
   “Apply clicked” means outbound interest, not a completed application.
3. **Internal truth:** use DB aggregates for current registered accounts and profiles. Report
   accepted uploads and successful backfills separately. Historical deletion and résumé versioning
   mean current row counts are not a complete lifetime-signup total. Anonymous event funnels are
   approximate across the Google OAuth round trip; don't force an identity join with email.
4. **Minimal data:** fixed event names and allowlisted route names. No résumé text, email/name,
   match rationale, freeform search/feedback, user IDs or token-bearing URLs. Never instrument
   `/auth/*`, `/api/*`, or tokenized unsubscribe pages. Disable replay and automatic form capture.
   Update `Privacy.tsx` to name the analytics service and data collected when tracking ships.
5. **Campaigns:** standardize new share links on allowlisted `utm_source`/`utm_campaign` values.
   The demo preserves `?src=`, but no attribution system consumes it here. Plausible supports UTM
   attribution and strips other query parameters by default; don't assume `src` already works.
   [Query parameter behavior](https://plausible.io/docs/custom-query-params).
6. **Verification:** one pageview per completed route navigation, no duplicate automatic/manual
   tracking, no events from local tests, no blocked UI when analytics fails, no sensitive fields in
   recorded requests, and one visible test conversion in the operator's dashboard.

Use the provider's private dashboard initially; Rolefeed needs no custom analytics admin page or
public visitor counter. Tracking begins when enabled. Existing retained edge/access data may offer
a rough historical baseline, but adding a script cannot reconstruct past unique visitors.

## Proposed Update 1.4 — Reliability and visibility

**Proposed, not opened or shipped.** Before the first merge, reconcile 1.3's closeout using its
actual #127/#128 boundary and carry forward unresolved items explicitly. Per `updates/README.md`,
create `updates/1.4.md` only when its first item merges. Keep decisions in ADRs and live rules in
INVARIANTS; this audit does not accept new architectural policy.

| PR-sized unit | Scope | Done when |
|---|---|---|
| 1. Truthful failure/cost signals | A1 + A4 | Aborts alert; billed match failures count; empty healthy runs stay quiet |
| 2. Actual match availability time | A3 | Match completed after the morning send reaches the next digest |
| 3. Whole-run ownership | A2 + duration/checkpointing | Overlap tests pass and full run duration/status is trustworthy |
| 4. Safe delivery retries | A5 | Concurrent/crashed delivery tests prove one provider send |
| 5. Board and upload correctness | A6–A8; split upload into its own PR if needed | Reverse-order response, empty-universe and bounded-read tests pass |
| 6. Audience measurement | Chosen tracker, explicit events, privacy copy, operator setup | Verified pageview and conversion reports with no sensitive payloads |

Start with PRs 1–3. Analytics can ship independently without waiting for the larger delivery claim
design. Durable onboarding belongs in a subsequent update, with a queue/status design of its own.

## Verification and limits

- Backend: **953 passed**, 35 opt-in tests deselected; SQLite/migrations exercised by the suite.
- Frontend: **229 passed** across 19 files; lint, typecheck and production build passed.
- Ruff lint/format, mypy (151 files), import-linter and offline lockfile check passed.
- Four targeted backend defect reproductions passed against the unchanged code using throwaway
  SQLite, fake provider responses and a frozen clock; run duration was also observed as zero.
  The temporary driver was `/private/tmp/rolefeed_audit_repro.py`, invoked with
  `PYTHONPATH=. UV_CACHE_DIR=/private/tmp/vja-uv-cache uv run python /private/tmp/rolefeed_audit_repro.py`.
- Frontend findings were source-inspected, not separately browser-reproduced. No live model calls,
  production data changes, sends, deploys, PostgreSQL rerun, dependency vulnerability scan or full
  security assessment were performed. Existing deprecation/router warnings are maintenance items.
