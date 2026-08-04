# Update 1.2 — plan of record

*Written 2026-08-03, the day after Update 1.1 closed. Three PRs, planned together and built one at a
time. This is a **plan**, not a release record: when the work lands it gets `docs/updates/1.2.md`
(the grouping, the measured before/after, the carried-forward ledger), and any re-litigable call
here becomes an ADR in `DECISIONS.md`. Live rules go to `docs/INVARIANTS.md` in the same session
that changes them.*

**Status: PR 1 built (`feat/paste-resume`, D-107). PRs 2 and 3 planned.** The update itself opened at
#120 and its record is `docs/updates/1.2.md`.

---

## Why these three

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
(API + SPA form / query floor / LLM prompt + schema). That is why three PRs rather than one.

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

- **One home for the rule.** A `vja.dates` helper (bottom layer, zero LLM, the `activity_window_clause`
  neighbourhood) owns the cutoff so no caller open-codes `21`. The bound is `COALESCE(source_updated_at,
  first_seen_at) >= now - MAX_POSTING_AGE_DAYS` — the same freshness expression the recency windows
  already use, so a board that genuinely re-dates a role keeps it alive, which is the correct answer.
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

### The problem

The current write-up answers "should I apply?". A user reading `gaps: ["no Kubernetes experience"]`
learns something they already knew and can do nothing with. The product's real leverage is that it
has **read the posting and read your résumé** — so it can say which of your existing bullets to
lead with, which words the posting uses that your résumé does not, and what the application should
address head-on. That is advice; the rest is commentary.

### Scope

**Schema (migration).** `matches` gains two nullable columns:

| Column | Type | Holds |
|---|---|---|
| `resume_actions` | `Text` (JSON list) | Concrete edits for *this* application: bullets to lead with, real experience to surface, posting vocabulary the résumé is missing. |
| `application_notes` | `Text` (JSON list) | What to address in the application itself: how to frame a gap, what the cover letter or screening answer should say. |

Nullable because **old rows stay as they are** — matching is idempotent per
`(posting, profile, resume_version)`, so a prompt change never recomputes an existing judgment. The
dashboard will show a mix of old-style and new-style write-ups for a while; new rows fill in
forward, exactly as `postings.description` did in D-095. **This is a manual Neon migration**
(export `VJA_DATABASE_URL` → `alembic current` → `upgrade head` → `current`) run *before* the PR
merges, per D-068/D-083.

**The prompt.** `_SYSTEM_PROMPT` and `MatchResult` gain the two fields with tight instructions:
every action must be grounded in something the résumé actually contains or the posting actually
says; never invent experience; never advise the user to claim a skill they lack — the correct
advice for a real gap is how to *address* it, not how to hide it. `fits` / `gaps` / `verdict` /
`score` keep their current meaning; this adds a layer, it does not repurpose one. The honesty rules
in the current prompt (say no when warranted, D-007) are load-bearing and stay untouched.

**The posting body reaches the model — and this is the substantive change.** `_posting_text`
currently sends title, level, location, remote, work-auth, stack and comp. It does **not** send the
description. Advice of the form "the posting names Kafka twice and your résumé never says it" is
impossible without the body. `postings.description` has existed since D-095 and is filled forward
(no backfill), so:

- Include the description when present, **truncated** to a bounded character budget.
- The cached prefix (résumé + instructions) is unchanged, so this adds volatile input tokens to
  every match call — roughly 750 tokens for a ~3 KB body. **Measure the real per-match cost
  before and after** on a small live sample and record it; if it is material, tighten the
  truncation rather than dropping the feature, because the feature is the point.
- Rows without a stored description still match, just without body-grounded actions. Do not
  backfill 12k descriptions to enable this.

**Render surfaces.**

- `PostingPanel` gains an actions block, placed **above** fits/gaps: the actionable part is what the
  user opened the panel for, and fits/gaps is now the supporting argument. Absent fields render
  nothing at all (same discipline as the description block).
- `PostingRow` gains the two fields. **`PublicPostingRow` must NOT declare them** — the D-105
  anti-leak guarantee is structural precisely because the public model does not *have* the
  match-derived fields, and adding them there would silently convert a structural guarantee into a
  filtering one.
- The **digest body currently carries only `rationale`**, not fits/gaps. Add **one** line: the
  single highest-value résumé action. A digest is a scannable list, not a coaching session — the
  full advice lives one click away in the panel, behind the dashboard link every digest now carries
  (D-102). No em dashes (D-099).

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

### Definition of Done

Green full gate; the migration written, run against Neon, and confirmed with `alembic current`
before merge; API tests pinning the new fields on `PostingRow` **and** their absence from
`PublicPostingRow`; panel tests for present/absent/partial; digest render + no-em-dash test; the
manual sample reviewed and signed off; an ADR in `DECISIONS.md`; INVARIANTS' *Matching & extraction*
section updated (the "every rationale must state fits, gaps, and a verdict" line becomes fits, gaps,
verdict **and actions**).

### Risk

**Low to medium, and the honest risk is cost, not quality.** Every match call gains the truncated
description as volatile (uncached) input — roughly 750 tokens for a ~3 KB body, on top of a cached
résumé prefix that does not change. That is the one item in 1.2 that pushes spend *up*; PR 2 pushes
it down, which is most of why they are sequenced that way. It is measurable in a single run, and if
it is material the answer is a tighter truncation budget, not dropping the feature.

The quality risk is real but thinner than it first looks: the prompt's existing honesty rules
(ground everything in the inputs, never invent experience, say no when warranted — D-007) already
carry that weight, and the new fields inherit them rather than competing with them. The manual
sample review is the check, and it is a check on whether the advice is *useful*, not on whether it
is safe.

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

**PR 2 is gated on network access to Neon** for the sizing query. If that is unavailable when its
turn comes, build PR 3 first rather than guessing a threshold — the order exists to optimize cost,
not to enforce a dependency, and a wrong constant is more expensive than a wrong sequence.

Each PR branches from `main` at its own start. Note the standing tax: all three touch `WORKLOG.md`,
so a branch cut early and merged late will conflict on exactly that one hunk. Resolve by hand,
newest-on-top.

## Open questions

- **Is 21 days right?** Open, and deliberately so — it is a guess until the Neon sizing query runs.
  `VJA_MAX_POSTING_AGE_DAYS` makes it cheap to change afterwards, but the *initial* value should
  come from the distribution, not from the number in this document's title.
- **How much does the description cost per match, really?** Measured in PR 3, not estimated here.
- **Should the age cap eventually inform employer health?** A company whose postings routinely age
  past 21 days without re-dating may simply not delist. That is lifespan/urgency intel (D-087 F4),
  parked, and this update deliberately does not start it.

## Not in this update

Not because they are unimportant — because they are not these three. Carried from 1.1's ledger:
the Cloudflare orange-cloud check, the deployed `robots.txt`, Google OAuth publishing status, the
GCP budget alert, the August billing check, the digest `new`-window hole, dead apply links on
`/demo`, `.cell-location` truncation, and `alerts.sh` being unable to express an edit.
