# Update 1.2 — plan of record

*Written 2026-08-03, the day after Update 1.1 closed. Three PRs, planned together and built one at
a time; a fourth was added on 2026-08-05 from production evidence. This is a **plan**, not a
release record: when the work lands it gets `docs/updates/1.2.md`
(the grouping, the measured before/after, the carried-forward ledger), and any re-litigable call
here becomes an ADR in `DECISIONS.md`. Live rules go to `docs/INVARIANTS.md` in the same session
that changes them.*

**Status: PR 1 merged (#121, D-107). PR 2 merged (#123, D-109). PR 4 merged (#124, D-110). PR 3 is
the last one open** — its scope was settled in conversation on 2026-08-06 and this document was
rewritten to match before any code was written. The update itself opened at #120 and its record is
`docs/updates/1.2.md`.

---

## Why these

Update 1.1 was the **funnel** update: 5,000 launch views produced 10 résumé uploads, so almost
nobody reached a job. It opened the door — `/demo`, self-serve vertical switching, a landing page
that reads well.

1.2 is the **other half of that problem**: what happens to the people who *do* walk through. Each
item removes a reason a real user gives up.

| # | Item | The friction it removes |
|---|---|---|
| 1 | Paste résumé text | The upload wall. A user with a Google Doc résumé, a LinkedIn profile, or a phone has to find and export a file before they can see a single job. |
| 2 | Hard 3-week age cap | Ghost jobs. A board that never delists shows a role open for three months; applying to it wastes the user's afternoon and costs us their trust. |
| 3 | Advice the user can act on | The write-up currently argues *whether* you fit. A job seeker already suspects whether they fit — what they cannot get anywhere else is *what to change before applying*. |

They are independent: any one can ship without the others, and they touch three different layers
(API + SPA form / query floor / LLM prompt + schema). That is why separate PRs rather than one.
**PR 4 below was not part of this reasoning** — it was added mid-update from production evidence,
and it is a defect rather than a friction.

**Plus one item that is not a PR-sized feature: a cadence copy sweep.** D-103 split the pipeline to
every 4 hours and left the digest daily, but the SPA copy was never swept — six strings still said
"nightly". Folded in as `fix/cadence-copy` because it is six lines and shipping it inside a feature
PR would bury it. The distinction the sweep has to keep straight is that **the pipeline is 4-hourly
and the email is daily**, so "updates every 4 hours" is right for the dashboard and tour while
"a digest each morning" is right for the inbox copy in Settings and Login.

---

## PR 1 — Paste résumé text

**Branch:** `feat/paste-resume`

### Scope

`POST /api/profiles` today requires a `file` part. It gains an alternative: the caller may send
**either** a file **or** a `resume_text` form field, and exactly one of the two.

- **Backend.** `file` and `resume_text` both become optional `Form`/`File` params; neither ⇒ 422,
  both ⇒ 422 (a caller that sends both has a bug, and silently picking one hides it). Pasted text
  runs the same length/emptiness guards `vja.resume` already enforces, so the rules stay in one
  place: `extract_resume_text` grows a sibling entry point (`clean_resume_text`) for the
  already-text case rather than the API re-implementing the caps.
- **Everything downstream is unchanged.** This is exactly the seam D-033 exists for: the input
  format is an upload-boundary concern and `profiles.resume_text` is what the pipeline reads.
  No schema change, no migration, no matching change, no digest change.
- **The existing guards all still apply** and must be re-pinned for the paste path: the D-085
  identical-content no-op, the rolling 24h changed-résumé limit, the D-057 daily ceiling, the
  D-104 second-vertical 409.
- **Frontend.** `Upload.tsx` gets a two-mode control — *Upload a file* / *Paste text* — over the
  existing `.segmented` control (already used by the feedback category picker and the dashboard
  toggles; no new component vocabulary). Paste mode renders a textarea with a live character
  count against the 200,000-char cap. Submit is disabled until the active mode has content. Both
  modes share one submit path and one error surface.

### Deliberately out of scope

- **PDF-by-paste heuristics.** Text pasted out of a PDF viewer arrives with broken line wrapping.
  We do not try to repair it — the model reads it fine, and a "helpful" reflow would corrupt real
  résumés to fix a cosmetic problem.
- **LinkedIn import.** A different project (auth, scraping, ToS) and not this PR.
- **Saving a draft.** The textarea is not persisted between visits.

### Definition of Done

Green `pytest` + ruff/format/mypy + import-linter + eslint/tsc/vitest; API tests covering
either/neither/both and each guard on the paste path; `Upload.test.tsx` covering the mode toggle,
the disabled-submit rule, and that the 202 commit-point behavior (D-082) is identical in both
modes; human-read diff; docs updated.

### Risk

Low. The one real hazard is **weakening a guard by accident** — the reupload limiter and the
identical-content no-op key on the extracted text, so they should be untouched by construction.
The tests exist to prove that, not to hope it.

---

## PR 2 — A posting older than 3 weeks stops being shown

**Branch:** `feat/posting-age-cap`

### The decision, stated plainly

**A display floor, not a status change.** Postings whose freshness date is older than 21 days are
excluded from the dashboard, from `/demo`, from the digest, and from the match candidate set. The
`postings` row itself is **never touched**: `status` stays `open`, nothing is deleted, and the
lifespan statistics the project has been accumulating since Phase 1 stay honest.

**Why not actually close them.** Age-closing fights the diff and loses. `close_posting` sets
`status='closed'`; on the next 4-hourly run the ATS still lists the job, so `diff` reports it as
`new`, `sync_employer` finds it in `closed_index` and routes it to `reopen_posting` — which
**resets `first_seen_at` and re-enters it in the `new` set** (D-053). The role would resurface as
brand new every four hours, and the digest would mail it out again. The diff is the product
(D-009); a policy that makes the diff lie about what changed is the wrong tool.

### Scope

- **One home for the rule.** A helper owns the cutoff so no caller open-codes `21`. The bound is
  `COALESCE(source_updated_at, first_seen_at) >= now - MAX_POSTING_AGE_DAYS` — the same freshness
  expression the recency windows already use, so a board that genuinely re-dates a role keeps it
  alive, which is the correct answer. *(**Built as `db.postings.age_floor_clause`, not in
  `vja.dates` as this plan first said**: the clause needs the `postings` table, so it belongs in the
  db layer next to `activity_window_clause`, and it is literally expressed as one more call to it.
  `vja.dates` normalizes ATS date *strings* and knows nothing about tables.)*
- **Applied in four places:**
  1. `dashboard_statement` — both the matched and cleaned views, and therefore `/demo` too (it
     shares the statement, which is the point of D-105's structural split).
  2. `postings_needing_match` — **the cost win.** Matching a posting we will never display is pure
     waste; this is the first change in the project that reduces LLM spend by not asking a question.
  3. The digest's new-roles set — belt and braces. In practice the digest window (`last_sent_at`)
     already keeps 3-week-old roles out, but a paused-then-resumed user (D-094) accumulates a wide
     window and would otherwise receive them.
  4. The public `/api/public/*` count endpoint, so the demo picker's per-vertical counts match the
     table the user then sees. A toggle that opens onto fewer rows than it advertised is a bug.
- **Configurable, not hardcoded.** `VJA_MAX_POSTING_AGE_DAYS`, default 21, read at call time. If 3
  weeks turns out to be wrong for a slow-moving vertical it is an env change, not a deploy.
- **The closure path is untouched.** A posting that genuinely vanishes from the ATS still closes
  the normal way and still appears in the digest's closures rollup (D-056).

### Measure before, and after — and this one is a **blocker**, not a nicety

**21 days is a guess and the plan must not treat it as a decision.** The freshness key is
`COALESCE(source_updated_at, first_seen_at)`, and `source_updated_at` is *the ATS's own posted
date* — which is exactly why 2023 rows sit at the bottom of the dashboard, and exactly what makes
the threshold risky. Many boards stamp the original posted date and never touch it again, so a
genuinely active req first posted six weeks ago carries a six-week-old date and a 21-day floor
would hide it along with the ghosts.

**The dev corpus cannot answer this.** `data/vja.db` is frozen at 2026-06-30 (newest `first_seen_at`),
so *every* row in it reads as months old — a survey there returns 100% stale and means nothing. The
sizing query must run against Neon, read-only, and is the first step of the PR:

- Open in-scope rows per vertical, and the share older than 21 / 30 / 60 / 90 days by the
  freshness key.
- The same split by `first_seen_at` alone, to separate "the board says it is old" from "we have
  genuinely been tracking it a long time".
- How many stale rows already carry a match (money already spent) versus pending (money saved).
- The oldest dozen rows with both dates, eyeballed — the 2023 tail should be obvious and its shape
  tells us whether the cutoff wants to be 21 days or 60.

Then pick the constant from the distribution. Killing the 2023 rows is the actual complaint and a
conservative cutoff does that; if the tail turns out to be thin, the aggressive cutoff is free. If
the two answers disagree, ship the conservative one — a hidden live role is a worse failure than a
visible stale one, because the user never learns what they did not see.

### Deliberately out of scope

- **Telling the user a role was hidden for age.** No "expired" badge, no tombstone. The product
  shows what changed; a role that quietly stops appearing is the same experience as one that closed.
- **Re-verifying old apply links.** D-008 verifies pre-digest only, and dead links going public on
  `/demo` is already a named, unfixed item from 1.1. The age cap will *incidentally* reduce that
  exposure — dead links skew old — but it is not the fix and must not be described as one.

### Definition of Done

Green full gate; DB tests pinning the cutoff on both dialects (the boundary matters: exactly 21
days old is in, 21 days + 1 second is out); a test proving the public statement carries the same
floor as the authed one; the before/after numbers captured; human-read diff; INVARIANTS updated
(the *Dashboard & freshness* section gains the floor; the D-039 "date-uncapped nightly" line is
now qualified and must be edited, not appended to).

### Risk

Medium, and it is entirely a **product** risk rather than a technical one: the mechanism is four
`WHERE` clauses, and the whole question is what number goes in them. Mitigated by the env knob and
by making the sizing query a blocking first step rather than a post-merge check.

---

## PR 3 — Advice a user can act on

**Branch:** `feat/actionable-match-advice`

> **Scope settled 2026-08-06, in conversation, before any code.** The section below is the agreed
> version; five decisions moved from what was first written here, and each is marked **[decided]**
> where it lands. The framing that drove them: *we are mainly reallocating a few bullets of fits and
> gaps into actionable résumé updates* — not bolting a coaching product onto the side of a matcher.

### The problem

The current write-up answers "should I apply?". A user reading `gaps: ["no Kubernetes experience"]`
learns something they already knew and can do nothing with. The product's real leverage is that it
has **read the posting and read your résumé** — so it can say which of your existing bullets to
lead with, which words the posting uses that your résumé does not, and what the application should
address head-on. That is advice; the rest is commentary.

**And the write-up is longer than its content.** Read against real rows: a `maybe · 42` carries 6
fits and 7 gaps, and its rationale paragraph is a four-sentence recap of the bullets directly
beneath it. Worse, the same *profile-constant* bullets recur on nearly every posting — "expected
graduation May 2027", "candidate is in Madison, WI; role is onsite in X, relocation required",
"early-career level aligns with candidate's student/intern status". True, restated every time,
wallpaper by the third role, and paid for in output tokens on every match.

**The one job the paragraph does that the lists cannot: weighting.** Two lists of equal-looking
bullets cannot say *which* gap was disqualifying. "The stack gap is a real risk" is why the score is
42 and not 65. That sentence stays; the recap around it goes.

### Scope

**Schema (migration).** `matches` gains two nullable columns:

| Column | Type | Holds |
|---|---|---|
| `resume_actions` | `Text` (JSON list) | Edits to the document, for things you **have** but present badly: bullets to lead with, real experience buried under "projects", posting vocabulary your résumé words differently. |
| `application_notes` | `Text` (JSON list) | What to say about things you **don't** have: how to frame a real gap, what the cover letter or screening answer should address head-on. |

**Two fields, not one, and the reason is structural rather than tidiness** *(considered and kept)*.
They split on *what act they license*: `resume_actions` is definitionally about content already in
the résumé, `application_notes` definitionally about content that is not. Blended into one list the
model has no boundary to respect, and the failure mode is *"add valuation to your skills section"* —
advice to lie, with our name on it. The schema makes that hard to say by accident; a prompt rule
alone only asks nicely.

Nullable because **old rows stay as they are** — matching is idempotent per
`(posting, profile, resume_version)`, so a prompt change never recomputes an existing judgment. The
dashboard will show a mix of old-style and new-style write-ups for a while; new rows fill in
forward, exactly as `postings.description` did in D-095. **This is a manual Neon migration**
(export `VJA_DATABASE_URL` → `alembic current` → `upgrade head` → `current`) run *before* the PR
merges, per D-068/D-083.

**The prompt** — five changes, and four of them are subtractive.

1. **[decided] Second person throughout** — rationale, fits, gaps, and both new fields. Today's
   output is written *about* the reader ("The candidate has a solid early-career foundation"),
   a leftover from the prompt's "one candidate, one posting" framing. It reads as a dossier on you
   rather than advice to you. It also makes dishonest advice harder to write: *"you should claim
   Spring Boot"* is more obviously wrong than *"the candidate should list Spring Boot"*.
2. **[decided] `fits` and `gaps` cap at 3 each**, and may not restate profile-constant facts
   (graduation date, home location vs role location, "early-career level aligns"). This is the
   reallocation: the bullets that go are the repeated ones, and the space they free is the advice.
3. **[decided] `rationale` stays 1-2 sentences and loses only its verdict-restating tail.** The
   closing clause of most lines today — *"Overall this is a plausible but not highly direct match"* —
   sits beside a rendered `[maybe · 56]` tag and carries nothing. Name what dominated, then stop.
   Note the constraint that forces this to be conservative: **`rationale` is a single column**
   rendered in both the panel and the digest body, so it cannot be short in one and full in the
   other without a second column, which is not worth it. Cutting fits/gaps to 3 each is what
   actually resolves the paragraph's redundancy — at 6 bullets instead of 13 it stops being a recap.
4. **[decided] Advice is written for every verdict, including `no`** — and "nothing you change makes
   this fit; this is a domain mismatch" is a **valid, complete answer**. The earlier proposal to
   suppress advice on `no` was wrong on cost and dangerous on quality: the reasoning tokens are
   spent before the verdict exists, so suppression saves only the list's own output tokens, and a
   `no` row is visible in the Cleaned view where a blank block reads as broken. The real risk is the
   opposite one — a model asked for three bullets against a hopeless match will manufacture bridging
   advice ("highlight your analytical coursework to position for the transition"), which is the
   exact fabrication these fields exist to prevent. Permitting emptiness is the guard.
5. Grounding, unchanged in spirit and now load-bearing for two more fields: every action must be
   grounded in something the résumé actually contains or the posting actually says; never invent
   experience; **never advise claiming a skill the résumé does not evidence** — the correct advice
   for a real gap is how to *address* it, not how to hide it. `verdict` / `score` keep their current
   meaning and the D-007 honesty rules (say no when warranted) stay untouched.

**The posting body reaches the model — and this is the substantive change.** `_posting_text`
currently sends title, level, location, remote, work-auth, stack and comp. It does **not** send the
description. Advice of the form "the posting names Kafka twice and your résumé never says it" is
impossible without the body. `postings.description` has existed since D-095 and is filled forward
(no backfill), so:

- Include the description when present, **head-truncated at ~4,000 characters** (~1,000 tokens),
  a module constant with an env override so tightening it after the cost measurement is a config
  change rather than a deploy (the `VJA_MAX_POSTING_AGE_DAYS` pattern). **[decided]** Head, not
  tail: bodies average ~3 KB so the cap clips only the long ones, and what it clips is the boilerplate
  tail (EEO statements, benefits, legal) while responsibilities and the posting's own vocabulary are
  front-loaded. **No boilerplate stripping** — heuristic cleanup is a second feature with its own
  failure modes.
- The cached prefix (résumé + instructions) is unchanged, so this adds volatile input tokens to
  every match call. **Measure the real per-match cost before and after** on a small live sample and
  record it; if it is material, tighten the truncation rather than dropping the feature, because the
  feature is the point.
- Rows without a stored description still match, just without body-grounded actions. Do not
  backfill 12k descriptions to enable this.

**How many rows actually have a body, and why this is not a blocking query.** `description` fills at
insert, on a content change, on reopen, or at extraction, and shipped 2026-07-24 with no backfill —
so rows that entered before that date and have not changed since carry a NULL. Two things bound
that to a tail: a row is only displayable if its activity date is inside 21 days (D-109), and
in-scope rows pick up a body at extraction from the detail the list-only fetchers already fetch.
What remains is a posting that entered before 2026-07-24 and has been **re-dated without its body
changing** — `update_changed` only writes the description when content actually moved. **The manual
quality sample is the measurement**: bodyless rows are self-evident in the output, so this costs
nothing and needs no separate read-only Neon pass.

**Render surfaces.**

- `PostingPanel` order is **verdict line → what to change → application notes → fits/gaps**
  **[decided]**: the actionable part is what the user opened the panel for, and fits/gaps is now the
  supporting argument. Absent or empty fields render nothing at all (same discipline as the
  description block).
- `PostingRow` gains the two fields. **`PublicPostingRow` must NOT declare them** — the D-105
  anti-leak guarantee is structural precisely because the public model does not *have* the
  match-derived fields, and adding them there would silently convert a structural guarantee into a
  filtering one.
- **[decided — this reverses what this plan first said] The digest body is structurally unchanged:
  summary only, no action line.** The original plan added the single highest-value résumé action to
  each digest row. Dropped on the reasoning that the inbox is a **triage** surface — you are deciding
  whether to click — while advice is **execution** and needs the panel's full context to be usable.
  The email keeps carrying `rationale` and nothing else, so it inherits the shortening in point 3
  above and changes in no other way. No em dashes (D-099).

### Verification, and why the gate is different here

Per D-020 as amended by D-090/D-093, model and prompt changes are **not** merge-gated by live evals.
The deterministic half (schema, serialization, render, the public-model omission) is a hard gate and
is tested normally. The quality half is **Hayden's explicit signoff** on a small representative
sample run manually against real postings and a real résumé, with the outputs preserved. Concretely,
before merge: a handful of postings spanning strong_yes → no, read end to end, checking that the
actions are grounded, specific, and would actually change what the user submits.

### Deliberately out of scope

- **Rewriting the résumé for the user.** We give actions; we do not generate a document. That is a
  different product with a different liability profile.
- **A cover-letter generator.** Same reason, and it invites exactly the fabrication the prompt is
  built to prevent.
- **Re-matching existing rows.** Decided: leave them. If reading the mixed output turns out to be
  jarring, backfilling one profile (Hayden's) is a cheap follow-up in 1.3 — not a reason to spend
  on a corpus-wide re-match now.
- **Backfilling `postings.description`.** Prospective only, per D-095. Rows without a body still
  match; their advice is just not vocabulary-grounded.

### The mixed-voice window, and why it needs no backfill

Matching is idempotent per `(posting, profile, resume_version)`, so no existing row is rewritten:
third-person write-ups will sit beside second-person ones. **D-109 bounds this better than it
looks** — a posting stops being displayed once its activity date passes 21 days, so the *visible*
corpus turns over on its own inside about three weeks. The exception is a long-lived posting a board
keeps re-dating, which stays visible carrying its original third-person match indefinitely. Thin
tail, named here so it is recognized as expected rather than as a bug.

### Definition of Done

Green full gate; the migration written, run against Neon, and confirmed with `alembic current`
before merge; API tests pinning the new fields on `PostingRow` **and** their absence from
`PublicPostingRow`; panel tests for present/absent/partial/empty-list; a prompt-level test that the
description reaches `_posting_text` truncated and that a bodyless candidate still matches; digest
render test proving the body is **structurally unchanged** plus the standing no-em-dash test; the
manual sample reviewed and signed off; an ADR in `DECISIONS.md`; INVARIANTS' *Matching & extraction*
section updated (the "every rationale must state fits, gaps, and a verdict" line becomes fits, gaps,
verdict **and actions**, and gains the second-person + 3-bullet rules).

### Risk

**Low to medium, and the honest risk is cost, not quality.** Every match call gains the truncated
description as volatile (uncached) input, on top of a cached résumé prefix that does not change.

**Correction to this plan's own sequencing argument:** it claimed PR 2 pre-paid for that increase by
shrinking the candidate set. That is now known to be wrong — the D-109 measurement found all 358
age-floored rows **already carried a match**, so the age floor saved **$0 on the existing corpus**
and only saves forward, per new `(profile, resume_version)`. The offset is real but smaller and
later than the sequencing claimed.

What genuinely offsets it is inside this PR: capping fits/gaps at 3 and dropping the rationale's
recap cut **output** tokens on every match, and output is the expensive side. Net may land near
flat. It is measurable in a single run, and if it is material the answer is a tighter truncation
budget, not dropping the feature.

The quality risk is real but thinner than it first looks: the prompt's existing honesty rules
(ground everything in the inputs, never invent experience, say no when warranted — D-007) already
carry that weight, and the new fields inherit them rather than competing with them. The sharpest
remaining edge is manufactured bridging advice on a hopeless match, which permitting an empty
advice list is specifically there to prevent. The manual sample review is the check, and it is a
check on whether the advice is *useful*, not on whether it is safe.

---

## PR 4 — A throttled apply-link check must not read as a dead link

**Branch:** `fix/digest-quarantine` · **Added 2026-08-05, after the fact.** Not one of the planned
three: it is the residual D-108 named and 1.1 carried before it, promoted to its own PR once
production evidence showed it is the larger live loss.

> **Built 2026-08-06 as D-110, and this section's scope changed twice on the way.** Two corrections
> to what is written below, both from re-measuring rather than re-reading:
>
> 1. **There is a third failure class the write-up did not have: `BLOCKED`.** Coinbase, Akuna and
>    Tower Research return **403 to HEAD *and* GET, with our User-Agent and with none** — a WAF, not
>    a rate limit. No amount of retry or throttling would ever have fixed them; they are quarantined
>    every single day and always would have been. They now ship, on the reasoning that Layer 1
>    already evidences the posting (the ATS listed it within 4 hours) and a 403 describes our
>    access, not the job.
> 2. **Item 4 (re-admission) is dropped by decision, not deferred.** Hayden's call: those roles are
>    days old and re-mailing them is waste — fresh delivery is the product. The 564 stuck pairs stay
>    lost. This also keeps the change away from `_unreported_clause`, which is where the risk was.
>
> Items 1-3 shipped as described, plus a **300s retry budget** that was not in this plan: 462 URLs ×
> 7s of backoff would push the job past its 1h task timeout, and a timed-out digest sends nothing at
> all. See D-110.

### The evidence, not the theory

Measured against Neon on 2026-08-05, the morning after D-108 shipped (image `77e65a2`):

- **D-108 is holding.** Of 320 relevant (posting, recipient) pairs first seen in the last 5 days,
  291 mailed, 16 quarantined, 13 to recipients with no send yet, and **zero unexplained**.
- **Quarantine is now the whole of the loss.** Across every open in-scope relevant pair regardless
  of age: 2,909 mailed · **784 quarantined** · 197 to never-sent recipients · 19 unexplained (all
  matched in July against an August `last_send` — the pre-D-108 residue that 1.2 decided stays
  lost). Roughly **one in five** relevant roles never reaches the recipient it was matched for.
- **Most of it is a false positive.** Today's send quarantined 125 pairs behind 113 distinct URLs,
  **90 of them `*.greenhouse.io`**. Re-checking 12 of those URLs by hand, one at a time, 1.5s
  apart: **11 returned 200 and 1 returned 404**. The 404 (Aurora Energy Research) is D-008 working
  exactly as intended. The other 11 were never dead.

The worked case that prompted this: `haydenham10@gmail.com` / trading saw 16 roles at the top of
the dashboard and 4 in the digest. The 16 decompose as **3 shipped · 3 quarantined this morning ·
4 quarantined on 08-03 and permanently lost · 6 correctly omitted** (mailed on 08-03; they returned
to the top of the table only because SIG and Headlands re-stamped their ATS date on 08-04, and the
table orders on `COALESCE(source_updated_at, first_seen_at)`). So **7 of 16 were the defect** and 6
were correct behaviour with misleading presentation.

### The mechanism

`build_digest` runs once per (vertical, profile) and `_apply_verification_gate` re-verifies every
candidate URL with a fresh `httpx.Client` — no dedupe across recipients, no delay, no retry. Today
that was ~685 HEAD requests concentrated on two Greenhouse hosts inside a six-minute job.
`verify_apply_url` returns a bare `bool`, so **404, 429, 503 and a timeout are the same answer**,
and any of them fails closed. A forward-only send window (`last_sent_at` only moves) then makes one
transient answer permanent: the posting fails both halves of the D-108 predicate the next morning.

Fail-closed verification is correct and is not in question (D-008). What is wrong is that "we could
not tell" is being recorded as "it is dead", and that the cost of being wrong once is the role.

**Caveat kept deliberately:** the status code is not logged anywhere, so "throttled" is inference
from the burst shape plus the clean re-checks, not from an observed 429. Recording it is part of
the fix, and the first thing the fix makes measurable.

### Scope

1. **Verify once per URL per digest job, not once per recipient.** A verification cache threaded
   through the job; ~685 requests become ~400 on today's volume. Also fixes the duplicated work
   that makes the burst as sharp as it is.
2. **Throttle per host, and share one client.** Small per-host spacing plus connection pooling.
   This is also a standing repo rule currently being violated ("politeness is policy: rate limits,
   sane user agent, respect robots.txt" — getting IP-banned is a self-inflicted coverage hole).
3. **Three-way result instead of a bool.** *alive* → ship; *dead* (404/410) → quarantine exactly as
   today; *unknown* (429/5xx/transport) → retry with backoff, and log the status. An unknown must
   not consume the posting's only chance.
4. **Make quarantine survivable.** Read the recent `digests.contents` blobs for the recipient and
   re-admit any still-open posting quarantined recently. **No migration is required:** the blob
   already stores `external_id` *and* `company`, and `UNIQUE(vertical, name)` on `employers` plus
   `UNIQUE(employer_id, external_id)` on `postings` make `(vertical, company, external_id)` resolve
   to exactly one posting.

Items 1-3 stop new losses; item 4 recovers roles that already lost the coin flip, and is the only
one that would have saved the four Headlands/Jane Street roles above.

### Deliberately out of scope

- **Weakening D-008.** A posting whose link is genuinely dead still must not ship. The Aurora 404
  is the control case and must keep being quarantined.
- **Backfilling the 784 already-lost pairs.** 1.2 already decided this (`fresh delivery is the
  product`); item 4 changes the future, not the past.
- **Verifying links for the dashboard or `/demo`.** Dead public apply links remain a named,
  unfixed item carried from 1.1.

### Definition of Done

Green full gate; a regression test written first and confirmed red, pinning that an *unknown*
result does not permanently drop a posting while a *dead* one still does; a test that item 4 cannot
resurface something already mailed and that its lookback is bounded; the per-host throttle pinned
without real network calls; an ADR; INVARIANTS' *Digest & delivery* verification line updated in
the same session. No migration, so CD's code-only path suffices (as D-108's did).

### Risk

**Medium, and it is item 4 alone.** Items 1-3 are narrow and self-contained. Item 4 changes what
`new` means in the digest, which is exactly the surface D-108 just fixed and exactly where a naive
predicate mails people roles they have already read — the same trap the `trigger=nightly` gate was
added for. It needs the bound and the already-mailed guard, and its test comes before its code.

---

## Sequencing

**1 → 2 → 3.** Build in that order and merge each before starting the next.

- **PR 1 first** because it is the lowest-risk, touches no shared query, and is the only one a
  waiting user feels immediately.
- **PR 2 second** because it reduces the match candidate set, so PR 3's per-match cost increase
  lands on a smaller, better-chosen set. Doing them in the other order means measuring PR 3's cost
  against a candidate population we were about to shrink.
- **PR 3 last**, and it is the only one needing a manual Neon migration and a manual quality
  signoff. It should not be blocking anything else.

**PR 2's Neon gate is closed** — the sizing query ran on 2026-08-04 and 21 days is now an argued
constant rather than a guess (see *Open questions*).

**PR 4 slots after PR 2, ahead of PR 3** (decided 2026-08-05). The case for jumping it to the front
was real — it is a live defect losing about one in five matched roles, where PR 2 is an improvement
— but PR 2 was already part-built when the evidence landed, and finishing it costs less than
carrying two open branches. PR 3 goes last regardless: it is the only one needing a manual Neon
migration and a manual quality signoff.

Each PR branches from `main` at its own start. Note the standing tax: all of them touch
`WORKLOG.md`, so a branch cut early and merged late will conflict on exactly that one hunk. Resolve
by hand, newest-on-top.

## Open questions

- **Is 21 days right?** ~~Open~~ **Answered 2026-08-04, and 21 days chosen.** The Neon sizing query
  returned 897 open in-scope rows keyed on `COALESCE(source_updated_at, first_seen_at)`, with
  `source_updated_at` present on 877 of 897 (98%) — so the "board stamps the original date forever"
  hazard is real but not dominant. Bands: ≤7d **285** · 8-14d **188** · 15-21d **75** · 22-30d
  **80** · 31-60d **172** · 61-180d **72** · >180d **25**. A 21-day floor cuts **349 of 897 (39%)**,
  leaving 548. Hayden's call, taken against the alternatives on the table (30d = 269 cut, 60d = 97):
  39% is a large cut and it is the intended one, since the 31-60d and 61-180d bands are 244 rows of
  exactly the tail the complaint was about. `VJA_MAX_POSTING_AGE_DAYS` keeps it cheap to revise.
- **How much does the description cost per match, really?** Measured in PR 3, not estimated here.
- **Should the age cap eventually inform employer health?** A company whose postings routinely age
  past 21 days without re-dating may simply not delist. That is lifespan/urgency intel (D-087 F4),
  parked, and this update deliberately does not start it.

## Not in this update

Not because they are unimportant — because they are not these four. Carried from 1.1's ledger:
the Cloudflare orange-cloud check, the deployed `robots.txt`, Google OAuth publishing status, the
GCP budget alert, the August billing check, dead apply links on `/demo`, `.cell-location`
truncation, and `alerts.sh` being unable to express an edit. *(The digest `new`-window hole left
this list: it was observed in production and fixed as D-108.)*

One more, surfaced by the 2026-08-05 investigation and deliberately not scoped here: **the
dashboard's newest-first ordering keys on the ATS date, while the digest ships on our detection
date**, so a role a board re-stamps returns to the top of the table looking new when it was mailed
a week ago. Six of the sixteen roles in the worked case above were this, and it reads as a bug to
the user. It is a presentation question (a "we found this on" column, a distinct sort, or a
re-dated marker), it needs a design call rather than a fix, and PR 4's scope is the real loss.
