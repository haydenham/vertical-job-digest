# Testing Strategy

*Build spec for how this project tests itself. Premise: **nearly all code here is written by Claude Code**, so tests
are not a safety net we add later — they are the mechanism by which we trust the code at all. The rule is simple:
no behavior is "done" until a test pins it. This doc defines the four test levels in **this project's** terms,
and the protocol for when each applies.*

Builds on **D-019** (tests run against captured fixtures, not live endpoints). Nothing here contradicts it.

## The shape (a pyramid, deliberately)

```
        E2E / live        ← a handful. Opt-in. Real network/LLM/email. Catch drift, not logic.
      ─────────────────
       System            ← a few. Whole nightly pipeline, in-process, externals faked.
    ───────────────────
     Integration         ← more. 2+ components across a real boundary (real SQLite).
  ─────────────────────────
   Unit                  ← most. Pure functions, no I/O, microseconds.
```

Fast tests are run constantly and so stay green; slow/flaky tests get skipped and so rot. We push as much coverage
as possible **down** the pyramid. If a thing *can* be tested as a pure function, it must be.

The default test command (`pytest`) runs **unit + integration + system** — all deterministic, offline, free, seconds
to run. The `live` and `e2e` tiers are opt-in markers that never run in the inner loop or block a merge. The `eval`
tier is also out of the local inner loop, but **does** block a merge in CI — *only* on PRs that touch the
prompt/matching/extraction code (path-filtered; see the eval section + `09`).

---

## Level 1 — Unit

**Scope:** one pure function, in isolation, zero I/O (no network, no DB, no clock, no LLM). Microsecond-fast.

**What lives here in this project:**
- **Fetcher field-mapping** — given a fixture payload dict, does `map()` produce the right `RawPosting`?
  (`external_id`, `title`, `apply_url`, `location`). One test per ATS module against `tests/fixtures/{ats}.json`.
- **`content_hash` canonicalization** — deterministic over the stable fields; **invariant** under volatile junk
  (view counts, "updated X ago", tracking params, key ordering). Same content ⇒ same hash; reorder keys ⇒ same hash;
  change description ⇒ different hash. This is the cache's correctness; test it hard. (Spec: `04` §3.)
- **Diff set arithmetic** — given `fetched_ids` and `stored_open_ids`, compute `new / still_present / closed` correctly,
  including the empty cases. Pure set logic, no DB. (Spec: `04` "Posting lifecycle".)
- **Endpoint construction** — `(ats_type, slug)` → URL for GH/Lever/Ashby. (Spec: `05`.)
- **Cheap pre-filter** — level/location/work-auth gating logic that runs before the strong model.
- Any normalizer: level mapping, comp-string parsing, location cleanup.

**Rules:** network and the Anthropic SDK are **never** touched here — if a function needs them, it isn't a unit and
belongs one level up (or should be refactored so its pure core *is* unit-testable). Freeze the clock for anything
that stamps `*_at`.

## Level 2 — Integration

**Scope:** two or more real components talking across a real boundary — **almost always the database**. Real SQLite
(in-memory or a temp file), real SQL, real schema. External services (ATS HTTP, Anthropic, Resend) are **stubbed/faked**.

**What lives here:**
- **fetch → diff → persist:** feed a fetcher a fixture, run the diff, assert the rows in `postings` — new rows
  `open` with `first_seen = last_seen`, and on a second pass with one id removed, that id flips to `closed` with
  `closed_at` set and **is not deleted** (D-009).
- **The "never mass-close on fetch failure" guard** (the single highest-stakes integration test): a fetch that
  raises `FetchError` must **not** close yesterday's postings — it records a `fetch_failure` and leaves rows
  `open`. (Spec: `05` health check.) Mass-closing on a transient 500 would ship a digest claiming every job died.
- **Extraction cache reuse:** unchanged `content_hash` ⇒ extraction is **not** re-invoked (assert the faked LLM
  was called zero times); changed hash ⇒ it is. This is D-005 cost discipline, made testable.
- **`matches` versioning:** re-matching a new `resume_version` inserts a new row, never overwrites
  (`UNIQUE(posting_id, profile_id, resume_version)` — spec `04` §5).
- **Digest assembly:** given known DB state, the `digests.contents` JSON contains the right new/closed sets.

**Rules:** HTTP is stubbed at the transport layer (`respx`/`responses`), so no real packets leave. The LLM is a
fake returning canned structured output. Every test gets a fresh DB; no shared state between tests.

## Level 3 — System

**Scope:** the **whole nightly pipeline** as one orchestrated run — `fetch → diff → extract → match → verify → send` —
in-process, real DB, but every external dependency faked (fixture ATS responses, fake LLM, fake mailer, fake
link-verifier). Deterministic and free; this is the closest we get to "a real night" without leaving the process.

**What it asserts:**
- A full run over a small seed of fake employers produces the expected `pipeline_runs` summary row:
  `employers_fetched`, `fetch_failures`, `postings_new/closed`, `extraction_calls`, `match_calls`, `llm_cost_usd`,
  `status ∈ {ok, partial, failed}`. (Spec: `04` §7.)
- **Idempotency:** run the pipeline twice over identical fetched data — the second run produces an **empty diff**,
  no duplicate postings, no second digest of the same content. (If night 2 re-sends night 1, the diff isn't a diff.)
- **Verification gate (D-008):** a posting whose `apply_url` fails the (faked) resolver is **quarantined** and does
  **not** appear in `digests.contents`. One fake posting must never ship.
- **Partial-failure handling:** one fetcher throws, the rest of the pipeline still completes and sends; the run is
  marked `partial`, not `failed`, and the failure is in `pipeline_runs.errors`.
- **A failed digest send leaves a loud `failed` record** (spec `04` §6) — silence is the bug.

**Rules:** still no real I/O. The point is orchestration correctness — wiring, ordering, summary records, the
"loud failure" contract — not the behavior of any one component (that's Levels 1–2).

## Level 4 — E2E / live (opt-in, never in the inner loop)

**Scope:** the real outside world. Real network, real ATS endpoints, real Anthropic calls, real (sandbox) email.
Slow, flaky by nature, costs tokens. Gated behind pytest markers (`-m live`, `-m e2e`); excluded from the default
run and from the merge gate. Run **before a weekly milestone**, when **ATS drift is suspected**, or after touching
a fetcher/the SDK integration — not per-commit.

**Two flavors:**
1. **Live ATS smoke (`-m live`, from D-019):** hit a couple of *real* verified Greenhouse/Lever/Ashby endpoints and
   assert the response *shape* we map still holds (the keys in `05` are present, types unchanged). This is the
   tripwire for the documented #1 risk — an ATS quietly changing its JSON and our mappers silently producing garbage.
   It tests *their* contract, not our logic.
2. **Full real run (`-m e2e`):** run the actual pipeline against a tiny real employer subset and send a digest to a
   **test inbox** via Resend's sandbox. A human eyeballs the result. This is the "proof-of-loop" check, run at
   milestone boundaries (week-1 first-diff-in-inbox; week-3 match column; week-4 aviation vertical add).

---

## LLM output is tested separately — as evals, not asserts

Matching and extraction are **non-deterministic**: you cannot `assert rationale == "..."`. So the LLM is **mocked
everywhere in Levels 1–3** (the pipeline's *wiring* is deterministic and gets tested; the model's *words* do not
run there). The model's actual behavior is pinned by a small, separate **eval suite** (`-m eval`, opt-in, metered):

Two sub-tiers, split by determinism so the gate is robust to the model flapping:

- **(a) Structural properties — deterministic, hard gate.** On model output (a recorded response is enough; no
  live call needed): `verdict ∈ {strong_yes,yes,maybe,no}`; `fits` non-empty AND `gaps` non-empty for **every**
  match (D-007 — a rationale missing either is a defect); extraction `level ∈` the allowed enum; `stack` parses as
  a JSON array. These are pure schema checks — they cannot flap, so they **block hard**.
- **(b) Behavioral cases — live, threshold gate.** The willingness-to-say-no test (a product requirement, not a
  nicety — D-007): a curated, deliberately-bad posting (senior role, wrong domain, visa-blocked) **must** return
  `verdict = no`; a couple of "obvious yes" cases must clear `maybe`. These call the real model, so they gate on a
  **threshold/majority over the small golden set** (e.g. sample an "obvious no" a few times, require the majority to
  say `no`) rather than demanding one perfect run — a single flaky sample warns, a real regression (the model now
  says `yes` to junk) fails the set.
- **This is a merge gate, not just a signal — but a *path-filtered* one.** CI runs `-m eval` **only when the PR
  touches the prompt / matching / extraction code** (`09`), exactly the changes that can degrade what ships in the
  digest. Other PRs never trigger it, so unrelated work pays neither tokens nor flake risk.
- **Metered + small.** Every eval run counts toward LLM spend, but the golden set is a handful of cases and only the
  prompt-touching PRs trigger it, so the bill is cents — cheap insurance on the one trust-critical output. Keep the
  set small and curated; grade structure/coverage against a rubric (optionally LLM-as-judge) where wording matters.

---

## When to write which test (the protocol)

| You are writing… | The test you owe, **in the same PR** |
|---|---|
| A new pure function (mapper, hash, diff, parser, pre-filter) | **Unit** test against a fixture/known input |
| Anything that reads or writes the DB, or chains two components | **Integration** test on a real temp DB, externals faked |
| A change to the pipeline orchestrator / run summary / send path | **System** test keeping the full run green |
| A new/changed fetcher, or anything touching a real endpoint | a **`live`** smoke fixture refresh; run `-m live` once manually |
| A new/changed matching or extraction **prompt** | an **`eval`** case (incl. an "obvious no"); run `-m eval` once |
| **A bug fix** | the **failing regression test first** (red), then the fix (green). The test reproduces the bug before the fix exists. No regression test ⇒ the bug isn't fixed, it's hidden. |

Non-negotiables:
- **A PR that adds behavior without a test is incomplete.** Reviewer (human) rejects on sight.
- **Push coverage down the pyramid.** Reach for a unit test before an integration test before a system test. If you
  find yourself writing a slow test for logic that could be a pure function, extract the pure function instead.
- **The default `pytest` run stays fast, offline, deterministic, and free.** Anything that isn't gets a marker
  (`live`/`eval`/`e2e`) and leaves the inner loop.
- **Fixtures are captured once and committed** (D-019). Regenerate deliberately (a documented `make refresh-fixtures`),
  never silently in a test.

## Tooling (decided)

- **Runner:** `pytest`. Markers registered in config: `live`, `e2e`, `eval` (all opt-in; default run excludes them).
- **HTTP stubbing:** `respx` (httpx) or `responses` — no real packets in Levels 1–3.
- **DB:** real SQLite per test (in-memory or `tmp_path`), schema built from the same migrations as prod; fresh per test.
- **Clock:** freeze time (`freezegun` or an injected clock) wherever a `*_at` is written.
- **Fixtures:** `tests/fixtures/{ats}.json`, one captured golden payload per verified endpoint (D-019).
- **Coverage:** tracked as a signal on the unit+integration+system tiers, not worshipped — a high number over shallow
  asserts is worse than fewer tests that pin the contracts above (diff correctness, the no-mass-close guard,
  verification gate, idempotency).
