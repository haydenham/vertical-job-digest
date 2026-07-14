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

The slate: two adaptations (**F1 freshness**, **F2 salary**) + two novel derivations from data
we already pay to collect (**F3 recurring-gaps report**, **F4 lifespan intel**).

## Blocking prerequisite — the D-085 churn diagnosis

Production logs (July 8–10) showed **343–654 "new" and 384–592 closed postings per night from a
static 44 fetched employers** — posting identity is likely churning (close/reopen cycles). This
was already queued in D-085 ("correctness before discount", ahead of Batch API work). It is now
**load-bearing for this roadmap**:

- **F1** would amplify churn into alert spam + repeated LLM spend every poll instead of nightly.
- **F4**'s lifespan medians are computed from `first_seen_at`/`closed_at`; churn corrupts them.

No F1 or F4 build starts until the churn diagnosis lands and steady-state numbers are re-measured.

## F1 — Intraday freshness + instant alerts (flagship adaptation)

**Thesis.** Being early is the single highest-feeling moment in a job search. Our bounded
universe (~66 fetchable employers) makes intraday polling *cheap and polite* where horizontal
boards find it expensive — and postings appear on the employer's own ATS before they propagate
to LinkedIn/aggregators, so "matched to you before it hits the boards" is an honest,
in-vertical-unbeatable claim.

**Design sketch.**

- **Scheduler:** Cloud Scheduler → a new intraday Cloud Run Job every ~1–2h, running
  fetch → diff → extract → match with **no digest stage**. The nightly `vja-nightly` keeps the
  digest (roll-up of the day, including already-alerted roles).
- **Alerts:** new relevant-verdict matches (`models.RELEVANT_VERDICTS`; exact threshold — e.g.
  strong_yes-only — decided at build) trigger an immediate per-user email via Resend:
  "*{title} at {company} — posted N minutes ago*" + rationale. An **alerted-at idempotency
  marker** on the match guarantees at-most-once alerting across polls and retries (same family
  as the D-086 delivery-idempotency follow-up — build them together).
- **Dashboard:** relative freshness ("2h ago") on rows; the *new today* window already exists.
- **Economics:** fetch+diff is deterministic HTTP, zero LLM. Extraction/matching already runs
  only on diff items, so total LLM spend ≈ unchanged — the same new postings, matched hours
  earlier. Politeness: ~66 employers × 12–24 polls/day is trivially within the politeness
  policy; per-fetcher rate limits unchanged.
- **Invariant impact:** supersedes D-005's "each ATS endpoint is hit once per day total" line
  **at build time** via its own ADR + INVARIANTS edit. Until then D-005 stands.

**Prereqs:** churn fix (above); alert idempotency design.
**Status:** planned, not started.

## F2 — Salary display (adaptation)

People love seeing salaries. Two phases, one rejected path.

**Phase A — surface what we already extract (cheap, first).** `postings.comp_min`/`comp_max`/
`comp_raw` are extracted by the Haiku pass and stored but never displayed — `PostingRow`
(`src/vja/api/app.py:113`) omits them. Build: additive API fields → dashboard row (compact
range) + side panel (raw string). **First step is a fill-rate query** (% of in-scope open
postings with non-null `comp_min`) — pay-transparency states mean coverage should be
meaningful, but the display treatment (chip vs. column) depends on the number.

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

**Status:** planned, not started (Phase A is the recommended first build of the slate).

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

## Sequencing (post-beta-exit)

1. **Churn diagnosis** (D-085 queue — now blocking F1 + F4)
2. **F2 Phase A** — salary surfacing (smallest visible win; days not weeks)
3. **F4** — lifespan intel (read-only, zero LLM; needs post-churn-fix data)
4. **F1** — intraday freshness + instant alerts (flagship; own ADR superseding D-005)
5. **F3** — recurring-gaps report
- **F2 Phase B** (H1B enrichment) — parallel track, data-only, no ordering dependency.

## Explicitly rejected / parked (the anti-clutter record)

- **Glassdoor/Indeed scraping** — ToS + politeness invariant; no open API. Closed.
- **YOE / new-grad flags** — redundant; the platform is early-career by construction.
- **Networking matches, autofill apply** — clutter in the benchmark product; autofill also
  collides with the core **no auto-apply** rule. Not adapted.
- **Applicant counts** ("<25 applicants") — no honest data source outside LinkedIn's walled
  garden; freshness (F1) is our substitute signal for the same feeling. Parked unless a
  legitimate source appears.
