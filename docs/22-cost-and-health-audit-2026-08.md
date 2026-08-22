# Cost + system-health audit — 2026-08-22 (UTC)

> **Status update (same session).** Items 1–3 and 6 of the ranked list below were **built** in
> `fix/extraction-schema-drift` and are covered by **D-112**: the repair at the `vja.llm` boundary,
> failure-path metering, the extraction circuit breaker, and the age floor on
> `postings_needing_extraction`. Verified live — 5/5 real postings extracted. **Not yet deployed;
> the burn continues until it is.** Items 4, 5, 7 and 8 remain open. This doc is otherwise left as
> written, as the record of what was true at the time of measurement.

**What this is.** A point-in-time, read-only audit of what Rolefeed costs and how it is actually
behaving in production, taken after Update 1.2 closed its last PR. No code changed in this session.

**Why it isn't an update doc.** `docs/updates/` groups *shipped work*. This is measurement, not a
release. Findings that become live rules belong in `DECISIONS.md` + `docs/INVARIANTS.md`; the
candidate ADRs are listed at the bottom.

**A note on dates.** Production runs on UTC and the audit was taken as UTC crossed into 2026-08-22.
Every date below is UTC. "Today" = 2026-08-22, whose first pipeline run had just started.

---

## The headline: extraction has been failing 100% since 2026-08-18, and we are paying for it

Layer 2 extraction stopped producing output on **2026-08-18 at 06:19 UTC**. It did not stop
*running*. Every run since has called Claude Haiku 4.5 on the full unextracted backlog, been billed
for every call, and thrown away every response at the Pydantic boundary.

**Zero postings have been successfully extracted since 2026-08-18.** Confirmed by keying on
`postings.extracted_at`: the last row stamped is 08-18, and 08-19 through 08-22 return no rows at
all.

### What the model is returning

Every response fails `ExtractedFields` validation with the same shape — the model is returning
**strings where the schema wants structured types**:

```
stack     Input should be a valid array   [input_value='["Excel", "PowerPoint", "Bloomberg"]', input_type=str]
comp_min  unable to parse string as integer [input_value='null', input_type=str]
comp_max  unable to parse string as integer [input_value='null', input_type=str]
```

A JSON-encoded *string* instead of a list; the literal four-character string `'null'` instead of a
null integer. The content is right and the types are wrong — which is why it fails uniformly rather
than intermittently, and why nothing about the posting corpus predicts it.

### It is a provider-side change, not something we shipped

The deployed image is `rolefeed:b237028`, **built and deployed 2026-08-10**. Extraction broke
**2026-08-18**, eight days later, on a byte-identical image with a pinned LiteLLM. Nothing in our
control changed in between. The behaviour change is upstream of us — either in the Anthropic
structured-output path or in how LiteLLM's `response_format` maps onto it.

Relevant: the current documented Anthropic contract for structured output is
`output_config: {format: {...}}`, and the older top-level `output_format` parameter is deprecated
API-wide. `vja.llm.LiteLLMClient.parse` passes `response_format=response_model` and lets LiteLLM
choose the mechanism. The failure signature — well-formed content, everything stringified — is what
you get from a JSON-mode/tool-emulation fallback rather than native constrained decoding. **That is
a hypothesis, not a verified root cause**; it needs one reproduction against the live API to settle.

### What it has cost

Anthropic console, August month-to-date, all of it Claude Haiku 4.5 (extraction is our only
Anthropic caller):

| Date (UTC) | Anthropic cost | Note |
|---|---:|---|
| Aug 10–14 | $0.98 / $0.85 / $0.73 / $1.41 / $0.75 | normal weekdays |
| Aug 15–16 | $0.06 / $0.05 | weekend, boards quiet |
| Aug 17 | $0.76 | last healthy day |
| Aug 18 | $1.17 | broke at 06:19 UTC |
| **Aug 19** | **$5.20** | |
| **Aug 20** | **$4.66** | |
| **Aug 21** | **$14.26** | |

**Month to date: $35.65.** Against a ~$0.90/weekday baseline, roughly **$22 of that is pure waste**,
and it is accelerating — Aug 21 alone cost more than the preceding eleven days combined.

**It accelerates by construction.** A failed extraction never stamps `extracted_at`, so the posting
returns to the candidate set on the next run, forever. The backlog only grows as Layer 1 keeps
adding ~500 rows/day. Failed calls per day, from Cloud Logging: **191 → 932 → 1,710 → 2,545**. There
is no ceiling in the code — `VJA_PIPELINE_MAX_MATCHES` bounds *matching*, and the daily budget
ceiling only guards *signup backfills* (D-101). Nothing bounds extraction.

### The account is nearly out of credit

**Anthropic credit balance: $5.58.** Yesterday cost $14.26. On the current trajectory the balance is
exhausted within a day, at which point extraction fails on 401/402 instead of on validation — which
would at least stop the bleeding, but by accident rather than by design.

---

## Second finding: the meter cannot see any of this

`docs/INVARIANTS.md` says metering is real, not a proxy. It is real **only for calls that
succeed.**

In `extract.run_extraction`, `usage` and `cost_usd` accumulate *after* the `try` block that wraps
`extract_posting`. A call that reaches the provider, gets billed, and then fails validation is
counted as `failed += 1` and contributes **zero tokens and zero dollars** to the run summary and to
`pipeline_runs`.

The consequence, in the same numbers: for Aug 19–21 `pipeline_runs` records `extraction_calls = 0`
and a total `llm_cost_usd` of about **$0.08**, while the provider billed **$24.12**. The meter did
not merely under-report during the most expensive three days in the project's history — it reported
approximately nothing, and the nightly summary line printed `extracted=0 (in=0 out=0)` while the
spend was 15× normal.

This is the finding with the longest tail. The bug will be fixed in an afternoon; the blind spot is
what let it run for four days unnoticed.

---

## Third finding: the product has quietly stopped delivering, and the UI hides it

Extraction is what stamps `postings.in_scope`. No extraction means no new posting can ever reach the
dashboard, the digest, or `/demo`, because every one of those surfaces floors on `in_scope IS TRUE`
(D-041/D-043).

Layer 1 is healthy throughout — ~500 new rows/day, fetch failures steady at ~3/run and all of the
known fail-closed classes (Airbus/Thales 2,000-cap, NextEra count drift). The break is entirely at
Layer 2.

**New roles mailed per day**, summed across all 36 recipients:

| Date (UTC) | new roles | closures |
|---|---:|---:|
| Aug 12 | 106 | 4,845 |
| Aug 15 | 250 | 3,838 |
| Aug 17 | 29 | 3,333 |
| Aug 18 | 85 | 4,734 |
| Aug 19 | 21 | 4,544 |
| Aug 20 | 16 | 4,945 |
| **Aug 21** | **3** | **5,641** |

Thirty-six people received a digest yesterday. Between all of them it carried **three** new roles and
about 157 closures each. The digest still sends, still renders, still reports success — it has simply
had almost nothing to say for three days. **A digest that fails to send is an alert (D-037); a digest
that sends nothing is not**, and that gap is exactly where this sat.

**The dashboard is draining.** 436 displayable rows right now. Nine of them were first seen in the
last four days. Eighty-three will fall out of the 21-day age floor (D-109) within the next week, with
essentially nothing replacing them.

**And the board still looks fresh, which is the part worth flagging.** `/demo` today shows rows
stamped `2026-08-21` at the top of Trading & Markets. Those are not new roles. The activity column
keys on `COALESCE(source_updated_at, first_seen_at)`, so an old posting whose ATS re-dates it
returns to the top looking new — and a *reopened* posting (D-053) resets `first_seen_at` while
keeping an `extracted_at` from weeks ago, so it sails past the `in_scope` floor without any
extraction. The freshness signal is doing exactly what it was designed to do, and the effect is that
a four-day ingestion outage is invisible on the page. This is the same presentation issue 1.2's
ledger already carries as "the dashboard's newest-first ordering keys on the ATS date"; the outage
makes it consequential rather than cosmetic.

---

## Fourth finding: we re-read the whole rejected corpus six times a day

`db.postings.postings_needing_extraction` selects every open, unextracted posting for a vertical —
**including `raw_payload`** — and `extract.run_extraction` then applies the free Stage-A title gate
in Python.

That means each run pulls the full JSON payload of every posting that has already been rejected by
the title gate, every time, in order to reject it again:

| Vertical | unextracted open rows | payload |
|---|---:|---:|
| robotics_software | 2,707 | 17 MB |
| aviation_software | 6,391 | 8.4 MB |
| grid_power_software | 5,119 | 8.3 MB |
| trading_software | 1,676 | 7.0 MB |

~41 MB per full pass × 6 passes/day ≈ **250 MB/day of Neon reads to re-derive a decision on a
column we already have.** Of those 15,893 rows, **10,682 are already past the 21-day age floor** and
can never be displayed even if they were extracted.

This one is **pre-existing and unrelated to the outage** — the outage inflates it, but the shape was
always there. It is not on fire (Neon bills compute, and the queries are indexed), which is why it
belongs below the first three. The fix is small: select `title` for the gate and fetch `raw_payload`
only for survivors, or push the age floor into the query.

---

## Where the money actually goes (steady state)

Stripping the outage out, monthly run-rate is roughly:

| Line | August MTD | Steady-state note |
|---|---:|---|
| Anthropic — extraction (Haiku 4.5) | $35.65 | ~$0.90/weekday healthy ⇒ **~$20/mo** |
| OpenAI — matching (GPT-5.6 Luna, low) | $5.56 | ~$0.25/day ⇒ **~$6/mo** |
| GCP — Cloud Run | $16.81 (forecast $24.62) | +633% vs July |
| **Total** | **~$58 MTD** | **~$50/mo healthy** |

Two things in that table are worth noticing.

**Extraction costs 3–4× what matching costs**, which inverts the intuition the architecture was built
on. Matching is the expensive model and it is cheap here, because two gates stand in front of it and
`VJA_PIPELINE_MAX_MATCHES` caps it at 400/run. Extraction is the cheap model and it dominates,
because it runs on every new posting that clears a *title* check — ~500/day — with no cap at all.
If LLM spend ever needs to come down, extraction is the lever, and the age floor is the obvious
first cut: extracting a posting that is already too old to display is pure waste (D-109 applied this
reasoning to matching and never to extraction).

**GCP's +633% is expected and was bought deliberately.** D-103 moved the pipeline from once-daily to
every four hours — 6× the executions — and D-101 put the API service on `--no-cpu-throttling`. The
forecast is $24.62/month. That is the intraday-freshness feature being paid for, not a regression.

Neon is not included; its billing lives outside GCP and was not checked this session.

---

## Smaller things found along the way

- **`pipeline_runs` cannot tell you how long a run took.** `finished_at` equals `started_at` to the
  microsecond on all 84 runs — the same `now` is passed to `start_run` and `finish_run`. Harmless
  today (the D-103 skip guard keys on `started_at`, which is correct), but it means we have no
  duration data at all, and the alert-window margins below cannot be checked against real run times.
- **Every run's status is `partial`, never `success`** — 84 of 84. With ~3 fetch failures per run
  from known fail-closed classes, `partial` is the permanent steady state, so the status field
  carries no signal and nothing can alert on it.
- **The GCP budget alert still does not exist.** `billingbudgets.googleapis.com` is not enabled on
  `role-feed-prod`. This has been on the carried-forward ledger since 1.1. It is also the one control
  that would have caught this outage from the cost side.
- **Alert-window margins are thin**, re-confirming the 08-06 entry: `vja-nightly` has 16 minutes of
  slack on a 5h window, `vja-digest` 2h on 26h. Both need delete-then-recreate to change (`alerts.sh`
  is idempotent by `displayName` and silently no-ops an edit).
- **`/demo`'s anti-leak guarantee holds.** Viewed while signed in, the match column still renders
  per-row "sign in" rather than verdicts — the structural guard (D-105) is doing its job.
- **Local `.env` has `VJA_DAILY_LLM_BUDGET_USD=7.5`; prod has no such env var set**, so the API
  service falls back to the code default. Worth reconciling against the "$25 in prod" claim in
  INVARIANTS — the value is asserted by `ship.sh`, and the deployed Job config does not show it.

---

## Ranked: what is worth doing

1. **Stop the burn.** Nothing bounds a failing extraction loop. Whatever the root-cause fix turns out
   to be, extraction needs a circuit breaker — N consecutive validation failures in a run aborts the
   stage — so that a broken Layer 2 costs one run's worth of calls, not four days'.
2. **Fix extraction.** Reproduce against the live API, then either pin the structured-output path
   explicitly or coerce at the boundary. A regression test on the observed payload shape
   (`'["a","b"]'` as `str`, `'null'` as `str`) comes first, per D-021.
3. **Close the metering hole.** Count tokens and cost on the failure path too. This is small, and it
   is what turns the next occurrence into a Tuesday rather than a week.
4. **Alert on silence, not just on failure.** A run that extracts nothing while the backlog is
   non-empty, or a digest that carries zero new roles across every recipient, should page. Both were
   true for three days and neither was an alert.
5. **Enable the GCP budget alert**, and add an Anthropic credit-balance check. The $5.58 balance is
   its own incident in waiting.
6. **Apply the age floor to extraction** (D-109's argument, extended): don't extract what can never
   be displayed. Cuts steady-state extraction spend and shrinks the backlog scan.
7. **Stop loading `raw_payload` for Stage-A-rejected rows** (finding 4).
8. **Record run duration** — pass a fresh `now` to `finish_run`.

## Candidate ADRs

- Extraction circuit breaker + the bounded-retry policy for a systematically failing Layer 2.
- Metering on the failure path (amends the D-035/D-069 metering rule, which currently reads as
  complete and is not).
- Age floor applied to `postings_needing_extraction` (extends D-109 from display/match to extract).
- Silence-based alerting as a first-class signal alongside failure-based (extends D-037/D-101).

## What this audit did not cover

Neon's own bill; Resend volume and deliverability; whether the 5,600 daily closure entries are real
or the Workday page-membership churn D-085 diagnosed; and the D-111 manual quality sample, which is
still owed and still needs prod data.
