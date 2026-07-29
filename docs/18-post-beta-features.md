# Post-beta feature roadmap — plan of record (D-087)

*The reasoned memo behind the post-public-beta feature slate, decided with Hayden 2026-07-14
(D-087). Memo-tier plan (authority order unchanged): when a feature ships, its decisions go to
`DECISIONS.md`, live rules to `docs/INVARIANTS.md`, and this file's status lines get updated.
Nothing in this document is live yet — `docs/15` (beta hardening) still governs current work,
and every rule in `docs/INVARIANTS.md` (notably D-005's once-daily fetch) stays authoritative
until a feature's own build ADR supersedes it.*

## Positioning + selection rule

The product frame (Hayden, 2026-07-14):

- **New** — jobs grouped by a niche vertical (bounded employer universe, total coverage).
- **Better** — AI matching that reasons (fits/gaps/verdict, willing to say *no*).
- **Proven** — it's a job-finding tool; the category needs no explanation.

Benchmark: **jobright.ai**. Its standout is minute-level freshness — seeing *posted 10 minutes
ago* on a role you want "is like striking gold" — plus clean display of location/time/salary/
level. Most of its other surface (résumé editing, networking matches, autofill apply) read as
clutter in actual use.

**Selection rule:** adapt 1–2 proven features from the leaders, add something genuinely novel,
and resist clutter. Redundant-for-us features are rejected on sight (the whole platform is
early-career, so YOE/new-grad flags say nothing here).

The original slate: two adaptations (**F1 freshness**, **F2 salary**) + two novel derivations from data
we already pay to collect (**F3 recurring-gaps report**, **F4 lifespan intel**). D-093 later parks **F5
city/region preferences** as an unsequenced follow-on; it does not expand the active build slate.

## Blocking prerequisite — the D-085 churn diagnosis

Production logs (July 8–10) showed **343–654 "new" and 384–592 closed postings per night from a
static 44 fetched employers** — posting identity is likely churning (close/reopen cycles). This
was already queued in D-085 ("correctness before discount", ahead of Batch API work). It is
**load-bearing for this roadmap**, and it has not improved: run 36 on **2026-07-28** logged
**357 new / 481 closed / 87 reopened** across 155 employers.

### How a reopen actually blocks (corrected 2026-07-28 — read this before sizing F1)

An earlier version of this memo said F1 would amplify churn into "repeated LLM spend every poll."
**That is wrong, and the correction matters because it moves the whole risk from cost to trust.**
A reopen costs **zero** LLM:

- **Matching** — `postings_needing_match` filters on `~exists(already_matched)` keyed on
  `(posting_id, profile_id, resume_version)` (`src/vja/db/matches.py:85`). `reopen_posting`
  updates the row **in place** (D-053), so the match row survives and the posting is never a
  candidate again.
- **Extraction** — `reopen_posting` clears `extracted_at` **only when `content_changed`**
  (`src/vja/db/postings.py:121`). An unchanged flap keeps the cached extraction (D-035).

What a reopen does instead is **reset `first_seen_at` to now** (`src/vja/db/postings.py:117-119`),
deliberately: *"so the role re-enters the digest's `new` set (which keys on
`first_seen_at > last_sent_at`) and the dashboard's 'new today'."* That one reset propagates to
exactly three places, and they are the product:

1. **The digest's `new` set** — a role the user already saw is presented as new again.
2. **The dashboard's *new today*** window, same reset.
3. **F4's lifespan medians**, computed from `first_seen_at`/`closed_at` — a reset destroys the
   true age.

So 87 reopens a night is 87 roles at risk of being re-presented as new. The cost is credibility,
not spend, in a product whose entire claim is *the diff is the product*.

**Higher polling frequency sharpens this in two ways.** (a) A close/reopen cycle that completes
between two daily fetches is invisible; polling 6x more often catches 6x more of them, and every
catch resets the clock again. (b) The sharper one: **frequency can manufacture reopens.** A fetch
that under-returns marks the missing rows closed, and the next fetch "finds" them and reopens
them. The fetcher-level false-closure guard exists (paginate-or-fail, per fetcher), but the
**pipeline-level threshold guard is P4.3 and remains unbuilt** — `DECISIONS.md` scopes it out of
the fetcher half explicitly, and `CLAUDE.md`'s Phase 4 line still carries 4.3 with no ✅. Six
times the fetches is six times the chances for any board with soft completeness to produce a
false close→reopen pair.

**The diagnosis question is therefore narrow:** are the reopens *real* (an employer genuinely
pulled and reposted a req — in which case resetting `first_seen_at` is correct and F1a is safe to
build) or *artifacts* (a board that intermittently under-returns)? Spread across the universe
says real; concentrated on a few employers or one `ats_type` says artifact, and then **P4.3 is
the actual prerequisite**, not a vague "churn fix."

### Where the diagnosis data lives (and the schema gap)

**Reopens are not recoverable from the DB after the fact.** `reopen_posting` overwrites
`first_seen_at` and nulls `closed_at`, so the row's history is destroyed, and `pipeline_runs` has
`postings_new`/`postings_closed` columns but **no `postings_reopened`**. The only durable record
is **Cloud Logging**, where `vja.pipeline` already emits exactly the right line per changed
employer:

```
employer sync [grid_power_software/Constellation Energy/icims]: fetched=208 new=9 reopened=3 updated=1 closed=9 unchanged=195
employer sync [aviation_software/Amadeus/workday]:             fetched=112 new=4 reopened=4 updated=1 closed=2 unchanged=103
```

Vertical, employer, **`ats_type`**, and per-employer reopen counts — the grouping the question
needs. Cloud Run's log retention bounds the history, so pull it before it ages out.

**Diagnosis runbook (read-only; no build):**

1. **Per-employer reopen concentration, N days** — the primary cut. Pull the `employer sync`
   lines and aggregate `reopened` by employer and by `ats_type`:
   ```
   gcloud logging read 'resource.type="cloud_run_job" AND textPayload:"employer sync"' \
     --freshness=14d --format="value(textPayload)" --limit 5000
   ```
   Parse `[vertical/employer/ats]` and the `reopened=` field; rank employers by total reopens and
   by reopens ÷ `fetched`. A flat spread is real churn; a head of 3-5 employers is an artifact.
2. **Does the head correlate with `ats_type`?** Group the same rows by the third bracket field.
   A Workday/Radancy/Paylocity concentration points straight at pagination completeness and
   therefore P4.3 (and at the D-092 ambiguous-cap boards already failing closed).
3. **Short-lifespan clusters (DB, corroborating)** — reopens erase their own history, but
   *closures* don't. Against Neon:
   ```sql
   SELECT e.name, e.ats_type, count(*) AS closures,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (p.closed_at - p.first_seen_at))/86400) AS median_days
   FROM postings p JOIN employers e ON e.id = p.employer_id
   WHERE p.status = 'closed' AND p.closed_at IS NOT NULL
   GROUP BY e.name, e.ats_type HAVING count(*) > 20
   ORDER BY median_days ASC LIMIT 25;
   ```
   A median lifespan under ~1 day is not a hiring signal; it is a board that flaps.
4. **ATS-date contradiction (DB, corroborating)** — an open posting whose `source_updated_at` is
   far older than its `first_seen_at` was almost certainly reopened rather than newly posted:
   ```sql
   SELECT e.name, e.ats_type, count(*) FROM postings p JOIN employers e ON e.id = p.employer_id
   WHERE p.status = 'open' AND p.source_updated_at IS NOT NULL
     AND p.first_seen_at - p.source_updated_at > interval '30 days'
   GROUP BY e.name, e.ats_type ORDER BY count(*) DESC LIMIT 25;
   ```
   (Noisy for recently-onboarded employers — exclude anything imported inside the window.)

**Likely follow-on either way:** persist `postings_reopened` on `pipeline_runs` so this question
is answerable from the DB next time instead of from logs before they expire. One additive column,
one manual Neon migration (D-083).

No **F1a**, **F1b**, or **F4** build starts until step 1 is done and the answer is written down here.

## F1 — Intraday freshness (flagship adaptation)

**Thesis.** Being early is the single highest-feeling moment in a job search. Our bounded
universe (~66 fetchable employers) makes intraday polling *cheap and polite* where horizontal
boards find it expensive — and postings appear on the employer's own ATS before they propagate
to LinkedIn/aggregators, so "matched to you before it hits the boards" is an honest,
in-vertical-unbeatable claim.

**Split into two builds (2026-07-28).** The freshness win and the alerting win are separable, and
only the second one needs alert idempotency. **F1a is the decided next build; F1b stays parked.**

### F1a — decouple the pipeline from the digest, run it every 4 hours

**Scope (Hayden, 2026-07-28):** fetch → diff → extract → match on a **4-hour** cadence; the email
digest stays **once every morning**. No instant alerts, so no alert-idempotency prereq.

**What is already free** (verified in code 2026-07-28, not assumed):

- **The digest window needs no change at all.** `build_digest` resolves `since` to
  `last_sent_at` for that recipient (`src/vja/digest/assembly.py:162`), **not** "the last 24
  hours." A daily digest on top of 4-hourly pipeline runs already covers everything since
  yesterday's send.
- **`vja-digest` already exists** as a standalone CLI entry point (`digest/send.py:send_main`).
- **Total LLM spend is ≈ flat** — extraction is `content_hash`-cached and matching excludes
  already-matched postings, so the same postings cost the same, just discovered sooner.
- **The container already has two run targets** (`vja-api`, `vja-nightly`); a third is an
  entrypoint override, no second build (D-060).

**Cadence evidence** — 20 nightly executions to 2026-07-28: median **~30 min**, most runs 13-40.
Every tail is a *catch-up*, not steady state: 172 min (07-14) and 118 (07-16) sit on the
SPAN/Brattle and robotics config adds; 90 min (07-27) and 69 (07-28) are the trading vertical's
first pass and its extraction tail. Last night split as **~12 min fetch+diff over 155 employers**
(finishing 11:13 from an 11:00 start) and ~56 min of Layer 2 + digests. At a 4-hour cadence each
run carries a sixth of the accumulated diff, so Layer 2 shrinks proportionally while the ~12-min
fetch floor stays fixed: **realistic steady-state run ≈ 15-20 min in a 240-min window.**

**Build list:**

1. `--no-digest` flag on `vja-nightly` (its argparse currently takes no arguments) — or a
   dedicated `vja-intraday` entry point. Trivial either way.
2. Promote `vja-digest` to a first-class scheduled job: it has **no failure alerting** today —
   that lives in `nightly.py:_send_failure_alert` and would be left behind by the split.
3. **Skip-if-running guard** (not a queue). Cheap insurance rather than load-bearing at 4h: the
   only thing that can still exceed 240 min is the first run after a **config-only** vertical or
   employer add, which needs no deploy and can land any time.
4. Deploy: two Cloud Run Jobs + two Cloud Scheduler entries in `ship.sh`; retune
   `--task-timeout` **below the interval** (D-086's 6h is sized for a daily job and would let a
   hung run overlap the next three).
5. Retune both D-101 alert policies — `absent_over_time(...[26h])` is wrong for both halves, and
   each job wants its own *failed* + *did-not-run* pair.
6. **A spend ceiling on the pipeline path.** D-101 deliberately narrowed the daily ceiling to
   *backfill* matches, so the nightly is uncapped — fine at one run/day, much less fine at six.
7. Its own ADR superseding D-005's "once per day per employer row" invariant + the INVARIANTS
   edit.

**Free side effect worth naming:** the pipeline job becomes **retry-safe** once it sends no
email, which is the exact constraint D-086 cited for `--max-retries 0`. Retries can come back on
the pipeline half while the digest half keeps zero.

**Sizing:** roughly two PRs plus the ADR. Nothing needs rewriting; the architecture anticipated
this split.

**Prereq:** the churn diagnosis above — specifically step 1. Reopens cost no LLM (see the
correction), so the risk F1a carries is **repeat roles in the morning digest**, not spend.

**Status:** scoped and cadence-decided; **blocked on the churn diagnosis**, not started.

### F1b — instant alerts (parked)

New relevant-verdict matches (`models.RELEVANT_VERDICTS`; exact threshold — e.g. strong_yes-only
— decided at build) trigger an immediate per-user email via Resend: "*{title} at {company},
posted N minutes ago*" + rationale. Requires an **alerted-at idempotency marker** on the match
for at-most-once delivery across polls and retries (same family as the D-086 delivery-idempotency
follow-on — build them together). Also wants relative freshness ("2h ago") on dashboard rows.

**Prereqs:** F1a shipped; alert idempotency design; churn diagnosis (a flapping role would alert
twice, which is far more intrusive by email than a repeated digest line).
**Status:** parked, deliberately behind F1a.

## F2 — Salary display (adaptation)

People love seeing salaries. Two phases, one rejected path.

**Phase A — surface what we already extract (cheap, first). ✅ Built 2026-07-24 (D-095).** The
fill-rate query ran first as planned: 172 of 314 in-scope open postings (55%) carry `comp_min`/
`comp_max`, 176 carry `comp_raw`, and `comp_min` is never present without `comp_raw`.

It also turned up the finding that reshaped the build: **the stored integers are not display-safe.**
Haiku annualizes despite the prompt forbidding it (`$49.82/hour` → `103579/125258`; a ten-week
internship at `$4,250 weekly` → `170000/170000`), stores non-USD amounts as bare integers, and
sometimes sources figures that `comp_raw` never quotes. So Phase A shipped a **corroboration guard**
(`vja.comp`) rather than a formatter: the range renders only when `comp_raw` agrees it is annual USD,
else `comp_raw` shows verbatim. 157 of 176 comp-bearing rows display; all 19 suppressions are saves.

Display treatment landed as **panel-only** — not the row chip or column this memo assumed — because
~45% of rows have no salary and a half-empty column reads worse than a click. That put the load on
panel discoverability, answered with a persistent row chevron + sharpened guide copy. The extraction
prompt was tightened in the same PR (future extractions only; the guard is what makes display safe).

**Phase B — H1B/DOL enrichment for comp-less postings.** The US DOL publishes quarterly
LCA/H1B wage-disclosure files — real, per-company, per-role, per-location salaries, free and
public. Bounded universe again makes this tractable: filter each quarterly file to our ~100
employers, normalize title families, store aggregate ranges per (company, title-family,
location), display as a clearly-labeled estimate: "*H1B-disclosed range for similar roles at
{company}*". Honest labeling matters — the data skews toward visa-sponsored roles. Independent
data-only sub-project; can run parallel to F1/F3.

**Rejected path — Glassdoor/Indeed.** No open API exists (Glassdoor's partner API has been
closed for years; Indeed's publisher API is dead), and scraping them would violate both their
ToS and our own politeness-is-policy invariant. Documented closed; do not re-litigate without
an official partnership on the table.

**Status:** Phase A **built** (D-095, salary in the detail panel); Phase B planned, not started.

**Added alongside Phase A (not originally in this slate): posting description display. ✅ Built
2026-07-24 (D-095 PR 2).** The description was never persisted — `RawPosting.description` existed
but only `raw_payload` was stored, and the list-only ATSs (~41% of in-scope open) discarded their
lazily-fetched detail body after handing it to the model. A `postings.description` column (HTML
normalized to plain text by the new `vja.text`) filled at insert and at extraction gives full
coverage going forward at zero new fetch and zero new LLM cost; existing rows fill as postings
insert, change, reopen, or re-extract (**no backfill**).

Sizing decided the read path: 184 of 314 in-scope open rows carry a body today, median ~3.2 KB of
plain text (p90 5.5 KB), so inlining would push a tens-of-KB dashboard load past 1 MB to serve text
opened on a handful of rows. It is therefore its own endpoint — **`GET /api/postings/{id}`**, fetched
when the panel opens — and the list response is unchanged. Two findings shaped the normalizer:
Greenhouse ships its `content` field as *escaped* HTML, and a newline-separator flatten shatters
sentences around inline tags. The live smoke also caught a real defect the unit tests missed — a
string `"loading"` sentinel rendering itself into the panel — now pinned by a regression test.

## F3 — Recurring-gaps report (novel)

**Thesis.** We store `matches.gaps` for every match ever made. Aggregated per user, that's a
career-coaching artifact nobody else has: "*across your 40 matches this month, the #1 thing
between you and strong_yes is X.*" It deepens the AI-matching **better** rather than adding
surface clutter, and it drives the existing résumé-update → re-match loop.

**Design sketch.** Periodic (monthly, and/or on résumé update) aggregation of the profile's
recent `matches.gaps` → one cheap LLM summarization call (Haiku-tier) → top recurring gap
themes + concrete advice. Surfaced as a dashboard card and/or a digest footer section. Cost:
one small model call per user per period — negligible; still metered (D-035/D-069 rules apply).

**Status:** planned, not started. No churn dependency (gaps text is per-match, not lifecycle).

## F4 — Urgency / lifespan intel (novel; the D-009 promise)

**Thesis.** D-009 promised posting-lifespan stats per company; no one surfaces "how fast does
this company close roles." Combined with F1's freshness, it completes the urgency story:
*posted 2h ago + typically fills in 9 days = apply now.*

**Design sketch.** Per employer: `median(closed_at − first_seen_at)` over closed postings
(months of closure data exist). Read-only API addition + dashboard treatment: a "typically
fills in ~N days" chip in the side panel, and a *closing soon* flag when a posting's age
approaches its employer's median. Zero LLM cost.

**Prereq:** churn fix — reopen/close cycling corrupts the medians (D-053 reopen semantics also
reset `first_seen_at`, which the stat must account for).
**Status:** planned, not started.

## F5 — City + region preferences (parked follow-on; D-093)

City selection is a proven job-board control. The Rolefeed-specific extension is broader regions: a user could
select “Midwest” and matching could map that preference to Chicago or other cities named in a posting. This is
the first concrete use case for variable prompt components derived from user preferences.

Location remains logistics, not match quality: preferences should annotate or prioritize the write-up/list,
not change the semantic résumé-to-role score. Explicit country/work-authorization incompatibility remains a
separate hard signal. The current one-size-fits-all prompt stays in place; schema, region taxonomy, UI, and prompt
wiring wait for a dedicated post-beta decision rather than riding the Luna cutover.

**Status:** idea accepted and parked; not sequenced or built.

## Sequencing (post-beta-exit)

1. **Churn diagnosis** (D-085 queue — blocking F1a, F1b, F4). Read-only; runbook above. **Next up.**
   → if the reopens are artifacts, **P4.3** (pipeline-level mass-closure threshold guard) becomes
   the real prerequisite and moves to position 2.
2. ~~**F2 Phase A** — salary surfacing~~ ✅ built 2026-07-24 (D-095), with description display
   added to the same block
3. **F1a** — 4-hourly pipeline, daily digest (flagship; own ADR superseding D-005). Promoted
   ahead of F4: it is the user-visible freshness win, and F4 needs *post-fix* data to be
   meaningful anyway.
4. **F4** — lifespan intel (read-only, zero LLM; needs post-churn-fix data)
5. **F3** — recurring-gaps report
6. **F1b** — instant alerts (needs F1a + alert idempotency)
- **F2 Phase B** (H1B enrichment) — parallel track, data-only, no ordering dependency.

## Explicitly rejected / parked (the anti-clutter record)

- **Glassdoor/Indeed scraping** — ToS + politeness invariant; no open API. Closed.
- **YOE / new-grad flags** — redundant; the platform is early-career by construction.
- **Networking matches, autofill apply** — clutter in the benchmark product; autofill also
  collides with the core **no auto-apply** rule. Not adapted.
- **Applicant counts** ("<25 applicants") — no honest data source outside LinkedIn's walled
  garden; freshness (F1) is our substitute signal for the same feeling. Parked unless a
  legitimate source appears.
