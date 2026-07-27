# Work Log

Append-only record of working sessions — a narrative backup to git history.
Newest entry on top. One entry per working session. Keep it terse: what changed, why, what's next.

---

## 2026-07-26 — D-098: UI motion — token set + app-wide transitions (#106) + landing scroll reveals

**Housekeeping on the previous entry:** D-097's "Next: Hayden reviews/commits/PRs" is **done** — trading
merged as **#105** (`fe4f6a2`) and `main` is clean. **Still open from it, and it is an ops step, not code:**
`main` auto-deploys and `/api/verticals` is config-driven, so the picker has been offering **Trading &
Markets** since that merge while Neon holds zero trading employers — export the Neon `VJA_DATABASE_URL` and
run `vja-import-employers data/seed/employers_seed.csv`. Also still open: the three Rippling activations
(`vja-review set-ats` → `approve` on `#103`/`#139`/`#141`) and D-095 PR 1's comp fill-rate re-run against Neon.

**Task:** usability/display polish. Session brief was a landing-page motion upgrade, then em-dash removal,
then back buttons on the non-dashboard pages.

**The audit inverted the brief, which is the interesting part.** The prompt described a Tailwind codebase to
de-sludge — strip `transition-all`, kill 300ms hovers, move `height`/`top` animations off the layout path.
**None of it existed.** `frontend/` is one hand-written `theme.css` with **five motion declarations in 1433
lines**: zero `transition-all`, zero layout-property animation, zero scroll listeners, zero
`IntersectionObserver`, zero `will-change`, and only 4 distinct durations (in two unit conventions) and 3
keyword easings. The clunk was the **absence** of motion: **30 hover/focus/checked/selected states defined,
exactly 2 transitioned**. The dashboard row was worst — hover background and the 3px verdict spine both
flipped at 0ms, so scanning the table strobed. Hayden rescoped off the audit.

**Scope decisions (Hayden, this session).** Transitions **app-wide, not landing-only** (`.btn`/`.card`/`a`
are shared, and the dashboard row needed it most) · em-dash removal covers **rendered frontend copy + the
digest email**, not code comments or docs · the three `—` **empty-value glyphs stay** (`PostingsTable:47`,
`PostingPanel:78`, `Verdict:20` — a typographic "no value" marker, not prose) · back buttons on **Settings
and Privacy, both pointing at `/`**, the smart root, which already routes a profiled user, an unprofiled
user, and a logged-out visitor correctly (D-065). Recorded as **D-098**.

**PR 1 — foundation (merged #106, `22918ad`), `theme.css` only, +96/−14.** The six motion tokens into
`:root`; **every** duration and curve in the file now resolves to one, including the three pre-existing
ones that disagreed (`120ms ease`, `0.15s ease`, `160ms ease-out`). Sixteen base rules gained explicit
property lists at `--dur-fast` — every property named is a colour, `transform` or `opacity`, so nothing
reflows mid-transition. First `:focus-visible` styling in the project's history (it appeared **zero** times;
every control fell back to a UA outline that is near-unreadable on `#08090c`), scoped to real interactive
elements so the two programmatically-focused dialog shells keep their deliberate `outline: none`. Global
`prefers-reduced-motion` block replacing one that had covered a single property on a single element.

**PR 2 — landing motion, this branch (`feat/landing-scroll-motion`, uncommitted).** Hero animates on load
with a 70ms stagger (last child lands at 210ms + 700ms); stats, pillars, how-it-works, verticals, founder
and footer reveal on scroll. **Three judgments that deviate from the obvious implementation, each for a
concrete failure it avoids.** (1) The reveal **never hides what it cannot un-hide**: the native
`animation-timeline: view()` path needs no JS, and the `IntersectionObserver` fallback sets its arming class
`js-reveal` on `<html>` *only after* confirming an observer exists — no JS, no observer, no support means
the page renders finished, not blank. (2) **`animation-range` ends on `entry`, not `cover`**: the brief's
`cover 35%` strands bottom-of-document blocks, because once scrolling stops a footer can never reach a cover
percentage and sits permanently half-faded; `entry 10% entry 90%` is reachable everywhere. (3) Reduced
motion needs an explicit `animation: none` for the reveals — scroll-driven animations are scrubbed by scroll
position, so the global `animation-duration: 0.01ms` does not touch them. The spinner is the one deliberate
reduced-motion exception (keeps turning, slower; freezing it would report a hang on a live request).
Stagger is `--i` per item, read by both paths, max index 4 → 280ms tail, inside the ~400ms budget.
**No dependency added:** CSS plus one 48-line hook. `scroll-behavior: smooth` + `scroll-margin-top` on the
landing's one jump link; **no sticky header exists** (`position: sticky` has zero hits), so that value is
breathing room, not header compensation.

**Verification.** eslint + `tsc -b` + vitest **146/146** (was 139; +5 hook tests, +2 Landing structural)
+ production build. New tests pin the safety invariant (no observer ⇒ `js-reveal` never set, so content is
never hidden), threshold 0.15, unobserve-after-fire so scrolling back up never replays, unmount cleanup,
the native-support no-op path, and that **the hero carries no `.reveal`** while every below-fold block does.
*One flake seen and diagnosed, not a real failure:* the first full run took 374s under machine load and
`Upload.test.tsx`'s retry test blew its 3000ms window; standalone it passes in 1.45s and every clean run
since is green. CSS is not loaded in jsdom, so no test can see the stylesheet either way.

**Next:** Hayden reviews/commits/PRs this branch. Then **PR 3** — em dashes (27 in rendered frontend copy,
5 in `digest/render.py`, which will move pinned digest tests) + the Settings/Privacy back buttons.
**Flagged, not fixed:** the posting panel has an entrance animation but no exit (it unmounts instantly), and
the tour + delete-confirm modals have neither; making them symmetric needs a delayed-unmount state change in
React, not CSS, so it stayed out of a motion-only branch.

---

## 2026-07-26 — D-097: trading vertical (the fourth, last for now) + cross-vertical duplication

**Housekeeping on the previous entry:** its "Next: Hayden reviews/commits/PRs" is **done** — the Rippling
work merged as **#104** (`1f48005`) and `main` is clean. Still open from it: the three Rippling activations
(`vja-review set-ats` → `approve` on `#103`/`#139`/`#141`), and from D-095 PR 1 the comp fill-rate re-run
against Neon. Hayden confirmed **robotics is live in prod**, so trading's import is the only pending cutover.

**Task:** add a trading vertical. The interesting part was not curation — it was that **grid/power already
owned ~17 trading-and-markets employers**, curated for their *energy desks* (Jane Street, Citadel, DRW, SIG,
Millennium, Balyasny, CME, ICE, plus the physical merchants). One vertical per user (D-064) means a trading
user would see **none** of them, and robotics' precedent was explicitly "never duplicate a company".

**Scope decisions (Hayden, this session).** **Duplicate the marquee 8** (Jane Street, Citadel, DRW, SIG,
Millennium, Balyasny, CME, ICE) rather than curate around them or move them out of grid — moving would
strip employers grid holds for good reason and force retire + re-insert surgery on prod under
`UNIQUE(vertical, name)`. Physical merchants stay grid-only. Key `trading_software`, display **"Trading &
Markets"**. Universe ~35–40. **Crypto + prediction markets in**, **sell-side bank tech + Bloomberg/
Broadridge/FactSet out**. Frontend copy ships in this branch. Recorded as **D-097**.

**One correction on the record.** When presenting the duplication option I said the duplicated postings
would re-extract for free, since extraction is content_hash-cached. Wrong: `postings_needing_extraction`
keys on `extracted_at IS NULL` **per posting row**, so there is no cross-row reuse of an identical body —
each duplicate pays a second Haiku extraction. Real cost of the decision: **5 extra nightly fetches** (3 of
the 8 are `layer2`/`detected`) plus that duplicate extraction. Corrected in D-097 and INVARIANTS; the
judgment didn't change.

**Built on `feat/trading-vertical` (uncommitted; Hayden owns commit/PR) — zero `src/` changes.** 44 seed
rows + `config/verticals/trading_software.yaml` + `profiles/hayden_trading_resume.md`. `AtsType` already
carried every value the curation needed (`avature`, `eightfold`), so D-004 held with **no code diff at
all**. CSV rows were appended by rewriting the file on **bytes** (it is 87 CRLF / 37 LF lines; Edit would
rewrite all of them) — `git diff --numstat` reads a clean `44  0`.

**Curation: 31 of 35 net-new candidates resolved to a live board (89%), so the universe overshot the ~35–40
target to 44** (36 net-new + 8 duplicates). Honoring the range would have meant deleting *verified
fetchable* boards, so instead the five marginal unfetchables were dropped (Peak6, Wolverine, IBKR,
Tradeweb, Quantlab/Jobvite) and the marquee unfetchables kept. **36 of 44 fetchable (82%)**: 26 Greenhouse,
4 Ashby, 3 Workday, 2 iCIMS, 1 Lever · 2 `detected` (Two Sigma/Avature, Millennium/Eightfold) · 6 `layer2`.

**Nine rows where probing beat guessing.** Optiver's US board is `optiverus` (plain `optiver` is a
near-empty global shell, 0 postings) · CTC `chicagotrading` · Five Rings `fiveringsllc` · Headlands
`headlandstechnologiesllc` · MarketAxess `marketaxesscorporation` · Galaxy `galaxydigitalservices` ·
**Kraken's Ashby slug is literally `kraken.com`** · Radix splits campus (`radixuniversity`, in scope) from
experienced · **Kalshi answers on both a stale Greenhouse board (27) and Ashby (36)** — careers site links
Ashby, so Ashby is pinned. **Cboe** is a Phenom front-end over a Workday tenant; both return 64 and Workday
is pinned (real `postedOn`, established contract). **HRT's only public API is its campus/talent-community
Greenhouse board** — 3 entries, two of them "join our talent community" placeholders. Included *because the
Stage-A gate drops those two on its own* (verified), so no per-employer rule and no fake postings (D-008).
Excluded for duplicate coverage: Cumberland (rides DRW's board), Jump Crypto (rides Jump's). Dropped for no
locatable careers page: Squarepoint.

**Stage-A tuned on measured data, not taste.** Over the 2,871 postings the first real pass fetched: shared
software/data baseline kept 1,074; the trading vocabulary added **+348** → 1,422. `trader` is deliberately
**in** (excluding it drops the "Quantitative Trader — New Grad" pipeline a CS+Econ candidate genuinely
applies to). Then `experienced` went into the excludes — trading firms label their non-campus track
literally **"Experienced Hire"** — dropping **69** survivors, all inspected and all genuinely
non-early-career. Final: **1,353 of 2,871 (47%)** in scope, which is the size of the one-time Haiku
extraction backlog when this vertical lands in prod.

**Verification.** Full default suite **749 passed, 35 deselected** (was 735); ruff format/check, mypy (143
files), import-linter (1 kept / 0 broken), `uv lock --check`; frontend eslint + `tsc -b` + vitest
**139/139** + production build. New/changed tests: real-config load + an 11-case Stage-A gate over real
board titles (incl. the HRT placeholders and "Experienced Hire"), the trading fetchable-subset counter, a
**cross-vertical duplication contract** test (same name under both verticals, same ATS wiring, different
`employer_id`), corpus totals 76→112, the `/api/verticals` picker set, and the frontend copy/landing
assertions. **Live end-to-end on a scratch migrated DB:** `vja-run --vertical trading_software` →
**36 employers, 0 failures, 2,871 postings**, every board clean on the first try. Then grid's Jane Street +
CME rows synced into the same DB: **221 Jane Street `external_id`s exist under both employer rows** with no
`UNIQUE(employer_id, external_id)` collision, and a re-sync of the grid row returned **all-`unchanged`**
(the D-088 churn check). No LLM calls, no prod DB, no deploy. Docs: D-097, INVARIANTS (D-005 wording
amended + a four-verticals rule), docs/06 (the duplication curation rule), docs/07 (demand-ledger addendum
— Avature rises to 3 companies incl. Two Sigma; build order unchanged, JazzHR still #1), seed README, CLAUDE.

**Flagged, not fixed (pre-existing, reproduces on clean `main`):** running `tests/unit/test_vertical_config.py`
together with `tests/integration/test_api.py::test_upload_unknown_vertical_404` fails with a `ConfigError` —
`test_config_dir_honors_env_override` reloads `vja.verticals`, and the API module's bound reference doesn't
survive it. The full default suite's ordering avoids it, so it isn't a gate failure; I left it alone rather
than fold an unrelated test-isolation fix into this branch.

**Next:** Hayden reviews/commits/PRs. **Sequencing matters:** `main` auto-deploys (D-068) and
`/api/verticals` is config-driven, so the picker offers **Trading & Markets** the moment this merges while
Neon holds zero trading employers — export the Neon `VJA_DATABASE_URL` and run
`vja-import-employers data/seed/employers_seed.csv` right after the deploy, then let the next nightly set
the baseline. **No migration.** Do **not** run `vja-load-profiles` against prod (it would add a fourth
active profile for haydenham10@gmail.com and a fourth digest).

## 2026-07-26 — D-096: coverage audit → the activation queue is empty → Rippling fetcher

**Housekeeping on the previous entry (it was stale, not mid-thought).** D-095 PR 2 merged as **#103**;
Neon is at head `a7c15e0b93d2` with `postings.description` present, so the D-083 pre-merge migration did
run. **Still open from D-095 PR 1 and unrecorded anywhere:** the comp fill-rate re-run against Neon — the
55% figure and the panel-only treatment were both chosen on local dev data.

**Context:** the session task was "add more companies + audit for `proposed` rows we could activate."
The audit answered the second half in the negative, which reshaped the first half.

**The audit (read-only, prod/Neon; 182 employers — 145 active, 13 `proposed`, 14 parked `approved`, 10
`retired`).** Of the 145 active, ~101 have a supported Layer-1 fetcher and **44 are active-but-
structurally-unfetchable** (`custom` 35, successfactors 3, avature 2, jobvite 2, ukg 1, eightfold 1).
**The no-code activation harvest is spent:** five of D-078's six runbook-activatable rows are already
`active` (ASI, GridBeyond, CivilGrid, Emerald AI, AiDASH), and live probes of every remaining
`proposed`/`approved` row on a supported ATS found **zero** cleanly activatable — Reliable Robotics and
Gridmatic have genuinely empty Lever boards, Ascend Analytics 404s on the Greenhouse API (500 on the
public board), Skydio has no working Greenhouse slug. So coverage required a **fetcher**, not a runbook.

**Scope decisions (Hayden, this session).** **Aloft `#133` → rejected/`retired`** — its Greenhouse board
is parent **Versaterm's** public-safety board (35 postings, "Chief Services and Delivery Officer",
Ottawa/Mesa), so activating it would attribute non-aviation roles to Aloft. **Build Rippling**, chosen
over JazzHR and Radancy variants on live-probe evidence. **Discovery run: Hayden runs `vja-discover`
himself.**

**The re-rank (supersedes D-078's fetcher ordering).** Probing beat the projection: **Radancy variants
dropped from rank 2 to last** — American Airlines and National Grid both **403**, L3Harris's clean JSON
endpoint returns `results_len=0`, NRG's aria total is a different format, Bombardier renders no table.
**JazzHR is now next** (3 rows / 21 jobs) but has **no feed at all** (`/apply/jobs.xml` + `jobs.json`
404, `/apply/feed` 410) — an HTML-parse build. **Correction on the record:** I first reported Rippling at
44 postings; that counted denormalized rows, not jobs. The real figure is **21**, which *ties* JazzHR —
Rippling won on contract quality and build risk, not coverage.

**Built on `feat/rippling-fetcher` (uncommitted; Hayden owns commit/PR).** New
`src/vja/fetchers/rippling.py`: slug-derived `GET api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`
returns a **bare JSON array** that is the complete set — it ignores `limit`/`offset`/`page` (a `?limit=5`
still returned all 38 rows) and 404s an unknown slug — so it takes the **single-response false-closure
guard** (Workable/Pinpoint/BambooHR), not paginate-or-fail. `external_id = uuid`; `apply_url` **supplied**,
never constructed; `location` from `workLocation.label`; no list date (`createdOn` is detail-only,
Pinpoint precedent). List-only: `fetch_detail` is `…/jobs/{uuid}` and `detail_description` joins the body.
Wiring is the intended one-liner each: `AtsType.RIPPLING`, an `_DERIVED_TEMPLATES` entry, a `_FETCHERS`
entry, one `_LIST_ONLY_FETCHERS` entry (`_DETAIL_RESOLVERS`/`_DETAIL_DESCRIPTIONS` derive). **No
migration** — `ats_type` is a `native_enum=False` VARCHAR(15) with no CHECK and `"rippling"` fits, so
**no Neon pre-merge step**.

**Two real findings the live smoke caught that the fixtures could not.** (1) `description` is **not a
string** — it is a dict of two HTML fragments, `role` (the posting) and `company` (identical boilerplate
on every job at that employer), uniform across all three tenants. Joined via the existing
`base.joined_body` with **`role` first**, so the panel doesn't open on "About us" (verified: on a real
Gridsight posting the company fragment starts at char 4,177 of 5,584). (2) **Rippling denormalizes its
list into one row per (job × work location)** — Gridsight's 38 rows are **15 jobs** — so the first build
failed Gridsight closed under D-088's "a duplicate `external_id` … is never silently collapsed". **Ruled
by Hayden:** narrow the guard rather than waive it — collapse on `uuid` and merge locations (the Workday
`locationsText` / Oracle `secondaryLocations` treatment) **only when the rows are identical apart from
`workLocation`**; rows disagreeing on anything else still fail the snapshot with zero mutation. The merged
location is **sorted**, because `content_hash` keys on `location` — API order would let a reordered board
flip every multi-location posting's hash and fake a corpus-wide content change, exactly the D-088 churn.

**Also landed (no code): Comply365/Vistair** — D-078 item (5) validated it in July and it was never
persisted. Re-probed at 10 open (BambooHR `vistairhr`, real US software roles incl. Beloit WI). Added as a
**curated seed CSV** row, not a proposal correction (it has never been in the DB — D-077 reserves the CSV
for exactly this). Aviation seed-fetchable **15 → 16**.

**Verification:** full default suite **735 passed, 35 deselected** (was 691; 44 new: `test_rippling.py`
×41 incl. the collapse/order-independence/conflict cases, plus registry + endpoints + extract list-only
pins); ruff format/check, mypy (143 files), import-linter (1 kept / 0 broken), `uv lock --check`.
**Live smoke** (`tests/live/test_rippling_live.py`, 4 passed) against all three real tenants, plus an
**end-to-end scratch-DB run** through `sync_employer`: 21 postings / 21 distinct `external_id`s
(Gridsight 15 + Portside 4 + Raptor Maps 2), and a **second sync returned all-`unchanged`** — the churn
check the D-088 sort exists for. Docs: D-096, INVARIANTS (snapshot-validation rule narrowed + Rippling
contract + build order **replaced**), docs/07 (third-edition demand ledger), seed README, CLAUDE.

**Next:** Hayden reviews/commits/PRs. **Sequencing constraint — the three activations must wait for merge
+ CD deploy**, because `approve` → `active` means the nightly Job fetches them:
`vja-review set-ats 103 --ats-type rippling --slug raptor-maps-inc` (then `139`/`gridsight`,
`141`/`portside`) → `vja-review approve 103 139 141`. Aloft `#133` was rejected in prod this session.
Flagged but **not** acted on: retired Aerovy `#111` (ashby `aerovy`) has 2 live Seattle software roles
today — reversing a human rejection is Hayden's call. Next fetcher block: **JazzHR**.

## 2026-07-24 — D-095 PR 2: posting description — persisted at zero new cost, served on demand

**Context:** PR 1 merged as **#102**, clearing the "hold PR 2 until PR 1 merges" gate. This is the second
half of D-095, and it closes the open read-path question PR 1 left: a detail endpoint vs. an inline snippet.

**Scope decisions (Hayden, this session).** **Read path = `GET /api/postings/{id}`, fetched when the panel
opens** — a fill query over the dev DB (314 in-scope open) found 184 rows (59%) carrying a body, median
~3.2 KB plain text / p90 5.5 KB, so inlining would take a tens-of-KB dashboard load past **1 MB** to serve
text a user opens on maybe three rows (a truncated snippet: still ~380 KB, and mostly "About us"). **No
body ⇒ render nothing** — beta, and the corpus fills as postings turn over, so explanatory copy isn't worth
it. **Paragraph-preserving plain text** (same work as collapsing; bullets are most of a job description).
**No SPA-side cache** — one PK lookup isn't worth the state. Recorded as a PR 2 implementation note under
D-095 (no new ADR).

**Built on `feat/posting-description` (uncommitted; Hayden owns commit/PR).** New bottom-layer
`src/vja/text.py` (`html_to_text`): block tags break lines (paragraph vs list-item spacing), inline markup
stays with its sentence, `script`/`style` dropped, entities decoded, blank-line runs collapsed. Two real-ATS
findings shaped it — **Greenhouse's `content` is *escaped* HTML** (`&lt;h3&gt;…`), so it is `html.unescape`d
before parsing or users would read raw tags; and flattening with a `"\n"` separator shatters
`We use <b>Python</b> and SQL` into one line per fragment, so the separator is empty and only block tags
insert breaks. Migration `a7c15e0b93d2` adds nullable `postings.description`. Write path: insert writes the
fetcher's body; `update_changed` writes it unconditionally (**required keyword-only** — it immediately caught
a stale call site in the tests) so a list-only `None` clears the stale body while the same statement's
`extracted_at` clear guarantees the refill; reopen preserves it when content didn't move; `save_extraction`
fills only when NULL (the `location` L1-authoritative pattern, now a loop over both columns). Each list-only
fetcher answers `detail_description(payload)` for its own shape behind a new `ListOnlyFetcher` protocol +
`base.joined_body`, wired as `_DETAIL_DESCRIPTIONS` beside `_DETAIL_RESOLVERS`; Oracle reads **only**
`External*Str` (the payload also carries `Internal*Str` written for the employee-facing site). `_source_text`
became `_posting_source`, reading the payload **once** for both the model text and the body — a second read
would double requests to a list-only board. API: `posting_description()` + `GET /api/postings/{id}` behind the
same `_resolve_profile` gate as the list, floored on the caller's vertical + `in_scope`. Frontend:
`fetchPostingDescription` (credentialed, abortable), panel `useEffect` keyed on posting id, body rendered last
(after the match write-up, before apply) as `pre-wrap` with `overflow-wrap: anywhere`.

**Two invariants the build had to protect.** `content_hash` still keys on the fetcher's **raw** description —
normalizing into it would flip every stored posting's hash on one night (a corpus-wide false "content
changed" + mass re-extraction, exactly D-088's churn); pinned by a regression test. And the extraction prompt
input is byte-identical, so results and the prompt cache don't move.

**Verification:** full default suite **691 passed, 31 deselected** (was 640; 51 new: `test_text.py` ×19, the
seven fetchers' `detail_description` ×14, pipeline description/reopen/hash-stability ×6, extraction-run
fill/never-clobber ×4, API detail endpoint ×7 incl. cross-vertical + out-of-scope + auth-required, plus the
schema-guard head); ruff format/check, mypy (140 files), import-linter (1 kept / 0 broken), `uv lock --check`;
alembic up/down/up on scratch SQLite; frontend eslint + `tsc -b` + vitest **139/139** (was 131) + production
build. **Live smoke** on a scratch migrated DB (real write path, minted session cookie, `VJA_AUTH_REQUIRED=1`,
served build, headless Chrome 1440×900): Greenhouse escaped-HTML body renders with paragraphs + bullets,
list-only body arrives via extraction, the no-body row renders no block while the rest of the panel stands,
exactly one detail request per open (none on list load), `pre-wrap` confirmed, no panel or document
overflow, zero console errors. **The smoke caught a real defect the unit tests missed:** the loading state
was the string `"loading"` and the render check was `typeof === "string"`, so mid-fetch the panel printed the
word "loading" to the user — the state is now `undefined`, with a regression test. Docs: D-095 PR 2 note,
INVARIANTS (description rule + SPA panel line), docs/18 F2, CLAUDE.

**Next:** Hayden reviews/commits/PRs. **Schema-changing PR — run the Neon migration pre-merge (D-083):**
explicitly `export VJA_DATABASE_URL=<Secret Manager Neon URL>` (Alembic does not read `.env`), then
`alembic current` → `upgrade head` → `current`. Note that PR 1's still-open follow-up stands: the 55%
comp fill-rate was measured on local dev data and was never re-run against Neon.

## 2026-07-24 — D-095 PR 1: salary display (F2 Phase A) + the panel click affordance

**Context:** the D-094 compliance block is merged (#99/#100/#101) and the remaining beta-exit items are
Hayden-run/no-code, so this starts the D-087 post-beta slate. `docs/18` sequences churn → F2 Phase A → F4 →
F1 → F3; churn blocks **F1/F4 only**, so salary was buildable now. Hayden added **description display** to
the session — not in the D-087 slate, and the bigger of the two — so it ships as PR 2.

**The finding that reshaped PR 1.** The mandated fill-rate query (dev DB, 314 in-scope open) returned
`comp_min`/`comp_max` on 172 (55%), `comp_raw` on 176, `comp_min` never present without `comp_raw` — but
also that the integers are **not display-safe**. Haiku annualizes despite the prompt forbidding it:
`$49.82 to $60.22 per hour` → `103579/125258`, a ten-week internship at `$4,250 weekly` → `170000/170000`,
`75,000 CAD to 108,00 CAD` → bare integers, `Pay within range listed + Bonus + Benefits + Equity` (no figure
at all) → `81456/122184`. Displaying those would invent a salary on a real posting (D-008's whole point).

**Scope decisions (Hayden, this session):** corroboration guard over prompt-fix-then-re-extract (a schema
change + real LLM spend before anything displays) and over raw-only display · new `postings.description`
column with HTML normalized to plain text via the existing `beautifulsoup4` (over HTML + a client sanitizer,
and over a no-migration read from `raw_payload` covering only ~59% of rows) · **no description backfill**
(natural fill; a re-fetch CLI and a clear-`extracted_at` re-extraction both rejected) · two PRs, salary
first · salary **panel-only**, no row chip and no sixth sortable column (~45% of rows would show a dash) ·
affordance = chevron + guide copy, **title keeps its one-click apply** (retargeting it was rejected as a
behavior change beta users would feel). Recorded as **D-095**.

**Built on `feat/salary-display` (uncommitted; Hayden owns commit/PR) — PR 1 of 2:** new pure
`src/vja/comp.py` (`annual_usd_display`, bottom import-linter layer, zero LLM) suppressing on non-annual
pay periods, non-USD currency, absent/digit-free `comp_raw`, implausible annual figures, and inverted
ranges — prefix-matched words so "through"/"Monday" don't false-positive, whole-word currency codes so
"Cadence" isn't CAD, and R$/C$/A$ only when they actually price a number. `DashboardPosting` +
`open_postings_with_match_quality` carry `comp_min`/`comp_max`/`comp_raw`; `PostingRow` adds them plus a
`@computed_field comp_display`, so the judgment is server-side and the SPA stays dumb. Extraction prompt
tightened (enumerate forbidden periods, forbid non-USD, require the integers to come from `comp_raw`) —
future extractions only. Frontend: a `.panel-salary` block (its own block, not a fourth `panel-meta` cell,
since the fallback is often a full sentence) rendering `comp_display` → `comp_raw` → "Not listed", with
`comp_raw` beneath a shown range; a sixth 16px grid track holding an `aria-hidden` chevron that rotates on
`.row.selected`; `.head-right` replacing the `span:last-child` alignment rule the new track would have
broken; sharpened `.table-guide` copy; tour slide 4 names salary.

**Verification:** full default suite **640 passed, 31 deselected** (45 new: `test_comp.py` ×43 driven by
the real production strings, plus API + dashboard-query comp coverage); ruff format/check, mypy (138 files),
import-linter (1 kept / 0 broken), `uv lock --check`; frontend eslint + `tsc -b` + vitest **131/131** (was
125) + production build. **Guard replayed over the whole dev corpus: 157 of 176 comp-bearing rows display,
and all 19 suppressions are genuine saves.** Live smoke on a scratch migrated DB (throwaway session secret,
minted cookie, served build, headless Chrome 1440×900): annual row → `$105,000 – $131,325` + raw beneath,
internship + hourly rows → raw only with no `$` range, no-comp row → "Not listed", chevrons render and
rotate, header alignment intact, no horizontal overflow, zero console errors. Docs: D-095, INVARIANTS
(dashboard display rule + SPA affordance line), docs/18 (F2 Phase A status + the annualization finding),
CLAUDE. **Prompt-change eval (the D-093/D-090 gate, run this session):** real Haiku over 5 production payloads,
old vs new prompt, 46,278 in / 2,443 out tokens ≈ $0.06. Weekly internship: old → **212,500** (52 × $4,250,
*worse than the stored 170,000 — the annualization isn't even stable between runs*), new → **null**. Hourly:
old → 38,460/44,950, new → **null**. Both clean-annual controls unchanged under both prompts (no
regression). The "Pay within range listed" row returned the same integers under both, with `comp_raw` now
quoting "$81,456 - $122,184 per-year-salary" — so that row was **not** a fabrication, just an
under-informative stored quote; the guard is conservative there and the prompt fix makes it display again
once re-extracted. D-095 corrected accordingly. Hayden signed off.

**Next:** Hayden reviews/commits/PRs. **One item open before merge:** re-run the fill-rate query against
Neon — the 55% figure and the panel-only treatment were chosen on local dev data. **PR 2 (description
column) is deliberately NOT started** — Hayden is holding it until PR 1 merges and wants it planned
separately, including the still-open read-path call (a `GET /api/postings/{id}` detail endpoint vs. a
truncated inline snippet; a full description on ~300 rows would add multi-MB to a list response that is
currently tens of KB). It needs the D-083 pre-merge Neon step when it does run.

## 2026-07-23 — D-094 compliance PR 3 (settings + account deletion) built — the 3-PR block complete

**Scope decisions (Hayden, this session):** the settings surface is one user resource —
`PATCH /api/me {digest_paused}` (rejected: a separate `/api/settings`); the delete confirm is a
plain modal, no type-to-confirm; the in-flight-backfill/delete race is accepted + documented (FK
enforcement makes resurrection impossible; a late `save_match` FK-fails and aborts that backfill
with one logged traceback), no locking; `/settings` is login-gated only so a never-onboarded user
can still delete. Recorded as a PR 3 implementation note under D-094 (no new ADR). **No migration**
— head stays `e91b3a6f2d04`, so no Neon pre-merge step.

**Built on `feat/settings-account-deletion` (uncommitted; Hayden owns commit/PR) — PR 3 of 3:**
`delete_user_account` in `db/users.py` (one `begin()` transaction, child→parent: matches by the
user's profile ids → profiles by `user_id` OR `user_email` (catches the never-linked pre-login
seed row) → digests by `recipient` email (no user FK) → the `users` row; counts logged by user id
only). `app.py`: `MeUser` gains `digest_paused` (populated from the already-loaded `User`);
`PATCH /api/me` reuses `set_digest_paused` (404 on vanished row); `DELETE /api/me` → 204 + session
pop in-handler; CORS `allow_methods` gains PATCH/DELETE. Frontend: `Settings.tsx` (toggle rendered
from context truth + silent `/api/me` re-sync; danger card → confirm modal on the WelcomeTour
scaffold; post-delete `logout()` + land on Landing), `SettingsRoute` (login-gated, no profile
check) + `/settings` route + nav link for every authed user; `api.ts` `setDigestPaused`/
`deleteAccount` + `digest_paused` on `User`; scoped `.settings-*`/`.btn-danger` theme block
(the palette's first red, used nowhere else); Privacy page copy now points pause + deletion at
`/settings` (founder email kept as fallback).

**Verification:** full default suite **595 passed, 31 deselected** (10 new: settings API ×9 —
PATCH pause/resume/idempotent/401/404-ghost, DELETE 401/204+isolation/seed-edge/no-profile —
plus a real-cookie login→DELETE→401 session test in `test_auth.py`); ruff format/check, mypy
(136 files), import-linter (1 kept / 0 broken), `uv lock --check`; frontend eslint + `tsc -b` +
vitest **125/125** (was 104: Settings suite ×11, App `/settings` guards + nav ×5, api client ×4,
Privacy settings-links pin) + production build. Live HTTP smoke on a scratch DB (throwaway
secret, minted session cookie, `VJA_AUTH_REQUIRED=1`): pause→resume flips `users.digest_paused`
both ways, anonymous PATCH/DELETE 401, DELETE 204 → same cookie 401, user/profile/match/digest
rows 0 while postings/employers survive. Docs: D-094 PR 3 note, INVARIANTS (delivery + auth
sections + SPA routes), docs/15 exit line, CLAUDE. **Next:** Hayden reviews/commits/PRs — this
closes the D-094 3-PR block; remaining exit items are the GCP alert pair, the OAuth
publishing-status check, and the no-code activations (all Hayden-run).

## 2026-07-23 — D-094 compliance PR 2 (digest unsubscribe) built

**Scope decisions (Hayden, this session):** confirm-page flow (GET renders a confirm page, **POST**
sets the flag — mail scanners prefetch GETs, so a prefetch must never unsubscribe anyone); RFC-8058
one-click headers included (`List-Unsubscribe` + `List-Unsubscribe-Post`, provider POST hits the same
endpoint — Gmail's native Unsubscribe + bulk-sender requirement); token = non-expiring `itsdangerous`
`URLSafeSerializer` seeded from `VJA_SESSION_SECRET` (salt `digest-unsubscribe`, payload `{uid,email}`,
both must match the live row). Recorded as an implementation note under D-094 (no new ADR).

**Built on `feat/digest-unsubscribe` (uncommitted; Hayden owns commit/PR) — PR 2 of 3:**
`users.digest_paused` (Boolean NOT NULL server-default false; migration `e91b3a6f2d04` off
`c4e8a7d9132f`, batch-op + real downgrade) — on `users`, not versioned `profiles`, so a reupload
can't reset it. New `vja/digest/unsubscribe.py` (make/parse token + URL; api imports it downward,
contract-clean). `send_digest` checks the flag **before** `build_digest` (new status `"paused"`, one
stderr line, no `digests` row → window doesn't advance; resume later gets the accumulated diff), and
threads footer + headers only when `VJA_PUBLIC_BASE_URL` and a `users` row exist (dev/seed-profile
sends stay plain). `render_digest` gained keyword-only `unsubscribe_url` (None ⇒ byte-identical
output). No-login `GET`/`POST /unsubscribe` in `app.py` (registered before the SPA mount; invalid
token → generic 400, no user enumeration; POST idempotent, body never read so the RFC-8058 form body
works). `ship.sh`: `VJA_SESSION_SECRET` added to `JOB_SECRETS` (REPLACE semantics — mandatory) +
`JOB_ENV` now sets `VJA_PUBLIC_BASE_URL` on the Job (service guard policy untouched); CUTOVER.md +
`.env.example` reconciled. Privacy page copy now points at the footer link (contact email kept).

**Verification:** full default suite **585 passed, 31 deselected** (18 new tests: token unit ×5,
render footer ×2, send paused/footer/headers ×4, `/unsubscribe` API ×7 incl. auth-required-on +
SPA-shadowing pins, migration round-trip ×1 — plus updated schema-guard head + deploy-config pins);
ruff format/check, mypy (135 files), import-linter (1 kept / 0 broken), `uv lock --check`,
`bash -n ship.sh`, alembic up/down/up on scratch SQLite; frontend eslint + `tsc -b` + vitest
**104/104** + production build. Live HTTP smoke on a scratch DB: GET confirm 200 (email + button),
RFC-8058 one-click POST 200, garbage token 400, `digest_paused` flipped true in DB. Docs: D-094 note,
INVARIANTS (digest & delivery), docs/15 exit line, CLAUDE. **Next:** Hayden reviews/commits/PRs.
**Schema-changing PR — run the Neon migration pre-merge (D-083):** export the Secret Manager
`VJA_DATABASE_URL`, then `alembic current` → `upgrade head` → `current`. Post-merge deploy check:
`gcloud run jobs describe vja-nightly` shows `VJA_SESSION_SECRET` mounted + `VJA_PUBLIC_BASE_URL`
set; then the next real digest proves the footer E2E. PR 3 (settings + deletion) follows on a fresh
branch.

## 2026-07-22 — D-094 beta exit re-scoped; compliance PR 1 (privacy notice) built

**Decision (D-094):** Hayden reduced the final beta-exit line — the five-pillar scaling doc, D-086 digest
idempotency, and broad monitoring are dropped; time goes to user-facing compliance/usability features. In:
a 3-PR block — privacy notice → digest unsubscribe (pause-only, flag on `users` so a résumé reupload can't
reset it) → settings page + hard account deletion. Kept minimums: one GCP alert-policy pair on the nightly
Job, a one-time Google OAuth publishing-status check (100-user "Testing" cap), the July-23 first-Luna-night
read-only audit, and the Hayden-run no-code activations. Exit-line state was reconciled: robotics config
merged #93 with its Neon baseline running, and Luna low merged #97 — both formerly-open exit items are done.

**Built on `feat/privacy-page` (frontend-only, uncommitted; Hayden owns commit/PR) — PR 1 of 3:** new static
`/privacy` route (`Privacy.tsx`): plain-language disclosure of what's stored (Google email/name, résumé
text, matches/digests), résumé processing by Anthropic + OpenAI APIs (with the not-used-for-training API-terms
line), Resend delivery, single session cookie, no selling/no auto-apply, and the contact-email deletion path
until PRs 2–3 ship self-serve. Landing footer links it (plain `<a>` — Landing renders Router-free in tests);
a new shell footer (Privacy + ©) renders on all non-`/` routes, skipping the landing which owns its own
footer; the upload form gains the one-line AI-processing disclosure beside submit. New scoped `.legal-page` /
`.app-footer` / `.upload-disclosure` styles in `theme.css`.

**Verification:** frontend eslint + `tsc -b --noEmit` + vitest **103/103** (was 95: new Privacy suite, shell
footer/route coverage incl. footer-absent-on-`/`, landing footer link, upload disclosure) + production build
green. Headless-Chrome pass against the served build on a scratch sqlite DB (throwaway session secret, minted
cookie, zero LLM): `/privacy` 1440+720, landing, and authed `/upload` 1440+720 — no overflow, no new console
errors (only the pre-existing anonymous `/api/me` 401 log). Backend untouched; `git diff --check` clean.
Docs: D-094, docs/15 exit line, CLAUDE. **Next:** Hayden reviews/commits/PRs; then PR 2 (unsubscribe:
migration + email footer + endpoint) on a fresh branch.

## 2026-07-22 — Gitleaks fixture false positive unblocked the post-Luna deploy

**Incident:** the D-093 deploy initially failed because prod lacked the `OPENAI_API_KEY` secret
(`ship.sh` now mounts it on both Cloud Run targets); Hayden created the Secret Manager secret and
re-ran CI via `workflow_dispatch`. That rerun then failed the `secrets` gate: gitleaks flagged
`data-api-key="86x0eymjxbhgol"` at `tests/fixtures/radancy_detail.html:1087` — the public
Apply-with-LinkedIn widget key served in NextEra's public careers page, captured with the D-052
Radancy fixture. It is a client-side identifier, not a credential; nothing was rotated. Root cause
of the late surfacing: push/PR runs scan the pushed range, but `workflow_dispatch` scans **full
history** (`fetch-depth: 0`), reaching the old fixture blob that no push diff ever contained.

**Built on `fix/gitleaks-fixture-allowlist` (uncommitted; Hayden owns commit/PR):** a local
full-history gitleaks (8.30.1) run against the default ruleset enumerated the complete finding set —
**two** public values in the same fixture's one historical blob: the widget key at line 1087 and a
NextEra `previewLink` URL token (`token=a4un…%3D%3D`) at line 693, embedded in the public
"no unsolicited resumes" body paragraph. New root `.gitleaks.toml` extends the default ruleset with
two narrow line-target allowlist regexes, one per value shape (deliberately not a blanket
`tests/fixtures/` path allowlist — fixtures are sanitized by policy and the scanner backstops that
policy). The allowlist is required because the values persist in the historical blob; scrubbing
alone cannot green a full-history scan. All three working-tree occurrences (the widget key at 1087
and as `companyId` at 915, the URL token at 693) were still scrubbed to `fixture0scrubbed` for tree
hygiene; no code reads the attributes, and the only detail-fetch assertion ("NextEra Energy" in the
description) is unaffected. docs/09 now records the config file and the range-vs-full-history scan
behavior.

**Verification:** local full-history gitleaks (`--log-opts=--all`, 109 commits) **zero findings**;
a worktree scan's only hits are the git-ignored `.env` (never scanned by CI — correct backstop
behavior). Full default suite **565 passed, 31 opt-in deselected**; Radancy fixture suite 18/18;
ruff format/check, mypy, import-linter (1 kept / 0 broken), `uv lock --check`, and
`git diff --check` green. **Next:** Hayden reviews/commits/PRs; after merge, re-run the deploy
(Actions → CI → Run workflow on `main`) — the dispatch-mode `secrets` pass is the end-to-end proof,
and the deploy then lands the Luna cutover with the new secret mount.

## 2026-07-22 — D-093 Luna-low matching cutover built after human-reviewed eval

**Decision:** the approved eight-case grid/aviation/robotics comparison produced Sonnet 4.6 medium **7/8**,
GPT-5.6 Luna low **8/8**, and Luna medium **8/8**. Sonnet promoted the deliberately ambiguous mid-level/domain-fit
case to `yes/72` twice; both Luna efforts kept it at `maybe/48`. Luna low averaged 5.94s versus Sonnet's 9.61s
and its LiteLLM catalog estimate was ~$0.018 versus ~$0.049 for the same eight cases; provider billing remains
authoritative. Hayden reviewed every score/rationale and selected `openai/gpt-5.6-luna` at `low` effort.

**Built on `eval/luna-vs-sonnet-matching` (uncommitted; Hayden owns commit/PR):** matching now defaults to Luna
low. One approved prompt-calibration round treats internships/coursework/projects as valid early-career evidence
and makes domestic relocation neutral to verdict/score while preserving explicit country/work-auth and mid/senior
guards. The tuned run passed **8/8**, moving the generic technical fit `maybe/58 → yes/76` and clear robotics
fit `yes/74 → strong_yes/88`; one malformed `fits` fragment did not repeat on its allowed rerun, so no heuristic
cleanup/retry was added. City + region preferences and variable prompt parts are parked post-beta; they annotate
logistics rather than change semantic match quality, and today's prompt stays universal.

**Deployment/security/workflow:** `ship.sh` mounts the existing OpenAI Secret Manager key by name on both the API
service and nightly Job and preserves the exact Luna-low env route; GitHub Actions never receives the provider key.
The secret-safe unchained `vja.llm` exception regression remains green. Extraction and matching live evals are
manual metered evidence requiring recorded outputs + Hayden signoff, not paid CI gates; no benchmark/CI machinery
was added. D-093, INVARIANTS, docs/08/09/12/15/17/18/19, deploy runbooks, CLAUDE, `.env.example`, and dataflow are
reconciled. Full default suite **565 passed, 31 opt-in deselected**; ruff format/check, mypy (132 files),
import-linter (1 kept / 0 broken), `uv lock --check`, `git diff --check`, bash syntax, frontend lint/types/**95
tests**/build, and production `linux/amd64` image `vja:luna-match-cutover` are green. No production deploy, commit,
or PR was performed. **Next:** Hayden reviews/commits/PRs; merge-to-main deploys Luna low, then the next normal
scheduled run is the first production quality/cost observation.

## 2026-07-22 — D-090 extraction candidates rejected; Haiku retained and eval kept advisory

**Decision:** the approved lean six-posting evaluation and one prompt-tuning round produced **Haiku 6/6**,
**DeepSeek V4 Flash 5/6**, and **DeepSeek V4 Pro 4/6**. Both DeepSeek models omitted the explicit United States
eligibility location on a remote role; Pro also labeled a 3–5-year Engineer II role `early_career` rather than
`mid`. Hayden rejected both candidates, so extraction remains `anthropic/claude-haiku-4-5`; no DeepSeek adapter,
production credential, route, or deploy change remains. The useful universal prompt rules and six representative
Haiku cases remain as a manual/advisory tool, never a merge gate. GPT-5.6 Luna matching is the next separate
branch/decision. Hayden explicitly rejected automatic extraction-model gating: the first solid Haiku baseline
was 5/6, which is evidence to review rather than a reason to block a PR.

**Security correction:** an initial DeepSeek provider failure rendered request details, including the old local
API key, through the provider SDK traceback. Hayden rotated the key. `vja.llm` now replaces provider-call failures
with a non-chained exception containing only model route, exception class, and integer status; a regression
formats the full traceback and proves keys and prompts cannot render. No secret value entered the repo diff.

**Built on `fix/extraction-eval-hardening` (uncommitted; Hayden owns commit/PR):** retained only the concrete
quality and security improvements. Focused provider/extraction coverage **22 passed**; full default suite
**564 passed, 25 opt-in deselected** (one pre-existing FastAPI/httpx deprecation warning). Ruff format/check,
mypy (132 files), import-linter (1 kept / 0 broken), `uv lock --check`, `git diff --check`, frontend lint/types/
**95 tests**, and production Docker image `vja:extraction-eval-hardening` are green. The final paid Haiku eval
was already 6/6 after the retained prompt change, so it was not rerun after deleting code used only by rejected
DeepSeek routes. The proposed automatic extraction-eval workflow and repository-secret dependency were removed;
then Hayden reviews/commits/PRs this branch. Matching/Luna starts only on its next branch.

## 2026-07-21 — D-090 lean provider readiness built; no model cutover

**Decision correction:** Hayden rejected work without a concrete use case. The D-090 plan now has three
small blocks only: provider readiness, DeepSeek V4 Flash extraction evaluation/cutover, and GPT-5.6 Luna
matching evaluation/cutover. Provider dashboards are authoritative for exact billing. The generic benchmark,
payload compaction, new prefilter, cache redesign, paid-failure-ledger work, and `no`-output follow-on are out;
shortening a `no` payload would not avoid the reasoning that produces the verdict.

**Built on `fix/optional-llm-catalog-cost` (uncommitted; Hayden owns commit/PR):** stable LiteLLM 1.93 replaces
1.92 so DeepSeek can map `reasoning_effort=none` to `thinking.type=disabled`. Valid structured responses no
longer fail solely because LiteLLM lacks catalog pricing: required usage/model/latency telemetry still crosses
the typed boundary, missing/invalid cost warns once per model, call/run cost becomes `None`, and the existing
nullable `pipeline_runs.llm_cost_usd` stores `NULL` rather than a false `$0`. Known catalog estimates still
aggregate unchanged. No model route, prompt, schema, provider credential, deployment, database migration,
Neon read, or paid provider call was made.

**Verification:** focused provider/extraction/matching/nightly coverage **26 passed**; full default suite
**563 passed, 20 opt-in deselected** (one pre-existing FastAPI/httpx deprecation warning). Ruff format/check,
mypy (132 files), import-linter (1 kept / 0 broken), `uv lock --check`, `git diff --check`, frontend lint/types/
**95 tests**, and production Docker image `vja:llm-provider-readiness` are green. LiteLLM 1.93's installed
DeepSeek transform was inspected locally and explicitly maps `none` to disabled thinking. **Next:** Hayden
reviews/commits/PRs this readiness block; after merge, create the separate small extraction-eval/cutover branch.

## 2026-07-21 — D-092 Workday pagination contract corrected from the first D-091 evidence run

**Read-only production audit:** PR #92 merged July 20, so the July 21 execution `vja-nightly-djxjt`
was the first scheduled run that actually carried D-091 (the documented July 18 gate was stale). It
completed once in 34m39s with zero retries; service health and anonymous 401 passed, all seven digests
sent once, four `-1` match scores normalized without match failures, and the nightly ended `ok` over a
partial 101-employer pipeline. All 15 fetch failures were Workday `nonzero → 0` boards. Every affected
walk exactly reached page one's target with equal unique-ID count, zero overlap, and zero malformed IDs;
four other multi-page Workday boards repeated the original total and also completed exactly. No manual
board fetch was performed and failed snapshots raised before the sync transaction. Adjacent run evidence:
the new Robotics baseline accounted for 313/389 extractions and `$1.5682` of `$2.1812` catalog cost; no
Robotics profile meant zero Robotics matches/digests.

**Built on `fix/workday-pagination-contract` (uncommitted; Hayden owns commit/PR):** D-092 makes page one
authoritative and accepts exactly two consistent later-page modes: repeat that total or report zero. Mixed/
other totals, early empty pages, short/over counts, repeated or malformed IDs, and request/shape/mapping
failures still reject before mutation. Thirteen observed zero-sentinel boards ended on short final pages and
will be restored. Airbus and Thales remain failed closed: both reported exactly 2,000 and returned 100 full
pages, an ambiguous cap signature now surfaced by an explicit `FetchError`. No broad cap workaround, config/
Layer-2 reclassification, DB/schema/model change, production mutation, deploy, commit, or PR was performed.
D-091's noisy shadow mode is retired; page evidence is debug-only and one compact completeness summary remains.

**Regression + verification:** the focused suite was observed red first (**7 failed / 11 passed**), then the
approved implementation passed **20 focused Workday/pipeline guard tests**. Full default suite **561 passed,
20 opt-in deselected**; ruff format/check, mypy (132 source files), import-linter (1 kept / 0 broken),
`uv lock --check`, and `git diff --check` are green. D-092, INVARIANTS, docs/05, docs/08, docs/15, docs/19,
and CLAUDE describe the same contract. **Next:** Hayden reviews/commits/PRs; merge deploys the fix, and the
next normal scheduled run should show 13 restored Workday boards plus only the two explicit cap failures before
LLM-optimization Block 2 begins.

## 2026-07-17 — D-091 Workday pagination diagnostics built after morning audit

**Read-only production audit:** July 17 execution `vja-nightly-qcw5d` completed once in 33m35s with zero
retries; all seven digest sends logged once, health/anonymous-401 passed, five `-1` match scores normalized,
and LiteLLM stayed on Haiku 4.5/Sonnet 4.6 with plausible `$1.2168` catalog cost. The partial pipeline had
15/75 fetch failures: GE Vernova's existing missing-title row plus **14 Workday tenants whose first nonzero
total became zero on page two**. Failed boards made no mutations. Hayden confirmed NextEra's 145 new + 121
reopened rows were expected old-job DB catch-up from the corrected D-088 Radancy snapshot.

**Built on `fix/workday-pagination-diagnostics` in an isolated worktree (uncommitted; Hayden owns commit/PR):**
D-091 keeps every changed-total Workday snapshot invalid, but finishes one bounded quarantined pagination walk
against page one's target before raising the original `FetchError`. Page logs now capture totals/sizes,
cumulative/unique/overlap/malformed counts, hashed ordered IDs, HTTP/response metadata, and a final
`would_complete` classification. No raw job identity/payload/content is logged; the invalid list never leaves
the fetcher, so diff/DB mutation remains impossible. Stable pagination behavior is unchanged. Regression
coverage distinguishes complete+disjoint zero-total pages, ignored-offset/repeated pages, premature empties,
and positive total drift; the standing pipeline failure test pins zero mutation.

**Verification + handoff:** focused Workday/pipeline suite **31 passed**; full default suite **555 passed,
20 opt-in deselected**; ruff format/check, mypy (53 source files), import-linter (1 kept / 0 broken),
`uv lock --check`, and `git diff --check` are green. D-091, INVARIANTS, docs/05, docs/15, docs/19, and CLAUDE
are current. No manual board fetch, behavior fix, DB/schema/model/config change, deploy, commit, or PR was
performed; the separate uncommitted Robotics worktree was untouched. **Next:** Hayden reviews/commits/PRs,
merge-to-main deploys the trace before July 18, and the normal scheduled run supplies the evidence for a
separately reviewed Workday contract correction.

## 2026-07-16 — Robotics vertical starter inputs built

**Built on `feat/robotics-vertical-seed` (uncommitted; Hayden owns commit/PR):** added the approved
`robotics_software` starter universe: 30 manually curated employers across humanoid/embodied AI,
warehouse/logistics, industrial/manufacturing, field/construction/agriculture/inspection, and
medical/service/consumer robotics. Twenty-four boards were live-verified through existing generic Layer-1
fetchers (10 Greenhouse, 5 Lever, 8 Ashby, 1 Workday); five unresolved enterprise portals route honestly to
Layer 2 and Universal Robots remains detected SuccessFactors. Existing Aviation/Grid companies were not
duplicated. Multi-vertical employer membership remains explicitly out of scope for a separate design PR.

**Config/profile/tests/docs:** added the Robotics YAML using the existing US + early-career prefilter and
seniority exclusions, with only Robotics-specific Stage-A title vocabulary added; the filtering system itself
did not change. Added the required Robotics-tilted Hayden profile, real-config loader coverage, API picker
coverage, and seed-import/fetchable-subset coverage. Updated docs/06, docs/17, and the seed guide. No `src/`,
schema, migration, frontend, database import, production deploy, LLM call, discovery run, commit, or PR was
performed. **Cutover remains later:** import the CSV into Neon and establish the initial baseline before the
config deploy exposes Robotics through config-driven `/api/verticals`. **Verification:** focused config/import/
API coverage is green; the full default suite is **555 passed, 20 opt-in deselected**; ruff format/check, mypy,
import-linter (1 kept / 0 broken), `uv lock --check`, and `git diff --check` are green. **Next:** Hayden reviews,
commits, and opens the PR; run/import/discovery operations wait for the approved LLM-cost work and explicit
production cutover.

## 2026-07-16 — PR #90 merged/deployed; LLM observation handoff reconciled

**Status-only/docs follow-up on `docs/litellm-post-merge-handoff` (uncommitted; Hayden owns commit/PR):** PR
#90 merged at `07ed265` and CD deployed that image to both `rolefeed` (revision `rolefeed-00043-qlh`, Ready)
and `vja-nightly` (generation 42, Ready). The Job retains `ANTHROPIC_API_KEY`, no model-route overrides,
`timeoutSeconds=21600`, and `maxRetries=0`; therefore extraction remains Haiku 4.5 and matching remains Sonnet
4.6 at medium effort. Post-deploy `/api/health` returned 200 and anonymous `/api/postings` returned 401. No
manual Job run was started—the once-daily fetch invariant and July 17 observation baseline remain intact.

**Clear-chat handoff:** freeze production changes and audit the July 17 scheduled run read-only for D-088
snapshot/churn behavior, D-089 score clamps + persistence/no rebilling, D-090 LiteLLM model/usage/cache/catalog
cost/errors, and D-086 runtime/one-attempt/digest delivery. Prefer keeping the freeze through July 18's second
D-088 night. `docs/19` is the plan of record. Exactly **three new-model steps** remain: Block 2 expanded eval +
CI repair → Block 3 extraction selection/cutover → Block 4 matching selection/cutover. Block 5 `no`-output is a
separate post-selection optimization. Block 2 begins only after Hayden approves fixtures, rubric, thresholds,
candidates, repetitions, and spend cap.

## 2026-07-16 — D-090 LiteLLM provider boundary built at Anthropic parity

**Built on `feat/litellm-provider-boundary` (uncommitted; Hayden owns commit/PR):** Layer-2 extraction
and matching now depend on the typed `vja.llm` boundary rather than Anthropic SDK response types.
Embedded LiteLLM owns request transport, Pydantic parsing, mutually-exclusive uncached/cache token
normalization, catalog cost, actual upstream model, latency, and request ID. Call-time routes default to
`VJA_EXTRACT_MODEL=anthropic/claude-haiku-4-5` and
`VJA_MATCH_MODEL=anthropic/claude-sonnet-4-6`; matching keeps `VJA_MATCH_EFFORT=medium`, which LiteLLM
maps to Anthropic adaptive thinking + output effort. Prompts, schemas, max tokens, cache breakpoint,
D-089 score clamp, per-posting isolation, idempotency, DB schema, credentials, and production models are
unchanged. The direct Anthropic dependency and hardcoded Sonnet/Haiku price tables are gone; stage totals
use returned catalog cost, persist the response's actual model, and fail on absent usage/pricing, false `$0`,
or unsupported/dropped parameters. No router, fallback, proxy, or new retry policy was added.

**Plan/docs + verification:** D-090 and new `docs/19` record the accepted pre-beta/Robotics sequence:
observe D-088 July 17/18 → provider boundary → expanded multi-model eval + missing CI eval repair →
extraction cutover → matching cutover → chosen-model `no`-output optimization. The existing CI/eval policy
drift is now explicit rather than falsely documented as live. Offline suite **552 passed, 20 opt-in
deselected**; the real Anthropic parity eval through LiteLLM passed **3/3**; ruff format/check, mypy (132
source files), import-linter (1 kept / 0 broken), `uv lock --check`, `git diff --check`, and the production
`linux/amd64` Docker image build are green. Docs: INVARIANTS, CLAUDE, `.env.example`, docs/08/09/12/15/17,
GCP runbook, beta ledger, and the doc map. **Next:** Hayden reviews/commits/PRs Block 1; observe the July 17
D-088 run; Block 2 starts only after Hayden approves its fixtures, rubric, thresholds, candidates, run count,
and spend cap.

## 2026-07-16 — D-089 match-score boundary guard built after read-only production shakeout

**Read-only shakeout on clean `main`:** the July 16 Cloud Run execution succeeded once in 1h57m54s under
the D-086 six-hour/zero-retry policy; all seven digests sent, the Scheduler is enabled for 06:00 America/
Chicago, `/api/health` returned 200, and anonymous `/api/postings` returned the required 401. It was **not**
a D-088 validation run: execution `vja-nightly-8wdb2` started at 06:00 CT and PR #88 merged at 06:41 CT.
The Job now points at `rolefeed:54181f8`, so July 17 and 18 are D-088 observation nights 1 and 2. The one
isolated fetch failure was GE Vernova (`missing 'title'`); fail-closed behavior preserved its prior rows.

**Concrete bug found and fixed on `fix/match-score-boundary` (uncommitted; Hayden owns commit/PR):** Sonnet
returned an otherwise-valid structured match with a negative score 26 times that morning (`-1` ×25, `-5`
×1), and the same signature appeared 56 times across seven execution dates since July 7. The installed
Anthropic SDK explains the contract gap: it preserves `integer` in the server schema but moves unsupported
numeric bounds into descriptive text; local Pydantic then rejected the paid response, so no match or usage
was saved and the pair retried nightly. D-089 implements Hayden's approved policy: real integers outside
0–100 clamp to the nearest boundary with a warning before strict final validation; wrong types and every
other malformed output still fail, with no corrective LLM call. Regression tests were observed red first
(unit validation + pipeline persistence/idempotency), then green.

**Adjacent evidence, deliberately not folded into this fix:** recent Workday snapshots intermittently fail
closed on source rows missing `title`/`externalPath`; do not re-hit a board after the nightly's once-daily
fetch. `pipeline_runs.started_at == finished_at` under the injected nightly timestamp, and the killed July 14
attempt persisted $0 despite logs showing $3.4071 before termination; both feed the already-planned minimum
Job monitoring/scaling work. **Verification:** focused suite 12/12; full default suite **543 passed, 20 opt-in
deselected** after hardening one logging assertion against Alembic's test-only logger disabling; ruff format/
check, mypy (130 source files), import-linter (1 kept / 0 broken), `uv lock --check`, and `git diff --check` are
green. Docs: D-089, INVARIANTS, docs/15, docs/17, and CLAUDE reconciled. **Next:** Hayden reviews/commits/PRs,
then observe the July 17 D-088 production run.

## 2026-07-15 — D-088 snapshot-integrity churn guard built; Message Batches deferred

**Built on `fix/snapshot-completeness-churn` (uncommitted; Hayden owns commit/PR):** the
cost/churn audit found a concrete completeness vulnerability without overclaiming it as the sole
cause of production churn. Workday, iCIMS, Oracle, SmartRecruiters, and Radancy now read the source
total on every page, fail on total drift, and require an exact final mapped count. The shared
`sync_employer` guard rejects duplicate ATS `external_id` values before opening the DB transaction,
so an inconsistent employer snapshot makes zero posting mutations. Changed employers now log
fetched/new/reopened/updated/closed/unchanged counts; failures log vertical/employer/provider +
reason. No schema, migration, fuzzy identity, production repair, bookend/double-fetch, or Batch API
was added. D-088 defers Anthropic Message Batches because the up-to-24-hour latency conflicts with
time-sensitive postings; re-measure after two production nights and reconsider extraction-first
batching only if spend remains material.

**Radancy live defect exposed and corrected:** the existing `CurrentPage`/`RecordsPerPage` request
was ignored by NextEra's board, silently repeating page 1 until 300 mapped rows crossed a reported
290 total. The new exact-count guard caught it in the live gate. The board's own `startrow` offsets
returned disjoint pages (0/25/50/275) and an exact 290-row snapshot, so the fetcher now follows that
contract. Regression-first coverage pins total drift and under/over-count failures across all five
providers, `startrow` pagination, duplicate-ID zero-mutation behavior, and employer-level logging.

**Verification + docs:** full default suite **540 passed, 20 opt-in deselected**; ruff format/check,
mypy (130 source files), import-linter (1 kept / 0 broken), `uv lock --check`, and
`git diff --check` green after the final one-line lint correction. Targeted live smoke is **8/8**:
Workday/PJM, iCIMS/Garmin, Oracle/Southern Company list+detail, SmartRecruiters/Vitol list+detail,
and Radancy/NextEra list+detail. D-088, INVARIANTS, docs/05, docs/08, docs/15, docs/17, and CLAUDE
are current. **Next:** Hayden reviews, commits, and PRs; after deploy, observe two nightly runs using
the new employer-level churn lines before deciding whether any anomaly-confirmation follow-up is
needed. The user-supplied cost CSVs under untracked `private/` remain untouched and must not be
staged.

## 2026-07-15 — D-085 résumé-reupload abuse guard built

**Built on `fix/resume-reupload-abuse-guard` (uncommitted; Hayden owns commit/PR):** identical
extracted résumé content now keeps the existing 202/profile response without refreshing the
backfill-progress stamp or scheduling another backfill (and succeeds even when the global LLM
ceiling is exhausted). The first upload remains allowed. Each accepted changed résumé atomically
claims new nullable `users.last_resume_reupload_at`; another change inside the rolling 24-hour
window returns 429 with an integer-seconds `Retry-After`. The per-user row lock serializes concurrent
production/Postgres uploads; reverting to an older stored content version still counts as changed
and refreshes the clock. Existing one-vertical, profile-version audit, five-day backfill, nightly
healing, and frontend 202 commit-point contracts remain intact.

**Regression + migration + gates:** after correcting a test-fixture syntax typo, the focused tests
failed against the old behavior (identical content hit the daily-budget 429; a second change was
accepted), then passed. Migration `c4e8a7d9132f` upgrade + downgrade were rehearsed on a populated
SQLite DB with a profile FK to the user; rows survived both directions. Full default suite **528
passed, 20 opt-in deselected**; ruff format/check, mypy (52 source files), import-linter (1 kept / 0
broken), `uv lock --check`, and `git diff --check` green. Frontend/eval gates are path-filtered out.
Docs/04, docs/11, docs/15, docs/17, INVARIANTS, D-085's implementation note, and CLAUDE are current;
this entry also supersedes the stale prior top entry's awaiting-PR state because landing PR #86 is
merged. **Production migration complete:** Hayden explicitly targeted Neon (`PostgresqlImpl`) and
verified `a06b99424c4c → c4e8a7d9132f (head)` on 2026-07-15. **Next:** Hayden reviews,
commits, and PRs this branch.

## 2026-07-14 — D-085 landing-copy follow-up built

**Built on `feat/landing-copy` (uncommitted; Hayden owns commit/PR):** completed the first accepted
post-PR-3 follow-up. The hero now promises **technology jobs** rather than engineering jobs; the three
cards each state a distinct user benefit (overlooked employers · fresh opportunities · honest fit);
How it works now owns the actual curate → fetch/diff/verify → extract/match/deliver mechanics. Hayden's
new founder description is preserved and its contact email is a direct link. Per Hayden's explicit
decision, the three-vertical/Robotics promise stays on the landing because the Robotics vertical will
be added; the config/picker work remains a separate beta-exit item.

**Regression + docs:** focused landing expectations failed against the old headline/cards/steps/contact
before the implementation, then passed. Full frontend eslint + TypeScript + Vitest **95/95** + production
build are green. No backend, API, schema, ADR, or live invariant changed. Docs/15 and docs/17 now correctly
record onboarding PR 3 as merged #82 (superseding their stale awaiting-review text); docs/16 and CLAUDE
record the completed D-085 copy pass. Browser visual verification was not completed; Hayden reviews the
rendered copy in the PR. **Next:** Hayden reviews/commits/PRs; then the D-085 résumé-reupload abuse guard
gets its own backend/security branch.

## 2026-07-14 — Post-beta feature slate decided + roadmap written (D-087)

**Planning/docs only on `docs/post-beta-feature-roadmap` (uncommitted; Hayden owns commit/PR); no
application code changed.** A feature-reasoning session: Hayden set the frame (new = niche-vertical
grouping, better = AI matching, proven = job-finding tool), benchmarked jobright.ai (freshness +
salary are the standouts; most else is clutter), and set the rule — adapt 1–2 proven features, add
something novel, resist clutter. Every scope decision ran through him.

**Accepted slate (D-087, plan of record `docs/18-post-beta-features.md`, builds only after the D-085
beta exit):** F1 intraday freshness + instant alerts (~1–2h fetch→diff→extract→match polls, alert-on-
arrival with idempotency marker, digest stays nightly; supersedes D-005's once-daily fetch **at build
time only**) · F2 salary (Phase A surfaces the stored-but-never-shown `comp_min/max/raw`, fill-rate
query first; Phase B = public DOL H1B/LCA enrichment; **Glassdoor/Indeed documented closed** — no open
API, scraping violates ToS + politeness policy) · F3 recurring-gaps report (aggregate `matches.gaps` →
"the #1 thing between you and strong_yes") · F4 per-employer lifespan/urgency intel (the D-009
promise). **Key dependency surfaced: the D-085 churn diagnosis now blocks F1 + F4** (alert spam /
corrupted medians). Sequence: churn fix → F2A → F4 → F1 → F3, F2B parallel. Rejected: YOE flags,
networking matches, autofill apply, applicant counts. Also verified the prior top entries' pending
branches merged (#83 SPAN/Brattle, #84 timeout guard) — main is clean.

**Docs updated:** new `docs/18` · D-087 · CLAUDE (roadmap bullet + doc map) · docs/15 (churn item
gates two roadmap features; post-exit pointer). INVARIANTS untouched — no live rule changed.
**Verification:** docs-only diff, human-read + stale-phrase scan; ADR id confirmed next-free; code
gates path-filtered out. **Next:** Hayden reviews/commits/PRs; beta-exit work (docs/15) continues
first — the slate starts only after exit, churn diagnosis leading.

## 2026-07-14 — Nightly duplicate-digest timeout guard built (D-086)

**Production diagnosis (read-only):** execution `vja-nightly-zvw6s` started under the standing Cloud Run
Job policy (`timeoutSeconds=7200`, `maxRetries=1`). Attempt 0 completed aviation Layer 2 and sent both
aviation digests, then Cloud Run killed it at exactly 7,200 seconds while grid was still running. Attempt 1
restarted the entire command, sent aviation again, then completed grid. Neon confirmed no duplicate active
profiles; Kanaga's single grid profile had 25 backfill + 154 nightly matches and one successful 28-role
digest. The duplicate was task retry, not signup/profile duplication.

**Built on `fix/nightly-timeout-duplicates` (uncommitted; Hayden owns commit/PR):** `ship.sh` now reasserts
a **21,600-second (6h) timeout + zero automatic retries** on every Job update; the cutover/create runbook
uses the same flags. An offline deploy-contract regression pins both paths; `bash -n` and installed-gcloud
flag discovery verify the shell/CLI surface. D-086, INVARIANTS, docs/15, and CLAUDE record the incident,
current rule, and durable per-execution delivery-idempotency follow-up. Full default suite **524 passed,
20 opt-in deselected**; ruff format/check, mypy (130 source files), import-linter (1 kept / 0 broken), and
`uv lock --check` green. Frontend/eval gates are path-filtered out. **Next:** Hayden reviews/commits/PRs;
merge-to-main CD applies the new Job policy. Production remains 2h/one-retry until that deploy completes.

## 2026-07-14 — SPAN + The Brattle Group curated seed onboarding built

**Built on `data/add-span-brattle` (uncommitted; Hayden owns commit/PR):** added SPAN and The Brattle Group
to the `grid_power_software` curated seed as active, verified Layer-1 employers. SPAN is Tier 5 / Grid & Clean
Energy Tech on Ashby slug `span`; Brattle is Tier 4 / Energy Economics & Consulting on Greenhouse slug
`thebrattlegroup`. Both use the existing slug-derived generic endpoints — no source code, explicit endpoint,
schema, or vertical-scope change. Seed fetchable coverage moves **49 → 51** after import. This entry also
supersedes the now-stale prior top entry's “awaiting review/merge” state: onboarding PR 3 merged as #82 before
this branch began.

**Validation + gates:** live application-fetcher validation returned **34 SPAN** and **21 Brattle** postings
with valid apply URLs. A seed-import regression pins both mappings/statuses plus the new Greenhouse/Ashby and
total counts. Focused import suite **8/8**; full default suite **523 passed, 20 opt-in deselected**; ruff format
+ lint, mypy (129 source files), import-linter (1 kept / 0 broken), `uv lock --check`, and `git diff --check`
green. Frontend/eval gates are path-filtered out. **Next:** Hayden reviews/commits/PRs; after merge, explicitly
targets Neon and runs `uv run vja-import-employers data/seed/employers_seed.csv`; the following nightly fetch
ingests both boards.

## 2026-07-13 — Onboarding PR 3 built: welcome tour + dashboard clarity (D-082/D-085)

**Built on `feat/onboarding-tutorial` (frontend-only; awaiting Hayden review/commit/PR):** a four-slide,
first-dashboard welcome dialog with Skip/Back/Next/Start exploring, Escape/backdrop dismissal, browser-local
`rolefeed.tour.seen` persistence, and an auth-aware `?` nav reopen affordance. Dashboard controls now read
**Matched for you / All in-scope** and **New today / 1 week / 2 weeks / All open**, with exact native-title
semantics. The table-use/read-only/nightly guide moved above results. `aviation_software` now renders as
**Aviation Technology** on the dashboard, locked résumé-update screen, and landing vertical card while its
config/API/DB key remains unchanged and hidden from user-facing UI; the broader landing rewrite remains queued.

**Regression-first + verification:** the initial focused expectations failed against the old UI (5 files,
8 tests), then the implementation and remaining stale upload-label assertions were brought green. Frontend
eslint + `tsc -b --noEmit` + vitest **95/95** + production build pass. Headless Chrome walked all four slides
at 1440/720 and captured the post-dismiss dashboard at both widths: no overflow, console/page errors, or raw
slug; guide position and all control labels verified. Docs/17 PR-3 checklist + DoD, docs/15 active ledger,
INVARIANTS dashboard contract, and CLAUDE roadmap reconciled. **Next:** Hayden reviews/commits/PRs; after
merge, continue the D-085 follow-up queue as separate branches (landing copy, reupload guard, churn diagnosis,
minimum Job monitoring) alongside UI/UX, company-database work, and beta feedback.

## 2026-07-13 — Beta-hardening ledger reconciled + PR-3/follow-up scope locked (D-084/D-085)

**Planning/docs only on `docs/beta-hardening-reconcile`; no application code changed.** Reconciled the
post-merge state that the prior top entry missed: onboarding PR 1 #78, PR 2 #79, and the D-083 auth/schema
hotfix #80 are merged on clean `main`; docs/17's PR-1 checklist is now checked and PR 3 is the only remaining
onboarding block. PR-3 copy is signed off: four welcome slides; Matched for you / All in-scope; New today /
1 week / 2 weeks / All open; Skip/Back/Next/Start exploring; the table-use/read-only/nightly hint moves above
the results; `aviation_software` displays as **Aviation Technology** while the internal slug stays stable.

**Discovery Day 2 closed (D-084):** multiple complete Terra reports show ~$0.77–$0.99 per run; ledger +
human review tooling exist. Hayden chose manual/on-demand discovery permanently — do not create a recurring
Job. Proposal activation/pruning continues as company-database curation, not unfinished agent work.

**Accepted post-PR-3 queue (D-085):** separate landing-copy pass (benefits vs mechanics vs founder story;
outward software→technology vocabulary) · separate résumé abuse guard (identical content = success/no
backfill; one changed reupload/user/rolling 24h → 429 + Retry-After) · minimum Cloud Job monitoring · robotics
promise/config resolution · scaling assessment + no-code activations. Read-only production logs supplied the
missing D-069 evidence: July 8–10 held at 44 fetched employers yet produced 343–654 new and 384–592 closed
postings nightly; extraction dominated ~$0.63–$1.65/night while matching usually hit 84–93% cache. **Decision:
diagnose identity/diff churn before Batch API; re-measure, then batch extraction first if still material.**
After onboarding, the main loops are UI/UX, employer databases, and beta-user feedback; scheduled discovery
and the endless fetcher tail are not beta-exit gates.

**Docs updated:** D-084/D-085 · INVARIANTS discovery schedule · docs/14 run policy · docs/15 closeout/exit
line · docs/16 landing follow-up · docs/17 merged state + PR-3/follow-ups · CLAUDE roadmap/doc map.
**Verification:** human-read docs diff + stale-phrase scan; no code gates triggered. **Next:** Hayden reviews,
commits, and PRs this docs branch; then branch from updated `main` for onboarding PR 3 implementation.

## 2026-07-13 — Onboarding PR-2 prod incident recovered + auth/schema hotfix built (D-083)

**Incident:** after PR #79 deployed, successful Google login appeared to return an existing user
to Landing. Cloud Run logs proved OAuth was not the failure: every `/api/me` probe on revision
`rolefeed-00032-5bf` returned 500 because production Neon lacked
`profiles.backfill_started_at`. The migration had been run as bare `uv run alembic upgrade head`;
Alembic does not load `.env`, so it upgraded default local SQLite. `AuthProvider` then hid the 500
by collapsing every probe failure to logged-out. **Recovered prod:** Hayden explicitly exported
the Secret Manager Neon `VJA_DATABASE_URL` and applied `a06b99424c4c`; read-only log verification
then showed `/api/me` 200 twice on the same revision (with the expected anonymous 401 separate).

**Built on `fix/onboarding-auth-failure`:** D-083 production schema-readiness guard — the image
sets `VJA_ALEMBIC_INI=/app/alembic.ini`; FastAPI lifespan rejects a known older DB revision before
Cloud Run readiness, while an unknown/newer DB revision remains allowed for old-image rollback.
Manual pre-merge migrations stay policy. Frontend auth now distinguishes thrown `/api/me` failures
from 401 and renders a retryable account-load error instead of Landing; `/login` is logged-out-only
and routes an existing session to onboarding/dashboard. Audit fix: `ProfileCreated.resume_version`
is now the API's real string type (the stale no-status comment also corrected). The low-probability
duplicate-backfill-on-timeout issue was deliberately left out of this focused PR.

**Verified:** regression tests were observed red first (auth failure → anon/Landing, unguarded
`/login`, missing schema-guard module), then green. Full backend: **522 passed**, 20 opt-in
deselected; ruff format/check, mypy (52 source files), import-linter (1 kept / 0 broken), and
`uv lock --check` green. Frontend: eslint + `tsc --noEmit` + vitest **89/89** green. Docs: D-083,
INVARIANTS, docs/17 incident note, CLAUDE/README, and the GCP deploy runbook now spell out that
Alembic needs an explicit production URL plus `current → upgrade → current`. **Next:** Hayden
reviews/commits/opens the PR; after merge, continue onboarding PR 3 (welcome slides + toggle copy).

## 2026-07-13 — Onboarding PR 2: backfill-status signal built (branch `feat/backfill-status`)

**PR 1 confirmed merged (#78) before starting.** The D-082 matching-progress signal, per docs/17.
Two refinements over the sketch (recorded in docs/17; D-082 governs): the `started` stamp lives in
the **upload endpoint** (pre-`add_task` — the 202 returns before the background task runs, so
stamping only in `run_backfill` would race the SPA's immediate probe), and **staleness is derived
server-side** (one clock, unit-testable; client stays dumb).

**Landed:** migration `a06b99424c4c` (nullable `profiles.backfill_started_at`/`_completed_at`;
additive; rehearsed on a local copy — **run on Neon before merge**, D-068) · `db/profiles.py`
stamp writers + `derive_backfill_status` (done ⇔ `completed >= started`, the reupload-ordering
rule; `running` staler than 10 min → done, the crash guard; never-stamped → null) ·
`run_backfill` stamps completed in a `finally` (lands even when every candidate fails) ·
`/api/me` profile gains `backfill_status` · Dashboard: status-driven ~10s poll (silent `/api/me`
re-probe + postings refetch; survives refresh, fires on reupload; `justOnboarded` router state no
longer read), "Matching in progress — results update live" banner shown above existing rows too
(the reupload case), matched empty states split into running ("Matches appear here as they're
computed") vs done ("No matches yet — full results after tonight's run").

**Verified:** backend gates + pytest **518** (+12: stamp round-trip, six derivation cases,
completion-on-failure, /api/me per state, endpoint-stamps-before-schedule) · frontend eslint +
tsc + vitest **85/85** (Dashboard suite reworked) · live headless-Chrome walkthrough on the
migrated DB copy (throwaway secret, zero LLM): fresh signup → done state; banner over real rows;
**the running→done poll flip observed live** — stamped `completed` mid-session, banner cleared on
the next tick without a reload; no console errors. Docs: INVARIANTS D-057 poll line rewritten
(+ commit-point line), docs/17 PR-2 ticked. **Next:** Hayden runs `alembic upgrade head` on Neon,
then reviews/commits/PRs (shots on the artifact page); then PR 3 (welcome slides + toggle copy —
copy sign-off at execution).

## 2026-07-13 — Onboarding overhaul scoped (D-082, docs/17) + PR 1 (upload-flow fixes) built

**Trigger:** the first real private-beta user hit onboarding friction (outdated résumé → confusing
reupload, "stuck on the upload page", ambiguous toggles) — the fresh-signup path had never been
walked. Exploration found a root cause for every complaint: the submit's only feedback was the
button label; the post-202 `/api/me` refresh flips global `loading` (the whole route blanks to
"loading…" mid-submit — the literal stuck report) with no timeout and two races (spurious error
after a successful upload; profile-visibility race bouncing back to `/onboarding`); an edited
résumé's new `resume_version` orphans all prior matches (matched view near-empty till the nightly);
no backfill status exists client-side; `/upload` had no back nav; no tutorial affordance. **Scoped
with Hayden (D-082, plan docs/17, 3 PRs):** PR 1 bug-fix tier → PR 2 backend backfill-status signal
(profile stamps + `/api/me`, supersedes D-057's no-status clause; INVARIANTS updates when it lands)
→ PR 3 welcome-slides tutorial + toggle clarity. Reupload affirmed = instant 5-day backfill +
nightly heals (full re-match at upload rejected: ~$3/event vs the $5 ceiling). Groups with the
docs/15 Day-3 shakeout.

**PR 1 landed (branch `fix/onboarding-upload`, frontend + one backend test):** upload busy notice
+ spinner; 30s `AbortController` timeout; friendly timeout/network error copy (no raw
`TypeError`); the **commit-point rule** — after 202 the upload never presents as failed:
`refresh()` now returns `Me` + takes `{silent}` (no loading flip), Upload retries the probe
bounded (4×, backoff) then navigates, last-resort "résumé uploaded — open your dashboard" state;
`/upload` back link; honest reupload blurb; Dashboard keeps previous data on poll ticks (no more
10s "loading…" flash); backend regression test pins the API-level double-upload path (same bytes
idempotent · edited bytes → new active version + old deactivated · backfill per accepted upload).

**Verified:** eslint + `tsc -b` + vitest **83/83** (was 73) · backend ruff/format/mypy/
import-linter/pytest **506 passed** · full fresh-account walkthrough in headless Chrome against
the served build on a **copy** of the local DB (throwaway secret, `VJA_BACKFILL_MAX_POSTINGS=0`,
bogus Anthropic key — zero LLM spend): onboarding → delayed-POST busy state → auto-land on
/dashboard with poll notice; aborted-POST friendly error; back-link click navigated; no overflow
at 1440/720. Before/after shots on the artifact page. Docs: D-082 · docs/17 (new) · docs/15 Day-1
ticked done + Day-3 gains the onboarding item · CLAUDE.md Phase-BH line + doc map. **Also
corrected:** WORKLOG/CLAUDE.md said UI PR 3 was pending merge — all four UI PRs (#74–77) are in
fact merged on `main`; the D-080 block is live. Robotics vertical config still absent (landing
advertises it; picker can't offer it) — Hayden's, pre-beta. **Next:** Hayden reviews/commits/PRs
PR 1; then PR 2 (status signal + migration) and PR 3 (tutorial) per docs/17.

## 2026-07-13 — UI rework PR 3: dashboard rework built (closes the D-080 block)

**PR 2 confirmed merged (#76, live in prod) before starting; branch `feat/ui-dashboard`.** Layout
decisions ran through Hayden first: rationale snippet = **two-line row** (muted truncated line
under the title, not a sixth column) · detail = **overlay panel** (Linear peek over the table,
not a docked split).

**Landed (frontend-only):** row-level match info — verdict/score chips stay, plus the snippet
line and a **verdict-colored spine** per row. Inline expansion deleted → new `PostingPanel`
(`role="dialog"`: title/company, meta card, full rationale, fits/gaps, apply CTA, ✕; Esc /
click-away / row-switch close; selection keys on `posting_id` so refetches that drop the posting
close it naturally). **Sortable headers** (natural-direction first click, flip on second, nulls
last both ways; default = freshness-desc, the server order) + **filter-as-you-type** over
company/title/location with `X of N` count — both pure client-side (`postingsView.ts` helpers;
`/api/postings` already returns the full set, contract untouched). Subbar search input, notice
cards, footer copy fixed. Bonus inside the table CSS (not a mobile pass): `minmax` title column
+ `overflow-x: auto` — narrow viewports scroll the table instead of the pre-existing 720px
column-crush. `postingsPath` mapping, D-057 poll, and routing pinned untouched by the existing
tests.

**Verified:** eslint + `tsc -b --noEmit` + vitest **73/73** green (was 57; new `postingsView` +
`PostingPanel` suites, reworked table/dashboard tests); headless-Chrome before/after shots at
1440 + 720 against the served build on the local sqlite DB (throwaway session secret) — panel
open, filter active, sorted-by-score, cleaned view, landing (shared `.cell-*`/`.verdict-*`
classes regression-checked, hero mock unchanged); no page overflow, no new console errors (the
landing's anon `/api/me` 401 log predates this PR). Docs: docs/16 PR-3 section ticked — the
**whole D-080 4-PR block is now built** (no new ADR, no INVARIANTS change). **Next:** Hayden
reviews/commits/opens the PR (shots on the artifact page); after merge the docs/15 Day-1 UI
item closes and the beta-hardening week moves to its next item.

## 2026-07-13 — UI rework PR 2: login + onboarding polish built

**PR 1 confirmed merged (#75) before starting; branch `feat/ui-auth`.** Decisions ran through Hayden
first: **centered** auth-card layout (/login, /onboarding, /upload) · login card = mark + heading +
**3 benefit lines** + Google CTA · vertical display copy = a frontend **slug→{name, blurb} map**
(`verticalCopy.ts`, reusing the landing's vertical copy; `/api/verticals` returns slugs only and the
API is frozen this block) with a prettified-slug fallback so a new vertical renders without a
frontend release · **robotics pre-added** as `robotics_software`.

**Landed (frontend-only):** `Login.tsx` → auth card, **stale "browse without signing in" copy
deleted** (false since D-067) and pinned gone by a test. `Upload.tsx` → vertical choice as
descriptive radio-cards (visually-hidden native radios), drag-and-drop résumé dropzone (native DnD,
no new deps; selected-file state in mono), and guard-status error styling (friendly lead + server
detail; 409/413/422/429); update mode shows the locked vertical as a static card (display name +
mono slug). Two-mode logic, guards, and the D-057 success flow untouched (`App.tsx` not in the
diff). `theme.css` gains a scoped auth-page block; the dead 9.4 select/file-input rules removed.

**Verified:** eslint + `tsc -b --noEmit` + vitest **57/57** green (new: `verticalCopy` unit test,
card-pick submit, dropzone drop, 409 lead); headless-Chrome before/after shots at 1440 + 720 against
the served build on a scratch sqlite DB (sessions minted with a **throwaway** secret — the prod
`VJA_SESSION_SECRET` was never read) — file-selected + mocked-409 states driven live; no horizontal
overflow, no unexpected console errors. Docs: docs/16 PR-2 section ticked (no new ADR — D-080
governs; no INVARIANTS change). **Next:** Hayden reviews/commits/opens the PR (shots on the artifact
page); then PR 3 (dashboard rework) closes the block.

## 2026-07-13 — UI rework PR 1: Linear-style marketing landing built

**PR 0 confirmed merged (#74) before starting; branch `feat/ui-landing`.** Copy decisions ran through
Hayden first (from his business thesis): **hero = coverage-led** ("The engineering jobs the big boards
miss."), sections expanded to hero → stats band → three thesis pillars → how-it-works → verticals →
founder story → footer; brand stays **"Rolefeed"** (D-058, not the thesis's "RoleFeed"); **robotics is
listed as a served vertical** alongside aerospace + energy — Hayden's call, he's adding the vertical
config this week before beta. **Flagged:** `main` auto-deploys (D-068), so until that config lands the
live landing advertises a vertical the onboarding picker (`/api/verticals`, config-driven) doesn't
offer — merge timing is Hayden's.

**Landed (frontend-only):** `Landing.tsx` rewritten (19-line placeholder → full static marketing page;
only live element is the `loginUrl()` Google CTA; product visual = a CSS-built mini dashboard mock
mirroring `PostingsTable` markup on live v2 tokens, per docs/16 no-binary-asset rule). `theme.css`
gains a scoped `.landing` block (marketing type scale, the one DESIGN.md-allowed hero glow — reworked
to a centered bounded ellipse after the first cut caused horizontal overflow — stats band, card/step
grids that collapse via `auto-fit minmax`). New `Landing.test.tsx` pins the section skeleton, CTA href,
pillars, three verticals, and the no-auto-apply footer. `App.tsx`/routes/guards untouched.

**Verified:** eslint + `tsc -b --noEmit` + vitest **50/50** green; headless-Chrome screenshots at 1440
(before/after) + 720 (grid-collapse sanity) — no horizontal scroll, no unexpected console errors.
Docs: docs/16 PR-1 section ticked with the copy decisions recorded (no new ADR — D-080 governs; no
INVARIANTS change). **Next:** Hayden reviews/commits/opens the PR (before/after shots on the artifact
page); then PR 2 (login/onboarding polish, incl. the stale "browse without signing in" copy fix).

## 2026-07-12 — UI rework PR 0: design language v2 landed (Indigo · Inter; D-081)

**The D-080 screenshot sign-off ran first:** built the SPA, served it from the API against the **local**
sqlite DB (`.env` points at Neon — every command carried a `VJA_DATABASE_URL` override), minted a signed
session cookie with the server's own secret, and drove headless Chrome (playwright-core + system Chrome) to
render three candidate token sets **on the live dashboard with real data** via runtime style injection:
A Indigo·Inter / B Amber·Geist / C Violet·Space Grotesk, beside the v1 baseline. Published as a comparison
artifact; **Hayden picked A**.

**Landed (frontend-only):** `DESIGN.md` rewritten to v2 "premium dark product" (blue-tinted near-black,
indigo `#6e79d6`, Inter for UI with JetBrains Mono reserved for true data, soft `--shadow-raised`, radius
10/6, terminal motifs → don'ts). `theme.css` fully rewritten to the v2 tokens/type roles. Motifs retired in
code: `App.tsx` wordmark `$ rolefeed▮` → indigo mark + "Rolefeed" (Inter 600) + sentence-case nav;
`Dashboard.tsx` `//` notice prefixes dropped, `~/vertical` → tint chip, footer's decorative `↵ open` hint
(rows only respond to click) → "Click a row to expand"; `Upload.tsx` error prefix dropped.

**Verified:** eslint + `tsc -b --noEmit` + vitest **45/45** green; rebuilt and re-screenshotted
dashboard/landing/login/upload on v2 — coherent, no console errors. Docs: D-081, docs/16 PR-0 section
ticked. **Next:** Hayden reviews/commits/opens the PR-0 PR (before/after shots on the artifact page);
then PR 1 (Linear-style marketing landing) on the merged tokens.

## 2026-07-12 — UI rework scoped: Linear reference, design language v2, 4-PR block (D-080, docs/16)

**Planning-only session** for the docs/15 Day-1 item; every decision run through Hayden via questionnaire.
Locked: **reference = Linear** (the D-072 timeboxed pick); **design language v2 with everything on the
table** — softer/more premium dark; the orange accent, Space Grotesk/JetBrains Mono, and the terminal motifs
(`$` prompt, blinking ▮, `//comments`) are all up for replacement, with accent + font decided from screenshot
comparisons during PR 0; **full Linear-style marketing landing**; **dashboard rework** = sortable columns +
text filter + side-panel detail + match info surfaced at row level (verdict/score + rationale snippet visible
without a click). Explicitly out: mobile pass, keyboard nav. **Shape: 4 PRs, strict order** — PR 0 foundation
(DESIGN.md v2 + tokens + shell) → PR 1 landing → PR 2 login/onboarding (incl. the stale "browse without
signing in" copy fix) → PR 3 dashboard. All frontend-only: verified `/api/postings` returns the full filtered
set unpaginated (`db/postings.py:470`), so sorting/filtering is client-side and no API contract moves.

A `/design-sync` (claude.ai/design testing-ground) detour was considered and **skipped** — Hayden's call after
clarifying the sync is one-way repo→design-tool.

**Landed:** `docs/16-ui-rework-plan.md` (plan of record, per-PR scope + DoD), D-080, docs/15 Day-1 section
rewritten to point at it, CLAUDE.md Phase-BH line updated. No `frontend/` code this session; no INVARIANTS
change (no live cross-cutting rule moved — D-080 governs a build block). Also noted: WORKLOG's prior top entry
predated the Pinpoint PR merge — #72 is merged; its post-merge steps (Aireon #135 `set-ats`, Aurora Neon seed
import) still unrecorded. **Next:** Hayden reviews/commits this branch → PR 0 (token candidates + screenshot
sign-off) in a fresh session.

## 2026-07-12 — Generic Pinpoint fetcher + Aurora onboard (D-079)

**Live contract first:** verified the same public `GET {board}/postings.json` contract on canonical Aireon
(2 current jobs) and Aurora Energy Research's provider-backed custom domain (87). Both return one rich
`{"data": [...]}` response with stable top-level posting ids, absolute apply URLs, structured location, and
the full split job content inline; neither exposes a posted/updated date or a pagination total. Decisions were
run through Hayden before implementation: canonical slug derivation + explicit endpoint override for custom
domains, single-response fail-closed semantics, top-level `id` identity, and no lazy detail resolver (D-079).

**Built:** one generic `PinpointFetcher`; enum/endpoint registry/discovery validation wired. The clean `data`
list is authoritative (valid empty closes cleanly; malformed envelope/entry, duplicate ids, HTTP/non-JSON fail
loudly). Rich description/responsibilities/qualifications/benefits/compensation are joined for stable
`content_hash` invalidation while the untouched posting stays `raw`. Captured a sanitized two-posting fixture;
unit coverage pins mapping, custom-domain override, completeness/failure guards, identity, and content hashing.
Aurora moved config-only from `custom/layer2` to `pinpoint/verified`, taking curated-seed fetchability 48→49
(grid 33→34). No migration (`pinpoint` fits application-validated `VARCHAR(15)`).

**Verified:** full offline suite (**505 passed**, 20 opt-in deselected); Aireon live smoke (**1 passed**);
ruff format/check; mypy (51 source files); import-linter (1 kept / 0 broken); `uv lock --check`;
`git diff --check`. Docs updated: CLAUDE, D-079, INVARIANTS, specs 04/05, routing 07, discovery runbook 14,
beta plan 15, and seed README. **Next:** Hayden reviews/commits/opens the PR. After merge/deploy, run the
D-077 prod path in docs/14 for Aireon proposal #135, then import the curated seed against Neon for Aurora;
the next one-fetcher PR is the D-078 Radancy-variants extension.

## 2026-07-12 — Prod coverage audit (72 unfetched rows triaged) + Honeywell Oracle onboard + D-078 fetcher re-rank

**Read-only audit of Neon** (Hayden-commissioned; deliverable = chat report + runbook, no repo audit doc):
135 employers, **63 fetchable / 62 fetched** by run #18 (Hayden's remembered "71" not reproducible from
`pipeline_runs`). All 72 unfetched rows probed live — registry-fetcher validation (the `set-ats` ≥1-posting
gate) + careers-page signature detection. **Bucket 1 (no code, +8–9):** six discovery rows validate on
supported ATSs (ASI 26 · GridBeyond bamboohr 2 · CivilGrid ashby 6 · Emerald AI ashby `emerald-ai` 7 ·
AiDASH greenhouse `aidashinc` 12 · Aloft greenhouse `versaterm` 34 — parent-company board, Hayden's call);
runbook commands are in the audit chat, Hayden executes (D-077 path). **Bucket 2:** new-fetcher demand
re-ranked → **D-078** (Pinpoint → Radancy variants → JazzHR → Jobvite → Taleo; docs/07 ledger rewritten).
**Bucket 3:** ~30 dead-end rows (email-only/bot-blocked/EU/dead) — retire slate in the chat runbook.

**Landed this session (code/data):** Honeywell Aerospace seed-CSV flip `custom/layer2 → oracle_hcm/verified`
(canonical host `ibqbjb.fa.ocs.oraclecloud.com` found via the page's `og:image`, siteNumber `CX_1`; 1,455
postings live-validated; constructed apply `/job/{Id}` resolves 200). Curated-seed fetchable 47→48 (aviation
14→15, Oracle 1→2); seed-import test expectations updated. Activates when Hayden runs
`vja-import-employers` against Neon post-merge.

**Corrections/finds worth remembering:** (1) **Jeppesen (Boeing) is duplicate coverage** — the Boeing board
is already fetched (seed row `Boeing`); recommend CSV retire, Hayden's call. (2) **Con Edison's Oracle host
found** (`ejcu.fa.us6.oraclecloud.com`/`CX_1033`) but fails paginate-or-fail at exactly 61 of 62, twice —
bug-shakeout candidate, do not retire. (3) **Comply365/Vistair** validates on BambooHR (`vistairhr`, 11
postings) but has **no DB row** — the BambooHR entry's runbook step below can't run for it until it's added
(curated seed add or re-discovery). (4) Reliable Robotics / Ascend / Gridmatic boards are live but empty —
re-run `set-ats` when they post. (5) **Record gap:** the post-deploy activation sweep (Veryon/Trax/United
now `active` in prod) has no WORKLOG entry, and docs' coverage figure (66) had drifted from prod (63).

**Verified:** seed-import tests (7 passed) + full offline suite + gates (see PR). Docs: D-078 appended;
INVARIANTS build-order line replaced; docs/07 ledger 2nd edition + steps 12–17 + fixups rewritten; docs/15
Day-5 item 5 rewritten; CLAUDE.md Phase-8/BH lines updated. **Next:** Hayden reviews/commits → runs the
Bucket-1 runbook + seed import against Neon → Pinpoint fetcher build (D-078 #1).

---

## 2026-07-12 — Generic BambooHR fetcher + lazy detail resolver (D-076 block 4)

**Built:** one generic slug-derived `BambooHRFetcher` over the authoritative
`https://{slug}.bamboohr.com/careers/list` JSON response. `meta.totalCount` must exactly match the
single `result` list (valid zero is authoritative; malformed/incomplete/duplicate data fails closed);
`external_id = id`; titles are trimmed; public apply URLs are constructed; structured `atsLocation`
wins over legacy `location` and remote fallbacks. The list pass keeps descriptions absent. Lazy
`/careers/{id}/detail` resolution returns only `result.jobOpening`, never sibling application
`formFields`. `AtsType`, endpoint derivation, registry, extraction routing, and discovery validation
are wired with no company/vertical branches.

**Tests/evidence:** captured sanitized GridBeyond list/detail fixtures; covered normal + empty boards,
location/province/remote fallbacks, malformed envelopes/count mismatch, missing/empty IDs and titles,
duplicate IDs, HTTP/non-JSON failures, strict detail validation, endpoint derivation, registry wiring,
lazy extraction routing, and discovery validate-by-fetch behavior. The opt-in GridBeyond live list/detail
smoke passed (2 current openings at fixture/live-contract capture).

**Verified:** full offline suite (**484 passed**, 19 opt-in deselected); BambooHR live smoke (**1 passed**);
ruff format/check; mypy (50 source files); import-linter (1 kept / 0 broken); `uv lock --check`;
`git diff --check`; human-read scoped diff. Docs updated: CLAUDE, INVARIANTS, specs 04/05, routing 07,
beta plan 15, and seed README. No Alembic migration (`bamboohr` fits application-validated `VARCHAR(15)`),
no seed CSV change, and no new ADR (implements D-076/D-077).

**Next:** Hayden reviews/commits/opens the PR. Production coverage is unchanged by this branch. After merge
and deployment, verify the current production fetchable count, then use the D-077 runbook per proposal:
GridBeyond (`gridbeyond`) and Comply365 (`vistairhr`) each run through `list --provider bamboohr` →
`set-ats` (must return at least one job) → explicit `approve`; leave any zero-opening board parked.

---

## 2026-07-11 — Generic Phenom fetcher + United onboarded (D-076 block 3)

**Live contract first:** United's public page exposes `widgetApiEndpoint=https://careers.united.com/widgets`,
`locale=en_us`, and `country=us`. Verified minimal generic `refineSearch` and `jobDetail` POST bodies; current
list total = 147. Crucially, `jobDetail.jobSeqNo` accepts the stable list `jobId` directly, preserving D-076's
identity contract and the existing `(employer, external_id)` lazy-detail interface.

**Built:** one generic `PhenomFetcher`: explicit tenant base with required `lang`/`country` query config;
`refineSearch` pagination by `from`/`size`; stable-`totalHits` paginate-or-fail guard; `jobId` mapping with inline
apply/location/date; lazy full `jobDetail`. Registry + extraction routing wired. United moved config-only from
`custom/layer2` to `phenom/verified`; curated-seed fetchable coverage 46→47 (aviation 13→14). No tenant values or
vertical/company branches entered code.

**Tests:** captured sanitized United list/detail fixtures; pagination assembly, empty board, short fetch, changing
total, malformed envelopes, HTTP/non-JSON failures, required query config, required mapping fields, and stable-id
detail lookup. Opt-in United live smoke passed both full list + detail. No Alembic migration: `phenom` fits the
existing application-validated `VARCHAR(15)`; no-drift check passes.

**Verified:** full offline suite (**455 passed**, 18 opt-in deselected); Phenom live smoke (1 passed); ruff
format/check; mypy (49 source files); import-linter (1 kept / 0 broken); `uv lock --check`; `git diff --check`;
human-read scoped diff. Docs: data model/fetcher specs, INVARIANTS, docs/07 + docs/15 roadmaps, seed README, and
CLAUDE updated. No new ADR (implements D-076 and the accepted endpoint-query plan). **Next:** Hayden
reviews/commits; after deploy, import the seed into Neon to activate United (+1 live), then BambooHR.

---

## 2026-07-11 — Paylocity fetcher + D-077 correction/activation tooling built

**Fetcher:** added generic explicit-endpoint Paylocity support over the server-rendered
`window.pageData.Jobs` payload (single-response false-closure guard; `JobId` identity; constructed direct apply
URL; structured location/date) plus lazy public-detail extraction. Captured sanitized Veryon list/detail fixtures;
the opt-in live smoke passed both list + detail against the current board. Registry, extraction routing, and
discovery provider-host markers are wired. No seed employer was added: the four waiting rows remain discovery
proposals until the post-deploy review runbook.

**D-077:** regression-first fixed parked (`approved`) re-approval; `vja-review list --provider` finds note evidence
or corrected types; `set-ats` accepts only supported ATSs, validates ≥1 live posting before an atomic ATS/verification
write + audit note, preserves status, and refuses active/retired rows. Activation remains the explicit `approve`
step. Tests pin success, zero/fetch failure no-write behavior, lifecycle guards, provider filtering, CLI composition,
and audit metadata.

**Schema correction run through Hayden:** no Alembic migration. Inspection proved ATS values are application-
validated `VARCHAR(15)` (`native_enum=False`, `create_constraint=False`), not the CHECK-constrained enums the docs
claimed; `paylocity` fits the existing column. Corrected `db/schema.py` + docs/04. Alembic no-drift check passes.

**Verified:** full offline suite (**436 passed**, 17 opt-in deselected); Paylocity live smoke (1 passed); ruff
format/check; mypy (48 source files); import-linter (1 kept / 0 broken); `uv lock --check`; CLI help;
`git diff --check`. Docs: current rules/specs + D-076/D-077 roadmaps/runbook updated; no new ADR (implements accepted
decisions; schema text was a factual correction). **Next:** Hayden reviews/commits; after deploy, correct + approve
the waiting Paylocity proposals via docs/14, record the resulting live coverage, then build Phenom (United).

---

## 2026-07-11 — Southwest + Thales onboarded through existing Workday fetcher (D-076 block 1)

**Config-only coverage win:** live-verified the two Phenom-skinned Workday boards before changing data:
Southwest `swa:wd1:external` returned 47 open jobs; Thales `thales.wd3`/`Careers` returned 2,000 global jobs.
Flipped both aviation seed rows from `custom/layer2` to `workday/verified` with explicit cxs endpoints — no
fetcher code and no new decision. The curated-seed fetchable count moves 44→46; the discovery-expanded live
baseline moves **64→66** once Hayden imports the seed into Neon.

**Tests/docs:** seed-import expectations now pin 46 total / 13 aviation / 22 Workday; seed README, docs/07,
docs/15, and CLAUDE roadmap updated. Verified: targeted seed-import tests (7); full offline suite (**409 passed**,
16 opt-in deselected); ruff format/check; mypy (47 source files); import-linter (1 kept / 0 broken);
`uv lock --check`; `git diff --check`. **Next:** Hayden reviews/commits, then runs `vja-import-employers`
against Neon; next PR is Paylocity + D-077 review correction/activation tooling.

---

## 2026-07-10 — Fetcher roadmap re-ranked by discovery demand (D-076; docs-only, beta-hardening Day-5 prep)

**Planning session — deliverable is the plan, no fetcher code.** Built the demand-ranked "which ATS next" list
Hayden asked for after the Terra runs skewed Paylocity-heavy.

**Evidence gathered:** (1) per-candidate resolver JSON across the nine `data/discovery_reports/` files (not raw
mentions — the prompt's provider list pollutes those): **Paylocity #1 unsupported (4 proposals** — Veryon, Trax
+ 2 grid), JazzHR 2, BambooHR 2 (incl. GridBeyond), singleton tail (Kula/Rippling/Gusto/TriNet/Trakstar/
Pinpoint), and 8 candidates on already-supported ATSs needing no work. (2) **Live probes:** Southwest + Thales
are **Workday under their Phenom skins** (`swa:wd1:external` cxs-verified, 57 jobs; `thales.wd3`/`Careers`) —
config-only onboards, killing 2 of Phenom's 3 expected wins; **United is the only real Phenom need** (Taleo
under; `/widgets` refineSearch paginates on `totalHits`, 155 jobs, `jobDetail` lazy detail); **Paylocity is an
easy build** (complete embedded `window.pageData` JSON, single-response, `JobId`, lazy detail; the v2 feed API
200s but is empty — not the data path); **BambooHR trivial** (`/careers/list` single-response JSON).

**Decisions run through Hayden (→ D-076):** order = Workday configs (SWA/Thales) → Paylocity → Phenom (United)
→ BambooHR → JazzHR probe/singletons; ledger lives in docs/07 (Day-2 "coverage ledger" first edition) + docs/15
Day 5 rewritten, no new doc; Getro/YC portfolio boards are not fetcher targets (park; later non-employer
`sources`). Host-marker hardening (paylocity/kula/gusto/rippling/trinet_hire/trakstar/pinpoint/phenom) rides
along with the builds.

**Second decision, same session (→ D-077):** Hayden flagged misresolved proposals (real Greenhouse companies
parked `unknown`) and the missing "new fetcher shipped → activate its waiting proposals" path. Reading
`review.py` also surfaced a real bug: **`approve` refuses parked (`approved`) rows**, contradicting its own
docstring + D-071. Decisions run through Hayden: corrections go through `vja-review` — never raw SQL, never
CSV-graduation (provenance) — via a new **`set-ats`** subcommand (validate-by-fetch before stamping, status
untouched) + **`list --provider`** (the evidence sits in notes, not `ats_type`, per D-074); the sweep is a
composed runbook (docs/14), not a batch command; the parked-re-approve bugfix rides along (regression test
first). No interim SQL — the misresolved rows stay inert until the tooling ships **with the Paylocity block**.

**Docs:** D-076 + D-077 appended; INVARIANTS fetcher-build-order line replaced + a new correction-protocol
bullet; docs/07 gained the demand ledger + probe findings + rewritten steps 8–13; docs/15 Day 5 rewritten
(incl. the D-077 rider on the Paylocity block); docs/14 parked-row guidance replaced with the D-077 runbook;
CLAUDE.md Phase-8/BH lines updated. **Next:** implement blocks 1–2 (SWA/Thales seed-CSV flip + the Paylocity
fetcher + the D-077 tooling) in the next session; per-fetcher build notes are in docs/07 so no re-probing
needed.

---

## 2026-07-10 — Discovery stream crash → complete Responses transport (D-075 → built)

**Observed:** the first live Terra aviation run completed and checkpointed wave 1 (est. $0.2161), then
crashed during wave 2 despite an HTTP 200. OpenAI Python SDK 2.45.0 raised `IndexError: list index out of
range` inside its high-level Responses stream accumulator: an output-text event's `output_index` was absent
from the SDK snapshot. The error happened before `_log_stream_event` received the event, so logging was not
the cause; streaming had only been enabled to provide those per-search lines.

**Decision run through Hayden:** prioritize reliable, exactly metered complete responses over per-search
progress. Discovery research now uses `responses.create`; structured ATS resolution uses `responses.parse`.
Wave/resolver bookends, post-request cost logs, tool/output caps, timeouts, SDK retries, checkpoints,
validation, and the D-074 protocol are unchanged. Catch-and-continue was rejected because a broken partial
stream has no final usage object and would under-meter spend; a custom SSE accumulator was unnecessary
SDK-adjacent complexity.

**Test-first fix:** `test_research_bypasses_sdk_stream_accumulator` failed against the old wrapper with the
same raw `IndexError`, then passed after the transport change. **Verified:** discovery unit + integration slice
(20 tests); full offline suite (**409 passed**, 16 opt-in deselected); ruff format/check; mypy (47 source files);
import-linter (1 kept / 0 broken); `uv lock --check`; `git diff --check`; scoped diff review. Docs: D-075 +
operator-guide logging contract; no INVARIANTS change because no current cross-cutting rule moved. **Next:**
Hayden reviews/commits; rerun the aviation discovery command to finish the live cost/yield measurement. Weekly
scheduling remains OFF.

## 2026-07-10 — Discovery → GPT-5.6 Terra + separately budgeted ATS resolution (D-074 → built)

**Migrated only Layer-3 discovery from Anthropic to OpenAI Responses** on
`feat/gpt-terra-discovery`; extraction/matching remain Anthropic. The trigger was the first Claude
batch: five legitimate employers, zero fetchable ATS resolutions. Broad sourcing had consumed the
useful research window, leaving ATS work as an unbounded best-effort tail.

**Decisions run through Hayden:** Terra default (5.6 family allow-list); three explicit sourcing waves
(capital portfolios / industry lists / market adjacency), **5 hosted web actions each**; at most five
candidates, then **4 actions per unresolved ATS** (low reasoning, 2k output, 120s); canonical
provider-URL + slug/endpoint evidence required; two transient retries then checkpoint+continue; `$4`
inclusive meter; streamed web progress; one rolling report; `--limit` caps resolution + persistence.

**Built:** OpenAI SDK + `OPENAI_API_KEY`; streamed Responses calls with implicit caching and
`store=False`; exact Sol/Terra/Luna token/cache rates plus $0.01/search accounting; spend checks between
every paid request; tool-free structuring still runs after a cap so research survives. The ATS outcome
is typed (`resolved_supported` / `resolved_unsupported` / blocked / no jobs / budget / failure), but
requires **no migration**: unsupported/unvalidated evidence lands in existing proposal `notes` and stays
`unknown`/`layer2`. “Supported” is derived from `SUPPORTED_ATS_TYPES`, not the model, and the existing
registry fetch must return ≥1 posting before a supported ATS is persisted. Human approval and inert
proposal safety are unchanged.

**Docs:** D-074 appended; Discovery invariant, CLAUDE roadmap/config, docs/14 operator guide, docs/15
Day-2 note, `.env.example`, disabled launchd template/readme, and ready-but-off GCP runbook/secrets updated.
The live run then exposed one safe false-negative: JazzHR uses `applytojob.com`; that deterministic
provider-host mapping + an exact Utilidata regression test now classify it `resolved_unsupported`.

**Verified:** `uv lock --check`; ruff format/check; mypy (115 files); import-linter (1 kept / 0 broken);
**408 offline tests** (424 collected, 16 opt-in deselected); `git diff --check`; CLI `--help`; installed SDK
signature/usage-field smoke. **Not run:** live Terra discovery — Hayden-run next with `OPENAI_API_KEY`,
starting with `vja-discover --vertical grid_power_software --limit 5 --dry-run`. The weekly schedule
remains OFF until that run records yield, ATS-resolution rate, rate-limit behavior, and real cost.

---

## 2026-07-10 — First live discovery run (beta-hardening Day 2, partial) — budget fix validated, rate limit is the new ceiling

**Ran `vja-discover --vertical grid_power_software` for real against prod Neon** (not `--dry-run`) — the first
genuine live discovery run. Low-risk by design: writes only `proposed`/`agent_discovered` rows, inert until a
human `vja-review approve` (only `active` employers are fetched nightly). Docs-only session; no code changed.

**The budget fix worked.** After this branch's loosening (searches/fetches 8→20/16, `$` ceiling 2→4), the loop
did **real oblique sourcing** instead of the earlier memory-only fallback: 5 candidates all off the **Energy
Impact Partners portfolio** — GridBeyond, GridX, Emerald AI, CivilGrid, eSmart Systems (rows #91–95, all
`proposed`/`layer2`/`unknown`). GridBeyond's ATS was confirmed **BambooHR** (slug `gridbeyond`) — but BambooHR
isn't in `SUPPORTED_ATS_TYPES`, so it parked; the other four are JS-rendered careers pages it couldn't resolve.
**Zero auto-fetchable this run** — all need manual ATS resolution (or a BambooHR fetcher for GridBeyond).

**The finding that matters (feeds Day 4 scaling):** the run stopped on an **external web-tool rate limit (429s
on `web_search`/`web_fetch`), NOT our `$4`/`_MAX_SEARCHES` caps** — those never engaged. So discovery *yield* is
now gated by the Anthropic web-tool rate limit, not our budget. The run completed only ~1 of ~3 planned source
waves (never reached DistribuTECH/RE+ exhibitor lists, Congruent/Breakthrough Energy portfolios, or a $12.5M
grid-funding lead it spotted). **Open question before enabling the weekly schedule (D-071):** is that limit
per-minute (→ add pacing/backoff between search waves) or a hard account quota?

**Docs:** `docs/15` Day 2 gained a "First live run — 2026-07-10 (partial)" note (candidates + the rate-limit
finding as a Day-4 input). No DECISIONS/INVARIANTS change (the D-073 bounds + D-071 gate are unchanged; this is
an observation, not a new rule).

**Not done here (open threads):** triage/approve of #91–95; the BambooHR-fetcher question; the rate-limit
per-minute-vs-quota investigation; an optional resume/second-wave run. Per-run **cost** was not captured (the
run stopped on rate limits well under the `$4` cap; exact `est_cost` wasn't recorded — Day 4 still needs a clean
full-run number).

---

## 2026-07-10 — Discovery tool budget loosened — fixed the self-starving run (same branch `fix/discover-progress-logging`)

**The new progress logging paid off immediately:** a cheap (~few cents) run that "worked" turned out to
have done **no live web research** — the checkpointed report (`data/discovery_reports/…`) showed the model
fell back to domain-knowledge guesses after "early failed parallel attempts consumed the quota." Dug into why.

**Root cause (not the $ ceiling — the tool budget strangled it):** per-request `max_uses` (tool def) and
the cumulative `_MAX_SEARCHES` were **both 8**, so the first turn's search allowance *was* the whole run's.
Turn 1 the model fired a parallel `web_search` burst → server ran 8 (hit `max_uses`), errored the rest,
some of the 8 failed → thin results, model wrapped up. Our cumulative counter saw 8 `server_tool_use`
blocks → `searches_used >= 8` → **loop broke after turn 1.** The $2 ceiling never engaged.

**Fix (scope = "beef up the tool", aggressiveness run through Hayden → *Generous*):** raised the defaults so
the model has room, dollar ceiling as the real backstop. `_MAX_SEARCHES` 8→**20**, `_MAX_FETCHES` 8→**16**,
`_MAX_CONTINUATIONS` 8→**12**, `_MAX_USD` 2.0→**4.0**. Per-request `max_uses` still tracks the cumulative caps
(via `_WEB_TOOLS`), so it's never the *earlier* limiter and a single turn can burst parallel searches without
a mid-turn wall — the between-turn cumulative check + $ ceiling bound the run. All env-overridable.

**Caveat recorded (in code + docs/14):** `TokenUsage.cost` meters **tokens only** — web_search/web_fetch
server-tool fees (~$0.01/search) sit outside it, so real spend runs a little above the printed `est_cost`
at high tool budgets. Still bounded by the token ceiling + tool caps.

**Test:** `test_web_tools_max_uses_not_below_cumulative_caps` pins the invariant that starved the run —
per-request `max_uses` must never sit below the cumulative cap.

**Docs:** `docs/14` cost section rewritten (new defaults, the "generous budget → real sourcing" rationale,
the meter caveat, the added env knobs). No INVARIANTS/DECISIONS change — D-073's bounds stay the rule, only
the default *values* moved (still hard-capped + cumulative + cached + checkpointed).

**Verified:** full offline gate — ruff/format + mypy + import-linter (1/0) + **411 pytest** (+1). **Not run
here:** the live `vja-discover` — Hayden re-runs with the beefed-up budget (should now do real multi-turn
sourcing, land ~$1–2) and `caffeinate -i`.

---

## 2026-07-09 — Discovery per-turn progress logging — the research loop stops being a silent black box (branch `fix/discover-progress-logging`)

**Problem (observed live):** `vja-discover`'s research loop emitted nothing per-turn — logging is wired
(INFO → stderr) but the loop only logged at the cost/tool guard-breaks and the final `est_cost=` print. So
the multi-minute `web_search`/`web_fetch` phase was a silent black box, then either the summary or (this
session, from a sleeping-laptop network drop) a raw `APITimeoutError` traceback. Plan-mode first; **scope run
through Hayden = logging only** (the timeout crash was self-inflicted `caffeinate`, not a code bug → left alone
to keep the branch true to its name).

**Did (all in `discover.py`, observability only — no behavior change):**
- **Per-turn heartbeat** INFO line in the research loop: `research turn N/M: +s search +f fetch (cum
  searches …/…, fetches …/…), est $X, stop=…` — which turn, this turn's tool use, cumulative tool-budget
  burn, running spend vs the `$MAX_USD` ceiling, and whether it continues. All values were already computed
  each turn; they were just never logged. The existing guard-break warnings stay (they explain *why* it stopped).
- **Bookend lines:** a `starting discovery research for <vertical> (<=N turns, $X ceiling, tool budget …)`
  before the loop and a `research finished after N turn(s), <len>-char report, est $X so far — structuring`
  after research (before the structuring turn).
- `for _ in range(...)` → `for turn in range(1, _MAX_CONTINUATIONS + 1)` (+ `turn = 0` guard) for the counter.

**Test:** `test_discover_logs_per_turn_progress` (unit) — a 2-turn (pause→end) fake client asserts one
heartbeat per turn with the advancing counter + the start/finished bookends.

**Gotcha worth flagging (pre-existing, NOT my change):** the first cut used `caplog`; it passed alone but
failed in the full suite. Traced it down — a **prior test corrupts global logging state**: after
`tests/system/test_run_pipeline.py` runs, `vja.discover`'s `isEnabledFor(INFO)` returns `False` even with
`manager.disable=0`, level INFO, and a handler attached directly to the logger — so INFO records simply
aren't emitted suite-wide. `caplog` (and even a hand-attached handler) captured nothing. Sidestepped by
spying on the module `logger` (monkeypatched fake recording `info/warning` calls) → pins *what the code
logs*, immune to logging config. **Open thread:** that global-logging corruption is a real test-isolation
bug (some pipeline-run dependency mutates logging and never restores it); out of scope here, but it will bite
the next person who reaches for `caplog`.

**Docs:** `docs/14` gained a per-turn-heartbeat note under `vja-discover`. No INVARIANTS/DECISIONS change —
this alters no cross-cutting rule (pure observability), so no ADR minted (run through Hayden).

**Verified:** full offline gate — ruff/format clean + mypy (1 file) + import-linter (1/0) + **410 pytest**
(+1: the new progress-logging test). **Not run here:** live `vja-discover` (Hayden-run; needs key + web
search + `caffeinate -i` this time).

**Next:** Hayden commits/PRs this branch, then re-runs `vja-discover` (now with live progress) to get the
per-run cost that gates the weekly schedule (D-071); then back to the beta-hardening week (`docs/15`).

---

## 2026-07-09 — Discovery loop cost-hardening — Sonnet 5 + $2 kill-switch + cumulative caps + caching + checkpoint (D-073 → built)

**A live `vja-discover` run burned $7 and produced nothing.** Reading the code found three real defects, all
fixed this session. Branch `docs/beta-hardening-scope` (continues the beta-hardening work; **note: this branch
now carries two logical changes — the D-072 scope docs and this D-073 code fix — Hayden may want to split into
two PRs**). Plan-mode-style: every parameter run through Hayden via options+recommendation.

**The bug (D-073):** (1) **no prompt caching** on an agentic loop re-sending a growing web-page-stuffed transcript
every `pause_turn` — uncached Opus input on a super-linear prefix; (2) **`max_uses` resets per request**, so the
resume loop had no real run cap (39 searches under a "15") and **no dollar ceiling at all**; (3) **all-or-nothing
persist** at the end → a killed Stage-1 discarded everything.

**Corrected a stale-catalog miss:** I claimed "Sonnet 5 doesn't exist" from a cached model list; Hayden pushed
back; the **live Models API confirmed `claude-sonnet-5`** (standard $3/$15, intro $2/$10 per MTok through
2026-08-31). Verified, didn't trust memory.

**Did (all in `discover.py`):**
- **Model default → `claude-sonnet-5`**; **model-aware `_model_rates`** (longest-prefix; standard list price,
  conservative) replacing hardcoded Opus constants → honest meter + kill-switch under any `VJA_DISCOVER_MODEL`.
- **Hard `VJA_DISCOVER_MAX_USD` = $2 kill-switch** — loop breaks the turn after `usage.cost()` crosses it.
- **Cumulative tool budget** (8 searches / 8 fetches) via `_count_tool_uses` counting `server_tool_use` blocks
  across resumes — the real fix for the reset bug; `max_uses` stays constant per request so the cache holds.
- **Prompt caching** (`cache_control` ephemeral, SDK-verified) so the growing prefix re-reads at ~0.1×; **`web_fetch
  max_content_tokens=5000`**.
- **Checkpoint**: `_dump_report` writes the raw report to `data/discovery_reports/` the moment research finishes
  (per-candidate DB persist already existed) → a capped/killed run keeps what it paid for. `_MAX_CONTINUATIONS`
  env-tunable (12→8).

**Net:** a full run now lands well under $1 and **cannot** run away or lose findings.

**Decisions:** **D-073 → accepted** (supersedes D-070's theatrical `max_uses` bound + Opus model/rate). INVARIANTS:
Discovery section — model → Sonnet 5, new "research loop is cached + $-bounded" invariant replacing the old
"bounded by max_uses" clause. CLAUDE.md 10.1 + docs/14 updated (model, cost, env knobs). `.gitignore` +=
`data/discovery_reports/`.

**Verified:** full offline gate — ruff/format + mypy (115 files) + import-linter (1/0) + **409 pytest** (+6:
dollar-ceiling break / cumulative-tool-cap break / cache_control+fetch-cap wiring / model-aware rates / tool-use
count / report checkpoint). CLI `--help` + constants smoke. **Not run here:** the live `vja-discover` (Hayden-run,
needs key + web search) — which now also yields the real per-run cost that gates the weekly schedule (D-071).

**Next:** Hayden re-runs `vja-discover` (should now be sub-$1, bounded). Then back to the beta-hardening week
(`docs/15`). **Branch hygiene:** consider splitting `docs/beta-hardening-scope` into the scope-docs PR (D-072) +
this cost-fix PR (D-073).

---

## 2026-07-08 — Beta hardening · scoped the pre-invite week + reconciled doc drift (D-072 → accepted)

**Docs-only session. Scoped the beta-hardening week and fixed the roadmap drift that had accumulated.** Branch
`docs/beta-hardening-scope`. Plan-mode-style: three scoping choices run through Hayden before any edit.

**Context:** Phase 10 (the last roadmap item) is done; go-live is fully closed. Hayden's own scope (6 items,
one day each) was slightly misaligned with the docs, which still read as if launch blockers were open.

**Reconciled (the drift):** CLAUDE.md listed **9.6 CI/CD as "NEXT"** though D-068 shipped it (→ marked ✅), and
listed **email E2E + `/security-review` as open closeout** though both are done (→ closed out). B-4 prod cleanup
+ fresh-account walkthrough passed; **real private users are signed up** — beta invites are unblocked.

**Did:**
- **New `docs/15-beta-hardening-plan.md`** — the plan of record: six one-day items (UI rework · discovery-agent
  live run + coverage ledger + low-signal pruning · bug shakeout + optional nightly alert · scaling plan across
  Neon/GCP/Resend/OAuth **+ Anthropic LLM spend** incl. the parked Batch API Block 2 · more fetchers, Phenom
  next) with DoD per day and a parked list. Only hard dep: Day 2 (discovery cost) → Day 4 (scaling).
- **CLAUDE.md:** 9.5d closeout marked complete; 9.6 CI/CD → ✅ (D-068); new **Phase BH — beta hardening
  (ACTIVE)** roadmap line; doc-map entry for `docs/15`.
- **docs/13:** status → DONE (both onboarding blocks landed, B-4 passed); pointer to `docs/15` for hardening.
- **DECISIONS:** D-067 got a dated **closeout-complete** note; **D-072** appended (beta-hardening scope of record).

**Decisions run through Hayden:** LLM cost **folded into the scaling day** (not its own, not deferred); email
E2E + `/security-review` **confirmed done** → reconcile docs rather than re-scope; deliverable = ordered plan +
doc reconciliation. Observability on Day 3 kept as a **flagged optional** sub-item; B-4 marked resolved.

**Verified:** docs-only diff — no code touched, so the pytest/lint gates aren't triggered (DoD here = human-read
diff + updated docs). Hayden commits/PRs.

**Next:** start **Day 1 (UI rework)** — first timebox the "which leader to model" pick. Day 2 is Hayden-run
(live `vja-discover`/`vja-review`, needs `ANTHROPIC_API_KEY` + web search).

---

## 2026-07-08 — Phase 10.2 · Layer-3 review surface — `vja-review` CLI + ready-but-off schedule (D-071 → built)

**Built the human approval gate that makes discovery output usable:** D-070's agent writes `proposed`
employers, but only `active` ones are fetched — so proposals were inert dead weight until now. Branch
`feat/phase10-discovery-agent` (continues 10.1). Code + docs; the live CLI walkthrough is Hayden-run.
**Plan-mode first, three decisions run through Hayden:** ready-but-off scheduling · approve→active|approved
(parked) · reject→retired.

**Did:**
- **New top-tier module `src/vja/review.py`** + `vja-review` CLI (`list`/`approve`/`reject`), same
  import-linter layer as `discover` (imports `db` + `fetchers.registry`, no re-fetch — trusts the agent's
  stamped `ats_type`). `approve_employer`: `ats_type ∈ SUPPORTED_ATS_TYPES` → `active` (fetched next
  nightly), else → `approved` + **parked** with a printed notice. `reject_employer` → `retired`. Guards
  not-found + non-proposed. Batch-friendly ids; exit 1 if any id fails.
- **`db/employers.py`:** `EmployerListing` read shape + `list_employers_by_status` /`get_employer_by_id` /
  `set_employer_status` (the lone write primitive; the approve-vs-park decision lives in `review`, not the
  DB layer). **No migration** — reuses existing `EmployerStatus` values (matches 10.1).
- **Fetchability keyed on `SUPPORTED_ATS_TYPES`, not `verification`** — the nightly's own predicate, so a
  hand-fixed `ats_type` activates on approve (the manual-resolution path, free). Parked rows are
  *structurally* unfetchable (`active_fetchable_employers` filters status+ATS), so `list --status approved`
  is the flag — no runtime guard.
- **Scheduling ready-but-OFF:** `deploy/launchd/com.vja.discover.plist.template` (weekly Mon-07:00,
  `RunAtLoad` off, **not** auto-installed by `install.sh`) + README "Discovery (disabled)" section + a
  Cloud Scheduler runbook (`deploy/gcp/CUTOVER.md` §8b, documented not created). No `ship.sh` change.

**Decisions:** **D-071 → accepted** (references D-070/D-047/D-031/D-017/D-009/D-005). INVARIANTS: extended
the "Discovery (Layer 3)" section (review-promote rules + parked-safety + ready-but-off schedule, replacing
the "block 10.2" forward-reference). CLAUDE.md Phase 10 → `10.2 ✅`.

**Verified:** full offline gate — ruff/format + mypy (115 files) + import-linter (1/0, `review` in the
pipeline layer) + **403 pytest** (+8 integration: approve fetchable→active / layer2→parked / keyed-on-ats-type
/ reject→retired / not-found / non-proposed-refused / list filters / CLI smoke). **Not run here:** the live
`vja-discover` → `vja-review` walkthrough (needs `ANTHROPIC_API_KEY` + web search) — Hayden-run; it also
yields the real per-run cost that gates enabling the weekly schedule.

**Next:** Hayden runs the live CLI walkthrough (10.1's still-pending smoke folds in). Then a week of **beta
hardening** (expand the employer universe — Phenom next per D-052 — coverage ledger, low-signal pruning,
landing/login polish) with the two beta users. **Later Phase 10:** auto-approval, a proposal-precision eval
(needs a sample), non-employer `sources`, enabling the weekly schedule. **Still parked:** the LLM-cost Batch
API Block 2 (needs the Block-1 nightly token read first).

---

## 2026-07-07 — Phase 10.1 · Layer-3 discovery agent, thin core (D-070 → built)

**Started Phase 10 (the last roadmap item) — the discovery agent that finds new *employers* and writes them as
`proposed` rows for human approval.** (Block 2 of the cost fix was parked — it needs the Block-1 nightly numbers,
which aren't read yet.) Branch `feat/phase10-discovery-agent` (off `main` @ `cd23d2a`). Code + docs; the live LLM
smoke is Hayden-run. **Plan-mode first, four decisions run through Hayden → all "recommended":** thin core first ·
Anthropic web tools · admin CLI review surface · validate-by-fetching.

**Did:**
- **New top-tier module `src/vja/discover.py`** + `vja-discover` CLI, two cleanly-separated stages:
  - **Stage 1 (LLM):** Opus 4.8 (`claude-opus-4-8`, adaptive thinking, `effort=medium`) with the server-side
    `web_search_20260209` + `web_fetch_20260209` tools runs an agentic research loop over oblique sources (VC/PE
    portfolios, conference sponsors, funding news, competitors-of-X), passed the existing universe as a
    do-not-repropose list; handles `pause_turn` (bounded by `_MAX_CONTINUATIONS`); a toolless `messages.parse` turn
    structures the report → `list[CandidateEmployer]`. Bounded by `web_search` `max_uses` (`VJA_DISCOVER_MAX_SEARCHES`);
    spend metered with the Block-1 `TokenUsage` (D-069) at Opus rates, printed per run.
  - **Stage 2 (deterministic, LLM-free):** dedup on normalized name, then **validate by actually fetching** — build an
    `Employer` from the guess and run `registry.get_fetcher(ats).fetch()` (pure reuse of the fetcher spine, D-017).
    Fetchable + ≥1 posting → `proposed`/`verification=detected` with the real ATS; else → `proposed`/`unknown`/`layer2`
    with the guess kept in `notes` for manual triage.
- **`db/employers.py`:** `normalize_employer_name` (lives in `db` so `discover -> db` stays one-directional),
  `existing_employer_names`, `insert_proposed_employer` (`source=agent_discovered`, `status=proposed`, idempotent on
  `UNIQUE(vertical, name)`). **No migration** — the schema already had the enum values; only `active` employers are
  fetched nightly, so proposals sit inert until approved.
- **`pyproject.toml`:** `vja-discover` entry point; `discover` added to the pipeline import-linter layer.

**Decisions:** **D-070 → accepted** (Phase 10.1 thin core; references D-047/D-017/D-005/D-069). INVARIANTS: new
"Discovery (Layer 3)" section + `discover` in the layering line. CLAUDE.md Phase 10 ticked (10.1 ✅, 10.2 = review
CLI + scheduling).

**Verified:** full offline gate — ruff/format + mypy (113 files) + import-linter (1/0) + **395 pytest** (+14: unit
validate-by-fetch fetchable/unresolved/dedup/unsupported-ATS + the Stage-1 loop incl. `pause_turn` resume;
integration `insert_proposed_employer` idempotency + `run_discovery` persistence & dry-run, faked client +
respx-stubbed ATS). CLI `--help` wires up. **Not run here:** the live `vja-discover --vertical grid_power_software
--limit 5 --dry-run` (needs `ANTHROPIC_API_KEY` + real web search) — Hayden-run.

**Next — 10.2 (block 2 of Phase 10):** the `vja-review` approve/reject admin CLI (`list_proposed` /
`set_employer_status`) + weekly scheduling (launchd / Cloud Run Job); later, auto-approval, a proposal-precision
eval once there's a sample, and discovery of non-employer `sources` (HN/niche). **Still open from before:** the
parked LLM-cost Block 2 (Batch API — needs the Block-1 nightly token read first).

---

## 2026-07-07 — Phase 5.x · LLM cost Block 1 — real token metering + Sonnet effort=medium (D-069 → built)

**Two signups cost $6/morning; the console showed ~10M input : <1M output (input-bound ~10:1) at ~7% cache
hit. Reading the code found the leak is extraction's unique, uncacheable descriptions — and that spend was
metered by a `$0.01`/item *proxy*, so we were optimizing blind. Block 1 = measure first (Hayden's call).**
Branch `feat/llm-cost-instrumentation` (off `main` @ `8d82236`, post-9.6). Code + docs; the eval sweep + the
post-deploy nightly read are Hayden-run.

**Did:**
- **Real token metering.** New `TokenUsage` value in `models.py` (input/output/cache_read/cache_write,
  `from_response` + cache-aware `cost()` + `cache_hit_rate`); `extract_posting`/`match_posting` now **return
  it** (not a scalar cost), summed through `ExtractionSummary`/`MatchingSummary`/`Layer2Summary` and **persisted
  to 4 new `pipeline_runs` columns** (additive Alembic migration `b2f4c1a9e07d`, applies clean on SQLite +
  born-on-PG per D-054). `nightly.py` logs a per-stage line with the matching cache-hit %. Centralized the
  ad-hoc `usage` reads / cost math that lived in `match._call_cost` + `extract` (both removed).
- **`effort=medium`** on the Sonnet match call (`output_config`), **env-overridable `VJA_MATCH_EFFORT`** — the
  API default `high` overspends since thinking bills as output. **Eval-gated (D-020):** ship the lowest
  eval-passing effort (sweep medium/low with a key).
- **Extraction `cache_control`** on the system prompt — expected no-op (Haiku's 4096 cacheable floor > the short
  prompt), kept as the correct pattern; the meter now shows whether it fires.

**Decisions:** **D-069 → accepted** (supersedes D-036's "adaptive/high, $0.01 proxy" cost posture). INVARIANTS:
metering line rewritten (real `TokenUsage` persisted, not proxy; proxy survives only as the backfill guard),
model-tiering line notes `effort=medium`.

**Verified:** full offline gate — ruff/format + mypy (110 files) + import-linter (1/0) + **381 pytest** (+2 unit
tests: effort default/override, extraction cache_control; + integration assertions that usage aggregates and the
`pipeline_runs` token columns persist). Migration upgrades a fresh DB to a single head with all 4 columns.
**Not run here:** the `eval` sweep (needs `ANTHROPIC_API_KEY`) and the prod nightly read.

**Next — ship checklist (in order; `feat/llm-cost-instrumentation` is built, uncommitted):**
1. Commit + push + open PR (gates run, deploy skipped on PRs).
2. Eval sweep — `VJA_MATCH_EFFORT=medium uv run pytest -m eval tests/eval/test_match_eval.py` (must pass; medium
   is the shipped default). Optionally `=low`; keep medium for the first measured night unless you set the knob
   on the prod service **and** job manually (`ship.sh` writes no env vars).
3. **`alembic upgrade head` on Neon BEFORE merging** — schema-changing PR; first real exercise of the D-068
   ordering rule, or tonight's nightly errors writing the new columns.
4. Merge → 9.6 auto-deploys the image onto the service + `vja-nightly` Job.

**Then test tomorrow (after the 6am-Chicago nightly):** read `pipeline_runs`
(`input/output/cache_read/cache_write_tokens`) + the Cloud Run Job `layer-2 […]` log line. Expect small numbers
on a steady night (nightly matches only *unmatched* postings) — a fresh signup beforehand fattens the sample;
`hit=%` near 0 confirms the resume prefix isn't clearing Sonnet's 2048 cache floor. Caveat: `pipeline_runs`
captures the **nightly**, not signup backfills (background API task, no run row — console/logs only).

**Block 2 (next block) = Batch API** (50% off extraction + matching), sized against these real numbers — incl.
whether the nightly re-extracts unchanged postings (a possible `content_hash`-churn bug the meter would expose).

---

## 2026-07-06 — Phase 9.6 · merge-triggered CI/CD to Cloud Run (D-068 → built)

**Closed the deploy loop for the beta-hardening week: merging to `main` now auto-deploys prod.** Branch
`feat/9.6-cicd` (off `main` @ `a085599`). Code + docs; no cloud ops in-session (no gcloud/creds in-sandbox).

**Did:** added a `deploy` job to `.github/workflows/ci.yml` — `needs: [gates, postgres, frontend, secrets]`
(green CI is a hard edge), `if` push-to-`main`-or-`workflow_dispatch` (never PRs), own non-cancelling
`deploy-prod` concurrency, `id-token: write` for WIF, `environment: production`. It auths keylessly via
**Workload Identity Federation** (`google-github-actions/auth@v2` off repo *variables* `GCP_WIF_PROVIDER` /
`GCP_DEPLOY_SA`), configures docker for Artifact Registry, then **execs `./deploy/gcp/ship.sh --force`** — the
key call: one code path, so the proven secret/SA/guards-preserved config never gets copied into YAML to drift.
`ship.sh` gained an **env-gated `ROLLBACK_ON_SMOKE_FAIL`** (CD sets `=1`): a failed health/anon-401 smoke
auto-shifts traffic back to the prior revision before exiting (deploy already sent 100% traffic to the new one);
default 0 = unchanged manual behavior. `deploy/gcp/README.md` gained a "CI/CD (9.6)" section: the one-time WIF
runbook (pool + repo-restricted OIDC provider + `github-deployer` SA with `run.admin`/`artifactregistry.writer`/
actAs-runtime-SA + `workloadIdentityUser` binding → prints the two repo variables), the migrate-before-merge
ordering rule, and rollback.

**Design calls (approved in plan):** WIF over a SA JSON key (no long-lived credential); auto-deploy over a
manual-approval `environment` gate (smoke + auto-rollback + `ship.sh` break-glass are the net); **migrations
stay manual** (CD deploys code only — schema-changing PRs run `alembic upgrade head` on Neon first); reuse
`ship.sh` over a YAML re-implementation (anti-drift).

**Decisions:** **D-068 → accepted** (supersedes D-066's "9.6 deferred"). INVARIANTS: new "`main` auto-deploys"
line under Testing & workflow. `docs/13` 9.6 ticked; `CLAUDE.md` already named 9.6 NEXT (last session).

**Verified:** `bash -n deploy/gcp/ship.sh` clean. shellcheck/actionlint not installed locally → workflow YAML
+ script reviewed by hand. **Cannot run the deploy here** — no gcloud/creds, and it's an outward-facing prod
deploy. **DoD is Hayden-run:** one-time WIF provisioning + repo variables, then a `workflow_dispatch` first run
(deploy + smoke green) → a real merge proves the push path.

**Next:** Hayden commits/PRs `feat/9.6-cicd`, runs the WIF setup (README §CI/CD), fires the first
`workflow_dispatch`. Still open from before: **B-4 prod data cleanup** + fresh-account walkthrough + beta
invites; go-live closeout (email E2E + `/security-review`); and the beta-hardening backlog (Phenom, landing/login
polish, coverage ledger).

---

## 2026-07-06 — Phase B · onboarding / auth-UX overhaul (D-064 + D-065 → done; the beta blocker)

**The real fix behind the broken fresh-account flow: vertical is now a property of the logged-in user, not a
global picker.** Branch `feat/phase-b-onboarding` (off `main` @ `ccee954`). Built backend-first (paused for
Hayden's review + commit), then the frontend.

**B-1 backend (committed separately):** new `active_profile_for_user(engine, email)` (the SPA's routing source);
`GET /api/me` reshaped → `{user, profile|null}` (refactored to inject `get_current_user` via `Depends` so it's
test-overridable); **one-vertical enforcement** on `POST /api/profiles` (different vertical → **409**;
same-vertical re-upload stays an idempotent résumé update); **`prompt="select_account"`** on the OAuth redirect.
+7 tests / 2 updated.

**B-2/B-3 frontend:** `App.tsx` is now real route guards off `useAuth()` — `Landing` (logged-out, kills the
401-as-error leak) · `/login` · `/onboarding` (pick vertical + upload) · `/dashboard` (their vertical) ·
`/upload` (résumé update, vertical **locked**). `api.ts`/`AuthProvider`/`useAuth` carry `{user, profile}` off
`/api/me`. **`Dashboard` takes its vertical as a prop from the profile** — dropped `fetchVerticals()`/`vs[0]`,
which **was the 404 bug**. **Matched-view poll (B-3):** on `justOnboarded` (router state set on the
onboarding→dashboard navigate), bounded client-side poll (`10s × ~2.5min`) of the backfill, then "full results
after tonight's run" — no backend push (D-057). Onboarding success **refreshes `/api/me`** before routing so the
new profile lands (else the guard would bounce back to onboarding).

**Caught in build (not in the plan):** using `active_verticals` (active-profile-driven) for the onboarding
picker would have **hidden aviation** once B-4 deactivates its seed profile → an aviation beta user couldn't
onboard (chicken-and-egg). **Fix:** repointed `GET /api/verticals` to **config-driven `available_verticals()`**
(joinable with zero profiles) and **removed the now-dead `profiles.active_verticals`**.

**Decisions:** D-064 + D-065 → **done**. INVARIANTS: SPA-routing line rewritten (guards + `/api/me` +
config-driven picker), résumé-upload line (onboarding/locked + refresh→route + matched poll + 409), one-vertical
line (enforced, not "known defect"). `docs/13` Phase B ticked.

**Verified:** Python gate — ruff/format + mypy (45 files) + import-linter (1/0) + **379 pytest** (+7). Frontend
gate — eslint clean, `tsc --noEmit` clean, **vitest 45** (+ new guard/poll tests), production `npm run build` ok.

**Next:** **B-4 prod data cleanup** (Hayden runs against Neon — deactivate the aviation seed profile on
`haydenham10@gmail.com`; grid stays; SQL provided) → deploy via `./deploy/gcp/ship.sh` → **re-run the
fresh-account walkthrough** before beta invites. Also still open from go-live closeout: email E2E +
`/security-review`.

---

## 2026-07-06 — Phase A · thin scripted deploy `ship.sh` (D-066 → done)

**First of the two pre-beta blocks (`docs/13`): the thin redeploy script, so shipping Phase B — the onboarding
overhaul — is one command, not a hand-walk of `CUTOVER.md`.** Branch `feat/phase-a-ship-script` (off `main`
@ `0e5beb1`). Code-only + docs; no cloud ops run in-session.

**Did:** `deploy/gcp/ship.sh` (new, executable) — build (`--platform linux/amd64`, the mandatory arm64→amd64
footgun) → push (tag = short SHA) → capture prior serving revision → `gcloud run deploy rolefeed` (re-asserts the
full CUTOVER §5 config: 8 secrets, runtime SA, `--allow-unauthenticated`) → `gcloud run jobs update vja-nightly`
(same image, D-031 trigger-swap; 5 secrets, no OAuth/session) → smoke (`/api/health` = ok **and** anon
`/api/postings?vertical=grid_power_software` → **401**) → print the `update-traffic` rollback naming the prior
revision. **Key contract:** the script passes **no** `--set-env-vars`, so the prod guards (`VJA_AUTH_REQUIRED`/
`VJA_COOKIE_SECURE`/`VJA_PUBLIC_BASE_URL`, CUTOVER §9) are preserved untouched — it can't reopen auth; the 401
smoke is the tripwire if that ever regresses. No secret **values** in the script (Secret Manager by name);
locked values are env-overridable defaults. Redeploy-only — schema (`alembic`), seed, domain, OAuth URIs stay
manual (CUTOVER). Dirty-tree → confirm/`--force` (tag is the SHA). `deploy/gcp/README.md` gains a "Redeploying
(`ship.sh`)" section.

**Design calls (approved in plan):** re-assert full config each deploy (self-healing vs drift; cost = the
`--set-secrets` replace-semantics, kept identical to CUTOVER + loudly commented) over image-only; guards
preserved-never-set; rollback = capture-prior + print (no auto-rollback).

**Decisions:** **D-066 → done.** No new INVARIANT (a redeploy script isn't a cross-cutting rule; CUTOVER +
README cover it). `docs/13` Phase A ticked.

**Verified:** `bash -n` clean; `chmod +x`. `shellcheck` not installed locally. **Cannot run the script here** —
no gcloud/docker/creds in-sandbox, and it's an outward-facing prod deploy. DoD's "no-op rebuild deploys
end-to-end" is Hayden-run.

**Next:** Hayden commits/PRs `feat/phase-a-ship-script` + runs a no-op `./deploy/gcp/ship.sh` to close Phase-A
DoD. Then **Phase B — onboarding/auth-UX overhaul** (the actual beta blocker): `/api/me`-driven per-user vertical
routing, real route guards (static landing → `/onboarding` → their dashboard), one-vertical write enforcement,
`prompt="select_account"`, matched-view client poll. Plus scope's **closeout** (email E2E + `/security-review`)
and the B-4 data cleanup (deactivate one of Hayden's two seed profiles).

---

## 2026-07-06 — Phase 9 · 9.5d go-live finished + found the onboarding flow is broken; planned the fix (D-064–067)

**Session picked up mid-cutover, live with Hayden. Net: the cloud cutover is done and the app is live on
`role-feed.com` with auth on — but a fresh-account walkthrough exposed that the onboarding/dashboard flow is
broken, so we specced the fix instead of inviting beta users.** Branch `docs/onboarding-and-shipping-plan`
(docs only; no code/ops in-session beyond read-only diagnostics + the two Hayden-run ops noted below).

**Go-live closeout (D-067):** Hayden flipped the prod guards (`VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`,
`VJA_PUBLIC_BASE_URL=https://role-feed.com`); confirmed anon `/api/postings` → **401**. The scary
**`role-feed.com` TLS reset** (RST right after ClientHello, from two networks) was **not** Cloud Run — the
mapping read `Ready`/`CertificateProvisioned`, DNS correct — it was **office wifi blocking a newly-registered
domain**; **works over hotspot.** (A delete+recreate of the mapping was a red herring; harmless.) Remaining
closeout: real email E2E + `/security-review`.

**The real finding — onboarding is broken (D-064/065):** a fresh Google account showed every step wrong:
logged-out `/` renders a **401 as an error string** (no login landing); after login the dashboard **404s**
because `active_verticals()` returns a **global, cross-user** vertical list and `Dashboard.tsx` defaults to the
sorted-first (`aviation_software`) regardless of user; the vertical picked at upload is ignored; no onboarding
gate. **Root cause:** the SPA treats vertical as a global picker, contradicting the standing (but never
documented) policy **one vertical per user** — a documentation/communication lapse, now fixed in the docs.

**Decisions:** **D-064** one-vertical-per-user made explicit (fixed at signup, immutable, no cross-user picker).
**D-065** onboarding overhaul target flow: static landing (+login CTA) → Google auth → **one page: pick vertical
+ upload résumé** → their dashboard (cleaned immediate; matched = loading via a bounded client-side poll, no new
backend; timeout → "full results after tonight's run"); adds `/api/me`, route guards, one-vertical enforcement,
`prompt="select_account"`. **D-066** ship a **thin scripted deploy** (`ship.sh`) before the fix, not full CI/CD
(deferred "9.6"). **D-067** go-live done + the corporate-wifi lesson. INVARIANTS updated: one-vertical rule
added, auth-required now **ON in prod**, the deployed global-picker flagged as a known defect.

**New doc:** `docs/13-onboarding-and-shipping-plan.md` — the plan of record for the next two blocks (**A** thin
ship-script → **B** onboarding overhaul), the beta-onboarding checklist, and the later roadmap (9.6 CI/CD,
Phase 10 discovery agent + review queue, beta hardening = expand the employer universe).

**Next (post-reset):** plan/build **Phase A** (ship-script), then **Phase B** (onboarding overhaul — the beta
blocker). Also pending: deactivate one of Hayden's two seed profiles (the dual-vertical anomaly under one email,
D-064 §B-4), finish go-live closeout (email E2E + security review), and merge this docs branch.

---

## 2026-07-02 — Phase 9 · 9.5d go-live (in progress): cloud cutover + container config-path bug fix (D-063)

**Executed most of `deploy/gcp/CUTOVER.md` live with Hayden; hit + fixed a real cutover-blocking bug.** Branch
`fix/vertical-config-path-in-container` (off `main` @ `8dcbc0a`).

**Cutover progress (ops, Hayden-driven):** image built `--platform linux/amd64` + pushed (§1); runtime-SA
secret grant (§2); `alembic upgrade head` on Neon (§3); baseline seed (§4) — 90 employers imported, `vja-run`
seeded **9,773 postings** (`first_seen_at` stamped), 2 profiles loaded (aviation + grid, both active). Service
deployed auth-OFF (§5) + `*.run.app` smoke green incl. **Google login round-trip** (§6). Custom domain
**mapped + cert green** (§7, `role-feed.com`, 8 apex A/AAAA in Cloudflare DNS-only). Nightly **Job + Scheduler
created** (§8, `0 6 * * *` America/Chicago). **Not yet done:** guard flip (§9), email E2E (§10), sec-review +
docs (§12), and merge of this branch.

**The bug (D-063):** first `vja-nightly` executions completed ok but did **zero Layer-2** — `extracted=0
matched=0 digests=none $0`, reproducibly. Root cause proven by running the deployed image: the nightly's
`for vertical in available_verticals()` got **`[]`** because `_CONFIG_DIR = Path(__file__).parents[2]/config/
verticals` assumes the repo/src layout, but the image installs vja **`--no-editable`** (site-packages), so
`parents[2]` missed and the config YAMLs (copied to `/app/config/verticals`) were never found. Local runs
(src layout) always worked → never caught pre-cloud. **Fix:** honor a **`VJA_VERTICALS_DIR`** env override
(mirrors the existing `VJA_FRONTEND_DIST` pattern, D-060 — same `--no-editable` path problem); Dockerfile sets
it to `/app/config/verticals`. Proven in-container: default → `[]`; `/app/config/verticals` → both verticals.
After rebuild+redeploy (image `b2a74fa`, + `--task-timeout=7200`/`--max-retries=1` on the Job), execution
`vja-nightly-295wd` **confirmed calling `api.anthropic.com` in the extraction phase** — Layer-2 now runs.

**Tests:** +1 regression (`test_config_dir_honors_env_override`, reloads the module under a patched env).
**Verified:** ruff + mypy clean; **372 pytest** green (was 371). Also folded two `CUTOVER.md` doc fixes
(explicit `import-employers` CSV path; the `--task-timeout` note).

**Next:** let `295wd` finish (extract ~2k → match → digest); confirm matches + first digest land; **then**
resume `CUTOVER.md` §9 guard flip → §10 email E2E → §12 sec-review/docs. **Merge `fix/vertical-config-path-
in-container` → `main`** so the deployed `b2a74fa` matches the default branch. Hayden also doing domain
follow-up.

---

## 2026-06-30 — Phase 9 · 9.5d-prep: engine hardening + cutover runbook + change-mgmt (D-062)

**Repo-side prep for the last block (9.5d go-live), no cloud ops run.** 9.5c is done+merged (PR #47 @
`74644e1`) — this session reconciles that, ships the one real pre-ship code fix, writes the executable cutover
runbook, and documents the post-launch change loop. Branch `feat/9.5d-prep`.

**Correction to last session:** D-061/WORKLOG said the laptop can't reach Neon (port-5432 filtered) so
migration had to go via a Cloud Run Job exec. Hayden reach-tested the pooled URL this session →
`neon ok`. So `alembic upgrade head` + baseline seed run **locally from his shell** — simpler, fewer moving
parts. Folded into the runbook + D-062.

**Did:**
- **Engine hardening (code)** `src/vja/db/engine.py`: `get_engine` now sets **`pool_pre_ping=True`** (all
  dialects) + **`pool_recycle=1800`** (`POOL_RECYCLE_SECONDS`, non-SQLite only) so Neon's serverless
  autosuspend can't hand out a dead pooled connection. SQLite FK-pragma listener untouched.
- **`deploy/gcp/CUTOVER.md`** (new) — the 9.5d runbook, analogue of the 9.5c `README.md`. Safety order
  `artifact→schema→seed→deploy(auth OFF)→smoke→domain→auth ON`; exact `gcloud`/`docker` commands (no secret
  values); the **`--platform linux/amd64`** gotcha (arm64 laptop → amd64 Cloud Run), runtime-SA
  `secretAccessor` grant, local `alembic`/seed, a **staged `*.run.app` smoke incl. login** before domain/auth,
  Cloud Run Job + Scheduler (`0 6 * * *` America/Chicago, matching launchd), the auth flip **last**, and a
  `update-traffic` rollback note. "Done when green" checklist.
- **`docs/11` §5 Post-launch change management** (new) — **Path A** (data → DB, no redeploy: employers via
  `vja-import-employers`, profiles via upload/`vja-load-profiles`) vs **Path B** (config/code baked in image →
  rebuild+deploy: `config/verticals/*.yaml`, scope/prefilter, fetchers, discovery agent). Maps Hayden's
  roadmap (2 new verticals + expansion + company-finder) onto the two loops; recommends a merge-triggered
  auto-deploy as a post-launch "9.6", flags moving config out of the image if churn ever hurts. Cross-linked
  from `docs/09` + the CLAUDE.md doc-map line.

**Decisions:** **D-062**. INVARIANTS: DB-access line gains the pre-ping/recycle rule. docs/12: 9.5c status →
merged via PR #47; §9.5d rewritten as an index → `deploy/gcp/CUTOVER.md`.

**Tests:** `tests/integration/test_engine.py` (+2: sqlite pre-pings/no-recycle; postgres pre-pings+recycles —
offline, `create_engine` is lazy). Rest of the suite unchanged.

**Verified:** full Python gate green — ruff format/check, mypy (110 files), import-linter (1 kept/0 broken),
`uv lock --check`, **371 pytest** (+2) on SQLite. (CI re-runs the suite on the `postgres:16` service on push;
the new engine tests are offline — `create_engine` is lazy — so they cover both dialects locally.)

**Next:** **STOP for Hayden to commit + PR** (`feat/9.5d-prep`). Then **9.5d — execute `deploy/gcp/CUTOVER.md`**
(Hayden-driven, his gcloud/console auth): build+push → deploy service (auth off) → smoke → domain → Job +
Scheduler → flip guards → test send → `/security-review` → docs. Post-launch: the §5 "9.6" auto-deploy loop.

**Branch:** `feat/9.5d-prep` (off `main` @ `74644e1`).

---

## 2026-06-30 — Phase 9 · Block 9.5c: cloud provisioning standup (D-061)

**Third 9.5 block — ops standup, no app code.** Stood up the cloud resources the 9.5d cutover deploys
*into*, live with Hayden in his consoles + a written runbook. Plan of record: `docs/12`.

**Did:**
- **`deploy/gcp/README.md`** (new) — the provisioning runbook (the cloud analogue of `deploy/launchd/`):
  variables block + locked-values table, `gcloud`-driven where reproducible, console steps marked
  (Neon/OAuth/Resend/Cloudflare), **no secret values in the repo** (→ Secret Manager), a "hand-off to 9.5d"
  green-checklist.
- **Provisioned (verified via `gcloud` reads):** GCP project **`role-feed-prod`** (#850723734041) + billing;
  4 APIs (run/artifactregistry/cloudscheduler/secretmanager, no Cloud SQL); Artifact Registry Docker repo
  **`rolefeed`** (`us-central1`); **8 secrets** loaded w/ enabled versions; **OAuth** web client in
  `role-feed-prod` (consent External/Testing, redirect `https://role-feed.com/auth/callback`); **Resend**
  domain `role-feed.com` verified + `digest@role-feed.com`; **Neon** DB (AWS us-east-2), `VJA_DATABASE_URL`
  stored **pooled + `postgresql+psycopg://`**.
- **`.env.example`** — corrected the one wrong literal (`rolefeed.com` → `https://role-feed.com` in the
  `VJA_PUBLIC_BASE_URL` example).

**Gotchas (captured in D-061 + runbook):** domain is **`role-feed.com` (hyphenated)**, not the `<rolefeed>.com`
the docs/12 table had assumed — literal differs everywhere. Neon hands out bare `postgresql://`; the
**`+psycopg` rewrite is mandatory** (re-lost it once when swapping to the pooled host — fixed, now v4). OAuth
client was first made under the wrong project, **re-created in `role-feed-prod`** (secrets @ v2). **Laptop
can't connect to Neon (local network blocks port 5432)** — irrelevant to prod (Cloud Run reaches Neon over
the cloud backbone); authoritative connect + `alembic upgrade head` runs at 9.5d via a Cloud Run Job exec.

**Decisions:** **D-061** (provisioning values locked). INVARIANTS: no change (no live cross-cutting rule
moved — the auth-required/cookie/redirect flips are still 9.5d). docs/11 §3.4 (verified sending domain) +
§3.5 (secrets store) ticked. docs/12: status line **fixed** (9.5b was stale — merged via PR #46 @ `0abbb5b`,
not "awaiting commit+PR"), 9.5c row → ✅, §9.5c rewritten as-built with the real literals.

**Tests:** none — docs/ops only, no code touched (Python/frontend gates unaffected).

**Next:** **STOP for Hayden to commit + PR** (9.5c, branch `feat/cloud-deploy-9.5c`). Then **9.5d — cutover/
go-live:** build+push image → Cloud Run service (API+SPA) + Cloud Run Job (`vja-nightly`) + Cloud Scheduler;
map custom domain; `alembic upgrade head` on Neon; suppressed baseline run; load Hayden's profile; flip
`VJA_AUTH_REQUIRED=1` + `VJA_COOKIE_SECURE=1` + `VJA_PUBLIC_BASE_URL`; add the `*.run.app` OAuth fallback URI;
real test send; `/security-review`. Full sketch in `docs/12` §9.5d.

**Branch:** `feat/cloud-deploy-9.5c` (off `main` @ `0abbb5b`).

---

## 2026-06-29 — Phase 9 · Block 9.5b: containerization (D-060)

**Second 9.5 block — packages the app as one image so 9.5c/d are pure ops.** Code+infra, no GCP needed.
One multi-stage image, **two run targets** (D-031): `vja-api` (Cloud Run service, default CMD) + `vja-nightly`
(Cloud Run Job, entrypoint override) — no second build. Plan of record: `docs/12`.

**Did:**
- **`Dockerfile`** (repo root): stage `web` = `node:24-bookworm-slim` (**Debian/glibc, not alpine** — dodges
  the musl `@rollup/rollup-linux-x64-musl` build break; matches local node v24.7) `npm ci && npm run build`;
  runtime = `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, **non-editable** `uv sync` in two cache layers
  (deps → project), copies `frontend/dist` in, `CMD vja-api --host 0.0.0.0` (honors `$PORT`). Bakes runtime
  data the wheel doesn't carry: `config/`, `migrations/`+`alembic.ini`, `data/seed/`. **No secrets/DB URL in
  the image** — all runtime env.
- **`VJA_FRONTEND_DIST`** (`app.frontend_dist_dir()` helper, replaces the `_FRONTEND_DIST` module const): the
  non-editable install moves the package off the repo layout `parents[3]/frontend/dist` assumed, so the dist
  dir is now explicit config (image sets `/app/frontend/dist`; dev/CI default to repo layout). This is what
  *unlocks* the clean (non-editable, immutable-artifact) install — editable-in-prod is the anti-pattern it
  avoids. The 9.5a serving tests now drive via the env, not the removed const.
- **`.dockerignore`**: `.venv`, `node_modules`, host `frontend/dist` (rebuilt in-image), `data/*.db`, `.git`,
  caches, `tests`/`docs`/`deploy`, local `.env`.

**Decisions:** **D-060**. INVARIANTS: SPA-serving line rewritten (`frontend_dist_dir`/`VJA_FRONTEND_DIST` +
one-image/two-entrypoints). docs/12: 9.5b → ✅ + smoke command + **fixed the stale 9.5a "awaiting commit+PR
on `feat/cloud-deploy`" header** (9.5a is merged to `main` via PR #45 @ `fd347cd`). docs/11 §3.5 gains the
containerization checkbox.

**Tests:** `tests/unit/test_api_helpers.py` (+2: `frontend_dist_dir` env-override / repo-layout default);
`tests/integration/test_serving.py` (3 funcs repointed from the removed const to `VJA_FRONTEND_DIST`).

**Verified:** full Python gate green — ruff format/check, mypy (110 files), import-linter (1/0), `uv lock
--check`, **369 pytest** (+2) on SQLite (no schema change). `docker build` clean; **local prod-parity smoke**:
`/api/health`→ok, `/` + `/upload` (catch-all) → Rolefeed SPA, `/assets/*`→200, unknown `/api`→404, binds
`0.0.0.0:8000`, both entrypoints present (601 MB image).

**Next:** **STOP for Hayden to commit + PR** (9.5b, branch `feat/containerization`). Then **9.5c — provision**
(GCP project + **Neon** PG + a `.com` via Cloudflare + Secret Manager + Artifact Registry + OAuth creds) —
ops/docs, needs the GCP project + domain. Then 9.5d cutover/go-live. See `docs/12`.

**Branch:** `feat/containerization` (off `main` @ `1775f87`, post-9.5a-PR-#45 merge).

---

## 2026-06-29 — Phase 9 · Block 9.5a: deploy-readiness app hardening (D-059)

**First 9.5 block — code-only, no infra.** Closes the app-level seams a TLS-terminating proxy (Cloud Run) +
an enforced auth gate expose, so 9.5b–d are pure packaging + ops. Surfaced by this session's loose-ends
audit; every prod behavior is **env-gated** so local dev defaults are unchanged. Plan of record:
`docs/12-cloud-deploy-plan.md`.

**Did (all `src/vja/api/`):**
- **Cookie hardening** (`auth.py`: `cookie_https_only`/`session_max_age`, `_env_truthy` factored out of
  `auth_required`): `SessionMiddleware` now gets `https_only` (`VJA_COOKIE_SECURE`, off in dev),
  `same_site="lax"` (Strict breaks Google's OAuth redirect), `max_age` (`VJA_SESSION_MAX_AGE`, 14d default).
- **HTTPS OAuth redirect_uri** (`auth.oauth_redirect_uri`): prefers `VJA_PUBLIC_BASE_URL` → `https://…/auth/
  callback` (else `url_for`), fixing the Cloud-Run `redirect_uri_mismatch`; `api_main`'s `uvicorn.run` gains
  `proxy_headers=True, forwarded_allow_ips="*"` as the fallback-path backstop.
- **SPA deep-link catch-all** (`app.py: _mount_spa`): replaced `StaticFiles(html=True)` with explicit
  `/assets` + a trailing `/{full_path:path}` → `index.html` for client routes (hard-refresh of `/upload`
  no longer 404s), real files served verbatim, unknown `/api`·`/auth` still 404. Mount gated on a real
  `index.html` (found a stale empty `frontend/dist` locally that the old `is_dir()` guard would have mounted).
- **Container bind** (`app.py: _parse_args`): `--host`/`--port` default from `VJA_API_HOST`/`PORT` (Cloud Run
  injects `$PORT`; container binds `0.0.0.0`); dev stays 127.0.0.1:8000; flags override. `load_dotenv` moved
  before parse so `.env` feeds defaults. **CORS** doc-noted only (already env-driven, same-origin in prod).
- **`.env.example`** gains the four knobs (`VJA_COOKIE_SECURE`, `VJA_SESSION_MAX_AGE`, `VJA_PUBLIC_BASE_URL`,
  `VJA_API_HOST`), all dev-safe defaults.

**Decisions:** **D-059**. INVARIANTS: SPA line (catch-all built) + login line (cookie/redirect built,
env-gated) rewritten. docs/11 §3.2 parenthetical updated. docs/12 9.5a → ✅.

**Tests:** `tests/unit/test_api_helpers.py` (+8 — cookie flag default/on, max_age default/override, redirect-uri
prefers base / falls back, parse-args env + flag override) · `tests/integration/test_serving.py` (+3 funcs —
index/assets/deeplink served; `/api`·`/auth` not masked; no mount without a real build).

**Verified:** full Python gate green — ruff format/check, mypy (110 files), import-linter (1/0), `uv lock --check`,
**367 pytest** (+12) on SQLite (no schema change → Postgres path unaffected; CI re-runs it). Frontend untouched.

**Next:** **STOP for Hayden to commit + PR** (9.5a). Then **9.5b — containerization** (multi-stage Dockerfile
building the SPA + serving under FastAPI; one image, `vja-api` + `vja-nightly` entrypoints) — also code-now, no
GCP needed. 9.5c/d (provision + cutover) wait on the GCP project + the `.com`. See `docs/12` for each block's spec.

**Branch:** `feat/cloud-deploy` (off `main` @ `250aa38`).

---

## 2026-06-29 — Doc close-out: Phase-8 Part B cash-in confirmed run (record correction)

**Not new code — fixing doc drift.** Hayden flagged that the Phase-8 Part B cash-in run *did* execute, yet
every recent entry's "Next" still listed it as "still-open (orthogonal, no code)." Confirmed against
`data/vja.db` — the run happened:
- **pipeline_runs:** #12 (2026-06-25) **2705 new** / 324 closed and #16 (2026-06-26) **2312 new** / 579
  closed — vs normal nightly deltas of ~11–78 new.
- **Extraction (Haiku):** 444 (06-25) + 655 (06-26) [+ an earlier 875 on 06-23]; nightly is ~4–24/day.
- **Matching (Sonnet):** 35 (06-25) + 184 (06-26) [+ 152 on 06-23]; nightly ~1–9/day. 425 matches total.
- **Digests:** `sent` daily through 2026-06-29 (nightly live via launchd).

The run already left a code fingerprint — **D-056** (digest closure rollup) fixed the ~922-closure wall it
exposed (pipeline_run #16's 579 closed + the 2-day backlog). What was missing was a close-out; the stale
"still-open: Part B cash-in" boilerplate got copy-pasted forward through the 9.1→9.4 "Next" sections (which,
being append-only history, are left as-written — this entry supersedes them).

**Corrected record:** Phase-8 Part B cash-in = **DONE**. Of that orthogonal pair, **only the Phenom fetcher
remains open.** No INVARIANTS/DECISIONS change (D-056 already captured the only decision the run produced).

**Worth an eye (not action):** `postings.in_scope` = 384 / 11 457; **zero `backfill`-trigger matches** (all
425 are `nightly`) — both expected (the dashboard floors on `in_scope`; no signup→backfill has run yet).

**Next:** 9.5 — cloud deploy + Postgres cutover + verified email domain + security review (+ the deferred
flips: `VJA_AUTH_REQUIRED` on, prod OAuth redirect URIs, cookie hardening, SPA deep-link catch-all). Then
Phenom (the last open Phase-8 item). This doc fix rides on the 9.5 branch.

**9.5 planned (this session) → `docs/12-cloud-deploy-plan.md`** (plan of record; survives chat resets). Four
sub-blocks: **9.5a app hardening** (cookies/proxy-HTTPS-redirect/SPA-catch-all/bind — code, testable now) ·
**9.5b containerization** (multi-stage Dockerfile — code) · **9.5c provision** (GCP project + **Neon** PG +
a `.com` via Cloudflare + Secret Manager) · **9.5d cutover/go-live** (deploy, `alembic upgrade`, suppressed
baseline run, Resend domain verify, flip auth/cookie guards, `/security-review`). Locked: **Neon not Cloud
SQL** (URL-swap ethos, ~$0), Cloud Run, buy a `.com`, **fresh DB + baseline run** (no sqlite→PG migration).
9.5a/b are code-now (no GCP needed); 9.5c/d are ops-later. **Resume by reading docs/12 → next ☐ block.**

**Branch:** `feat/cloud-deploy` (off `main` @ `250aa38`, post-9.4-PR-#44 merge).

---

## 2026-06-29 — Phase 9 · Block 9.4: multi-user frontend (Rolefeed) (D-058)

**The UI that makes 9.2 auth + 9.3 upload reachable.** Frontend-only — **no backend code touched**; every
endpoint already existed (`/auth/*`, `/api/me`, `POST /api/profiles`) and CORS already allowed credentials.
A user can now sign in with Google, upload a résumé, and see *their* matches. Product renamed **Rolefeed**
(user-facing brand; codebase/CLI stay `vja`). Four forks, all the recommended option:
1. **Routed pages** (`react-router-dom`) over conditional rendering. 2. **`VJA_AUTH_REQUIRED` stays off in
9.4** (dashboard anonymous-readable; login only gates `/upload`) — flips at 9.5. 3. **Optimistic upload
feedback** (no status endpoint, honours D-057). 4. **Credentialed fetches** so the session resolves the
user's own profile (the 9.2 seam).

**Did (all in `frontend/`):**
- **Branding → Rolefeed:** wordmark (`$ rolefeed▮`), `index.html` `<title>`, `package.json` name/description.
- **Routing:** added `react-router-dom`; `main.tsx` wraps `<BrowserRouter><AuthProvider>`; `App.tsx` is now
  the shell (brand + auth-aware nav) + `<Routes>`. Old App body extracted verbatim → `pages/Dashboard.tsx`
  (behaviour unchanged; its data-flow tests moved to `Dashboard.test.tsx`).
- **Auth client:** `api.ts` gains `credentials: "include"` on every call + `loginUrl`/`fetchMe`/`logout`/
  `uploadResume` (+ typed `ApiError` carrying status + server `detail`, `User`/`ProfileCreated` types).
  `auth/useAuth.ts` (context+hook, no component → clean Fast-Refresh) + `auth/AuthProvider.tsx` (probes
  `/api/me` once; 401 ⇒ anonymous, a valid state).
- **Pages:** `Login.tsx` (Google sign-in anchor → `loginUrl()`), `Upload.tsx` (soft-gated → `/login`;
  vertical select + file input → `uploadResume` → optimistic "résumé received (v{n})" + dashboard link;
  413/422/429 surface inline). New CSS in `theme.css` (nav, panel, btn, form, subbar).

**Decisions:** **D-058**. INVARIANTS: D-042 SPA line rewritten (Rolefeed, routes, credentialed fetches,
deep-link caveat) + new résumé-upload-surface line; auth-gate line now "stays off through 9.4". CLAUDE.md
Phase 9 list 9.4 ✅. docs/11 §3.2 gains the frontend-UI checkbox + auth-gate note.

**Tests:** frontend gate green — eslint (0 warnings), `tsc -b --noEmit`, **vitest 34 passed** (8 files; +
`api` upload/login/me, `AuthProvider`, `Login`, `Upload`, `App` shell/nav; `Dashboard` carries the old App
tests). `npm run build` bundles clean (tsc + vite). No Python touched → backend suite unaffected.

**Known follow-up (9.5, noted in D-058/docs):** prod `StaticFiles(html=True)` 404s a hard-refresh of
`/upload`|`/login` (client-side nav is fine) — needs a catch-all → `index.html` at deploy, alongside the
`VJA_AUTH_REQUIRED` flip + prod OAuth redirect URIs + cookie hardening.

**Next:** **STOP for Hayden to commit + PR** (9.4). Then **9.5 — cloud deploy + Postgres cutover + verified
email domain + security review** (+ the deferred flips above). Still-open orthogonal (no code): Phase-8
Part B cash-in run + the Phenom fetcher. Optional dev check: a real Google round-trip locally (set
`GOOGLE_CLIENT_*` + `VJA_SESSION_SECRET`, run FastAPI :8000 + `VITE_API_BASE=…:8000 npm run dev`).

**Branch:** `feat/multi-user-frontend` (off `main` @ `d5864db`, post-9.3-PR-#43 merge). *(Prior WORKLOG entry
was stale — its "STOP to commit+PR 9.3" already happened as PR #43.)*

---

## 2026-06-27 — Phase 9 · Block 9.3: résumé upload + signup→backfill + cost guards (D-057)

**The product's first write path.** A logged-in user uploads a résumé → a profile is created → the D-039
signup backfill matches it against the last 5 days of open postings. Backend-only (upload UI is 9.4; prod
hardening is 9.5). Four forks, all run through Hayden taking the recommended option:
1. **Formats = text/markdown + text PDF** (`pypdf`), scanned/OCR deferred. 2. **Background backfill** (202 +
`profile_id`, `run_backfill` as a threadpool `BackgroundTask`) over inline-sync / defer-to-nightly.
3. **Cost guards = per-backfill cap + global daily ceiling**, skip cooldown, defer captcha/edge to 9.5.
4. **`POST /api/profiles` (multipart), no status endpoint** (no schema change).

**Did:**
- **`src/vja/resume.py`** (new leaf, D-033 adapter): `extract_resume_text(filename, data)` — UTF-8
  text/markdown + text-PDF (`pypdf`, routed by `%PDF-` magic or `.pdf`); scanned/empty/non-text/oversize/
  too-long all raise `ResumeError`. **Never logs the text/bytes** (PII, docs/11 §3.1). New deps `pypdf` +
  `python-multipart` (FastAPI form parsing).
- **Cost guards** (`match.py` + `db/matches.py`): `_match_profile` gains `max_postings`; `run_backfill`
  passes `VJA_BACKFILL_MAX_POSTINGS` (default 100) — **nightly stays uncapped** (`None`). `count_matches_since`
  + `estimate_daily_spend` (count since midnight × `_NOMINAL_MATCH_USD` ~$0.01, no per-match ledger) +
  `check_backfill_budget` raising `BackfillBudgetExceeded` over `VJA_DAILY_LLM_BUDGET_USD` (default $5).
- **profiles repo:** `upsert_profile` gains `user_id` (stamped on insert + reactivate; CLI path unchanged →
  NULL→linked-by-email per D-055); new `get_profile(engine, id)`.
- **`POST /api/profiles`** (`api/app.py`, behind `require_user`): budget→file-read(413)→adapter(422)→
  vertical config(404)→`upsert_profile(user_id=…)`→`get_profile`→`BackgroundTasks(run_backfill)`→**202**
  `{profile_id, vertical, resume_version}`. `run_backfill` referenced as a module global (monkeypatchable).
  `.env.example` gains the two guard knobs.

**Decisions:** **D-057**. INVARIANTS: Cost & safety gains the guard line; Auth & identity gains the
first-write-endpoint line; the backfill line now notes the posting cap. docs/11 §3.3 backfill-guard box
ticked + rate-limit/captcha deferral noted; §3.1 PII-logging note. CLAUDE.md Phase 9 block list (9.1–9.3 ✅).

**Tests:** `tests/unit/test_resume.py` (+11 — text/md/PDF extraction via a hand-built correct-xref PDF;
scanned/unreadable/non-UTF8/empty/whitespace/oversize/too-long rejections). `test_backfill.py` (+4 — cap
slices to N; `estimate_daily_spend` arithmetic; budget raises over / passes under). `test_api.py` (+6 —
upload 401-unauth / 202 creates+links `user_id`+triggers backfill / 422 bad file / 404 unknown vertical /
429 over budget / 413 oversize; `run_backfill` stubbed so the BackgroundTask never hits Anthropic).

**Verified:** full Python gate green — ruff format/check, mypy (108 files), lint-imports (1 kept/0 broken),
`uv lock --check` in sync, **355 pytest** (+21) on SQLite (Postgres via `VJA_TEST_DATABASE_URL` when set —
no new schema, so the dialect path is unaffected). No migration this block (no schema change).

**Next:** **STOP for Hayden to commit + PR** (9.3). Then **9.4 — multi-user frontend** (login UI + résumé
upload form over this endpoint + signup→backfill UX). Still-open (orthogonal, no code): the Phase-8 Part B
cash-in run + the Phenom fetcher. Optional outward-facing follow-up: send the held digest (re-check baseline
first).

**Branch:** `feat/resume-upload-backfill` (off `main` @ `8d03159`, post-9.2-PR-#41 / D-056-PR-#42 merge).

---

## 2026-06-26 — Pre-9.3: summarize digest closures by company (D-056)

**Did:** Render-only fix to the digest-quality bug the Phase-8 cash-in run exposed — the body listed every
closed role as one bullet, so a 2-day backlog (~940 closures: Boeing 241, GE Vernova 147, Airbus 134…) would
render as a wall burying the ~66 new roles (kill-criterion violation; the nightly would re-send it unattended).
`src/vja/digest/render.py`: **≤10 closures enumerate as before; >10 roll up by company** —
`N roles across C companies:` + top-10 (`• Company — n`, count desc via `Counter.most_common`) +
`…and M more companies (P roles)` tail, with `_plural` for company/role singular-plural. Symmetric in text +
HTML (new `_closed_html`, `_rollup_split` shared). **Subject keeps the true count; `contents_to_dict` keeps the
full closed list** — only the human-facing body summarizes (audit/D-037 completeness intact). New/quarantine
paths untouched; no DB/schema/dep change.

**Decisions:** **D-056** (dual-mode, threshold 10, company rollup; body-only). INVARIANTS digest section gains
the closure-rollup line.

**Tests:** `tests/unit/test_digest_render.py` +5 — many-closures rollup (subject true count, per-company counts,
no per-role enumeration), tail collapse + singular wording (11 single-role companies), the 10/11 boundary
(incl. "1 company" singular), few-closures-stay-detailed, audit-keeps-all-15-when-summarized. Failing-first
repro per D-021.

**Verified:** eyeballed the real 922-closure backlog shape → 11 lines, new role on top, subject "922 closed".
Full Python gate green — ruff format/check, ruff, mypy (106 files), lint-imports (1/0), `uv lock --check` (no
new deps), **334 pytest** (+5). Render-only → Postgres path unaffected (no SQL touched).

**Next:** **STOP for Hayden to commit + PR.** Then **9.3 — résumé upload + signup→backfill + cost/abuse guards**
(behind `require_user`, D-055). **Optional follow-up (outward-facing, confirm first):** send the held digest —
re-check current baseline/state, since nightly/data may have moved since the cash-in.

**Branch:** `fix/digest-closure-summary` (off `main` @ `bf76767`, post-9.2-PR-#41 merge).

---

## 2026-06-26 — Phase 9 · Block 9.2: auth foundation — Google OAuth + `users` + read-API authz (D-055)

**Built the layer 9.3 depends on** (its résumé-upload / signup→backfill write endpoints sit behind login).
Three forks run through Hayden, all taking the recommended option:
1. **Real Google OAuth, exercised locally** (not stubbed-till-deploy) — so 9.3's writes are genuinely
   gateable now. 2. **`users` table + nullable `profiles.user_id` FK** (not email-as-sole-key) — clean
   multi-user shape, migration trivial + born-on-both-dialects (D-054). 3. **Authz layer + deferred hard
   enforcement** (not auth-required-now) — local dashboard stays usable before the 9.4 login UI; existing
   API tests stay green.

**Did:**
- **Schema/migration** (`db/schema.py` + `7d5b69c46786`): `users` (`google_sub` uniq/nullable, `email`
  uniq/not-null, `name`, `created_at`) + nullable `profiles.user_id` FK. `op.batch_alter_table` so the FK
  lands on SQLite (table rebuild) and Postgres alike. Hand-fixed the autogen to render `UTCDateTime` as
  `sa.DateTime(timezone=True)` (repo convention) and name the FK; `alembic check` → no drift.
- **`db/users.py`:** `upsert_user_by_google` (idempotent on `sub` → adopt email-only row → insert) +
  `_link_profiles` (backfills `profiles.user_id` by email = the D-027→FK bridge, so the seed profile
  attaches on first login) + `get_user`. `profiles.user_email` kept → match/digest/nightly untouched.
- **`api/auth.py`:** Authlib Google OIDC registry (inert/503 until `GOOGLE_CLIENT_*`; lazy discovery),
  `get_current_user`/`require_user` deps, `auth_required()` reading `VJA_AUTH_REQUIRED`, `session_secret()`.
- **`api/app.py`:** `SessionMiddleware`; `/auth/login` + `/auth/callback` (exchange → upsert+link → session
  → redirect) + `/auth/logout` + `/api/me`; `_resolve_profile(…, user)` — authed resolves own profile (403
  on another's `profile_id`), unauthenticated keeps the single-active default, `VJA_AUTH_REQUIRED` ⇒ 401.
- **Deps/config:** `authlib` + `itsdangerous` (`uv lock`); mypy override for un-stubbed authlib; `.env.example`
  gains `GOOGLE_CLIENT_ID/SECRET`, `VJA_SESSION_SECRET`, `VJA_AUTH_REQUIRED` + the localhost redirect note.
- **Migration bug found in the live login (D-021):** the first real OAuth login 500'd on `no such table: users`
  — the prod `vja.db` hadn't been upgraded. Upgrading then crashed: the `profiles.user_id` **batch rebuild**
  (SQLite can't add a FK in place) drops+recreates `profiles`, and with `PRAGMA foreign_keys=ON` (the app's
  runtime setting, which `migrations/env.py` was inheriting via `get_engine`) the DROP tripped `matches → profiles`
  on the **populated** DB. The empty-table fixture never hit it. **Fix:** `env.py` now runs migrations on a
  dedicated engine with **SQLite FKs OFF** (set at connect — the pragma is a no-op in a txn; the app keeps FKs
  ON) — exactly SQLite's documented ALTER procedure. Regression test `test_add_user_id_on_populated_db` seeds a
  `matches`→`profiles` row, upgrades, asserts success + data preserved. Real `vja.db` then migrated cleanly
  (backed up first; 3 profiles / 394 matches / 11 327 postings intact) after clearing the partial-migration
  orphans (`users` + `_alembic_tmp_profiles`) the aborted first attempt left behind (alembic uses
  non-transactional DDL on SQLite, so the failed run isn't atomic).

**Decisions:** **D-055**. INVARIANTS gains an **Auth & identity** section; docs/11 §3.2 (users+authz) ticked,
§2 seam status updated.

**Tests:** new `tests/integration/test_auth.py` (users-repo idempotency/email-adoption/profile-link;
login 503-unconfigured + redirect-to-Google; callback creates+links+sessions with the token exchange
mocked; `/api/me` 401/200; logout). Extended `test_api.py` with authz (own-profile resolution, 403 on
another's id, `VJA_AUTH_REQUIRED` 401). The live Google handshake is a **manual** check, not in the suite.

**Verified:** full Python gate green — ruff format/check, mypy (106 files), lint-imports (1 kept/0 broken),
`uv lock --check` in sync, **329 pytest on SQLite and 329 on Postgres** (local PG 15 throwaway on :5433,
Docker still unavailable; CI uses 16) — the `users`+FK migration proven on both dialects (D-054), incl. the
new populated-DB regression. **Live login verified end-to-end:** `/auth/login` 302s to Google with the real
client (live OIDC discovery), the callback authenticated + created the user after the migration fix.

**Next:** **STOP for Hayden to commit + PR** (9.2). Hayden provisions the Google OAuth client (consent
screen + Web credentials, redirect `http://localhost:8000/auth/callback`) to run the manual login check.
Then **9.3 — résumé upload + signup→backfill + cost/abuse guards** (behind `require_user`). Still-open
(orthogonal, no code): the Phase-8 Part B cash-in run + the Phenom fetcher.

**Branch:** `feat/auth-foundation` (off `main` @ `30ac867`, post-9.1-PR-#40 merge).

---

## 2026-06-26 — Phase 9 plan + Block 9.1: Postgres path CI-verified on both dialects (D-054)

**Planned Phase 9** (cloud + multi-user product, D-047) into 5 PR-sized blocks and built the first.
Reasoning with Hayden reframed his "frontend-first" instinct: two of the three "frontend" items are
full-stack and order-coupled — résumé **upload** is the first *write* endpoint (API is read-only by
invariant, D-005/D-041) and spends LLM tokens via signup→backfill (§3.3), so it sits **behind login**;
the vertical **toggle** is dropped as a user feature (1-vertical-per-user limiter → a real user only sees
their own vertical). Accepted leans: **Google OAuth** (zero passwords), **GCP** (Cloud Run + Cloud Run Job
via Cloud Scheduler — the D-031 trigger swap — + Cloud SQL + Secret Manager), **1-vertical/user** default.
Block order of record: **9.1 Postgres-CI spine** ✅ · 9.2 auth (OAuth + `users` + authz) · 9.3 résumé
upload + signup→backfill + cost/abuse guards (gated by auth) · 9.4 multi-user frontend · 9.5 cloud deploy +
full Postgres cutover + verified email domain + security review.

**Did (9.1):** turned D-025's "just a URL swap + `alembic upgrade`" from faith into a CI gate, so every later
block's security/PII tables are born-on-Postgres-verified. **Zero behavior change.**
- `psycopg[binary]>=3.2` → `[project.dependencies]` (SQLAlchemy-native `postgresql+psycopg://`); SQLite stays
  the default. `uv lock` (3 new pkgs: psycopg, psycopg-binary, tzdata).
- `tests/conftest.py`: the single `migrated_engine` fixture honors `VJA_TEST_DATABASE_URL` — unset → today's
  `tmp_path` SQLite (unchanged); set → that Postgres with a per-test `DROP SCHEMA public CASCADE; CREATE
  SCHEMA public` before `alembic upgrade head` (clean isolation on one shared service DB, no dependence on
  migration `downgrade()`s).
- `.github/workflows/ci.yml`: new `postgres` job (service `postgres:16`) re-runs the offline suite with the
  env var set. pytest-only (lint/types/imports/lock/frontend are dialect-agnostic — covered by `gates`).

**Decisions:** **D-054** (Postgres path CI-verified on both dialects; psycopg; per-test schema reset; no
dialect gaps found). INVARIANTS DB line updated; docs/11 §1 DB row + §3.5 first item ticked.

**Dialect gaps:** **none.** The 315-test suite (schema built via `alembic upgrade head` per test → migrations
exercised) passed on Postgres first run. The Core portability choices held: `native_enum=False` VARCHAR+CHECK
enums, `UTCDateTime` over `DateTime(timezone=True)` (→ `timestamptz`), `sa.JSON`, integer `server_default`s.

**Verified:** **315 pytest on Postgres** (local PG 15, throwaway instance — Docker unavailable, so a Homebrew
`postgresql@15` datadir on :5433; CI uses 16) **and 315 on SQLite**; full Python gate green — ruff
format/check, mypy (103 files), lint-imports (1 kept/0 broken), `uv lock --check` in sync.

**Next:** **STOP for Hayden to commit + PR** (9.1). Then **9.2 — auth foundation** (Google OAuth + `users`
table + read-API authz, plugging the docs/11 §2 `(vertical, profile_id)` seam). Still-open from the prior
session (orthogonal, no code): the Phase-8 **Part B cash-in run** (`vja-import-employers` → `vja-run` →
extract → match) and the **Phenom** fetcher — neither blocks Phase 9.

**Branch:** `feat/postgres-ci-portability` (off `main` @ `7516e91`, post-D-053-PR-#39 merge).

---

## 2026-06-25 — Re-opened-posting fix (D-053) — unblocking the Phase-8 cash-in run

**Did:** Session task was "reason on next steps." Reasoned that Phase 8 had shipped 5 fetchers (39→44
coverage) with **zero paid pipeline runs** since the aviation vertical — coverage was theoretical. Chose
to **cash in the coverage** with a real extract→match run before building more (Phenom). The free
count-gate (`vja-run`) surfaced **two blockers** before any spend:
- **Stale DB (free fix):** `vja-import-employers` was never re-run after the Phase-8 seed edits → the 8
  verified P8 tenants (Constellation/Exelon/SIG/ICE/SITA/NextEra/Southern/Vitol) sat as stale
  `detected`/`layer2` rows with no endpoint ("cannot build endpoint"); 7 correctly-parked tenants were
  stale-`active` and wrongly attempted. Seed is correct + importer is a `(vertical,name)` upsert → one
  re-import fixes all 15. **Deferred to the operational Part B** (after this PR merges).
- **Re-opened-posting bug (this PR):** 10 employers (Vistra, S&P Global, Jane Street, AES, Xcel, Fluence,
  Shell Trading, Yes Energy, Wood Mac, Kraken) crashed with `UNIQUE constraint failed:
  postings.employer_id, postings.external_id` — a posting that closed (D-009, never deleted) then
  reappeared landed in `diff.new`, and `insert_posting` collided with the surviving closed row, aborting
  the employer's whole transaction (new + closures discarded).

**Fix:** `sync_employer` now intersects `diff.new` with a new `closed_index` and routes a reappeared id to
a new `reopen_posting` (UPDATE in place) instead of `insert_posting`. Reopen **resets `first_seen_at`** so
the role surfaces as new again (Hayden's call over "reopen silently"); clears `extracted_at` only when the
body's `content_hash` moved (cache-aware, D-035); same non-NULL `source_updated_at` guard as `bump`.
`diff.py` stays pure set arithmetic. A `reopened` counter rides `SyncResult`/`RunSummary` + the
`vja-run`/nightly summary lines (observability only — `pipeline_runs.postings_new` keeps counting true
inserts; no schema change).

**Decisions:** **D-053** (reopen-in-place + surface-as-new + cache-aware re-extract + reopened
observability-only). INVARIANTS diff/data-model section gains the reopen line (next to D-009).

**Tests:** `tests/integration/test_pipeline.py` +3 — reopen resurrects the same row (no IntegrityError,
`first_seen_at` advanced, counted `reopened` not `new`); changed-body reopen clears `extracted_at`;
identical-body reopen preserves the cached extraction. The production `vja-run` crash is the
failing-in-prod repro (D-021). 14 pass in the file.

**Verified:** full Python gate green — ruff format/check, mypy (42 files), lint-imports (1 kept/0 broken),
**315 pytest** (+3), `uv lock --check` in sync (no new deps).

**Next:** **STOP for Hayden to commit + PR.** Then **Part B (operational, no code):** `vja-import-employers`
→ `vja-run` (now clean) → count-gate + authorize → `vja-extract` (Haiku) → `vja-match` (Sonnet) → look at
the digest/dashboard. The BP Trading single Workday job missing `externalPath` is an isolated, non-blocking
upstream data quirk to note, not fix. Then Phenom (the deferred Phase-8 build order) once the cash-in
proves the current coverage's worth.

**Branch:** `fix/reopen-closed-postings` (off `main` @ `78693c0`, post-Radancy-PR-#38 merge).

---

## 2026-06-24 — Phase 8 · Block 4: Radancy/TalentBrew Tier-C fetcher + platform-probe resequence (D-052)

**Did:** With Tier-B done, the docs' next item was the generic Layer-2 **LLM-read** tail. A Step-0
reconnaissance pass changed the plan.

- **Research → decision (both run through Hayden):** live-probed the `custom`/`layer2` tail and found it's
  mostly **JS-rendered SPAs or bot-blocked** (United/Southwest = Phenom shells, NextEra = Radancy, Aurora =
  React, GridStatus = 403, Mercuria = marketing page) — served HTML carries almost no job content, so a
  literal "LLM-read-the-page" fetcher would read nothing on the employers that matter. **Decision 1:** probe
  the two big multi-tenant platforms (Phenom, Radancy) for a clean API *before* the LLM-read (the iCIMS
  lesson, D-048; faithful to D-017). **Decision 2:** Radancy first (grid priority, D-022); Phenom next.
- **Step-0 crack (Radancy):** the JS landing page is empty, but `GET {endpoint}/search-jobs/results?
  CurrentPage=&RecordsPerPage=&SearchType=5` returns the jobs **server-rendered** in a
  `<table id="searchresults">` (uniform TalentBrew markup → one generic fetcher). Always HTML
  (`Accept: json` ignored) → an **HTML-parse** fetcher (the repo's first; +`beautifulsoup4`). Total from the
  table `aria-label` ("Results 1 to 25 of 288"); rows in `tr.data-row`; the `/job/{slug}/{id}` link gives id
  + apply_url, the `jobLocation`/`jobDate` cells give location + a real date. Captured 2 fixtures (NextEra
  list + one job detail, D-019).
- **Fetcher** (`src/vja/fetchers/radancy.py`): list-only + **paginate-or-fail** on the aria-label total
  (mis-parse/short-tally → `FetchError`, never a partial → no false closures) + lazy `fetch_detail`
  (`div.jobdescription`, routed by the same `extract._DETAIL_RESOLVERS` map — now 4). `external_id` = the
  `/job/{slug}/{id}` **path** (Workday `externalPath` parity — the detail URL needs the slug; the id alone
  302s to an error page; and `fetch_detail(employer, external_id)` can't widen without coupling fetchers to
  the db layer / breaking import-linter). `updated_at` from `jobDate` parsed `%b %d, %Y` → ISO (a D-030 win
  Workday lacks). Endpoint is **explicit per-tenant** (no slug). Wired into the registry + resolver map.
- **Seed:** NextEra `layer2 → verified` (endpoint = search base; 288 open at probe). NRG/National Grid/
  L3Harris **parked `proposed`/`detected`, kept `radancy`** (NRG 200 but different results markup; National
  Grid 403; L3Harris 301) — because wiring `RADANCY` into `SUPPORTED_ATS_TYPES` means
  `active_fetchable_employers` would otherwise select an endpointless active row and fail (the D-051
  invariant; Workday P4.2 parked-tenant precedent, D-032). Coverage **43→44** (grid 32→33).

**Decisions:** **D-052** (probe-platforms-before-LLM-read resequence + Radancy via server-rendered
`/search-jobs/results` HTML; HTML-parse fetcher; list-only + paginate-or-fail + lazy detail; path-as-id;
`bs4` dep; NextEra onboarded, 3 parked; 43→44). INVARIANTS (fetcher-order line + new Radancy contract line +
the resolver-map line now 4), `docs/07` (platform table split, build-order items 7–10, endpoint encoding,
coverage math 59%→61%), CLAUDE Phase-8 line, `data/seed/README.md` both status blocks.

**Tests:** `tests/unit/test_radancy.py` (16: real-fixture golden mapping + total parse, single-page,
pagination by CurrentPage, paginate-or-fail/truncation, mid-pagination error, empty board, missing
table/total, row missing link/title, missing location+date, unparseable date, HTTP 500, `fetch_detail`
description + error-page redirect + HTTP error); `tests/live/test_radancy_live.py` (opt-in NextEra smoke +
detail-has-description); `test_extract.py` (parametrized Radancy lazy-detail dispatch); `test_registry.py`
(Radancy supported); `test_employers_import.py` counts (43→44, +Radancy; endpoint-or-slug invariant relaxed
since Radancy is endpoint-only).

**Verified:** full Python gate green — ruff format/check, mypy (103 files), lint-imports (1/0, no new layer
edge), **312 pytest** (+17), `uv lock` in sync (1 new dep: `beautifulsoup4`). Live smoke (2): NextEra returns
well-formed postings + apply_url under `/job/`; `fetch_detail` returns a real description body.

**Next:** **STOP for Hayden to commit + PR** (Block 4). Then **Phenom** (the `/widgets/` JSON API — United/
Southwest/Thales), then Tier-C singletons, then the Layer-2 LLM-read tail for the genuinely-custom remainder.
NRG/National Grid/L3Harris await a verified search base (config-only onboard). No paid extract/match run yet.

**Branch:** `feat/radancy-fetcher` (off `main` @ `bad8ede`, post-Block-3-PR-#37 merge).

---

## 2026-06-24 — Phase 8 · Block 3: SmartRecruiters + Oracle HCM Tier-B fetchers (D-050, D-051)

**Did:** Built the next two Phase-8 (Tier-B) fetchers in one combined PR (Hayden's call), completing the
documented build order's Tier-B set (iCIMS → Workable → **SmartRecruiters → Oracle**). Both are list-only
for the description, so both reuse — and generalize — Workday's lazy-detail path.

- **Step-0 feasibility probe (the gate):** live-probed both APIs. **SmartRecruiters** =
  `api.smartrecruiters.com/v1/companies/{slug}/postings` — clean JSON, `totalFound`/offset pagination,
  uniform → one generic fetcher (Vitol slug `Vitol`, 42 open). **Oracle ORC** =
  `{host}/hcmRestApi/.../recruitingCEJobRequisitions?…&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={CX_n}`
  — clean JSON, `TotalJobsCount` pagination (Southern Co: `emje.fa.us6`, `CX_1001`, 105 open). Two probe
  findings shaped the build: (1) **both lists omit the description** (SR has none; Oracle's `External*Str`
  are empty in list mode) → both are list-only like Workday, not iCIMS-rich; (2) Oracle's `expand` param
  is **required** (without it: no `requisitionList`). Captured 4 fixtures (list + detail each, D-019).
- **SmartRecruiters fetcher** (`src/vja/fetchers/smartrecruiters.py`): list-only + paginate-or-fail on
  `totalFound` + `fetch_detail` (the `jobAd.sections` body). `apply_url` **constructed**
  (`jobs.smartrecruiters.com/{slug}/{id}`, verified 200 — no detail fetch for the link, D-008);
  `external_id = id` (D-016); `location` from `fullLocation` with empty comma-segments collapsed;
  `updated_at = releasedDate` (D-030). Slug-derivable → added to `endpoints.py` `_DERIVED_TEMPLATES`.
- **Oracle fetcher** (`src/vja/fetchers/oracle.py`): list-only + paginate-or-fail on `TotalJobsCount`
  (limit/offset appended as `finder` sub-params) + `fetch_detail` (the `ExternalDescriptionStr` body,
  host + siteNumber parsed off the seeded list endpoint). `apply_url = {careers_url}/job/{Id}` (verified);
  `external_id = Id`; `location = PrimaryLocation`; `updated_at = PostedDate`. Explicit per-tenant endpoint
  (no `endpoints.py` change). Both wired into the registry.
- **Generalized the lazy-detail dispatch** (`src/vja/extract.py`): the Workday-only `if` in `_source_text`
  is now a per-ATS `_DETAIL_RESOLVERS` map (Workday + SmartRecruiters + Oracle); the default resolver
  dispatches by `ats_type`. Adding a list-only ATS is now a one-line wire-up. Injection point stays a
  single callable (existing tests unchanged in shape).
- **Seed (config/data):** Vitol `detected → verified` (slug `Vitol`); Southern Company `detected →
  verified` (Oracle list endpoint w/ `siteNumber=CX_1001`). **Honeywell + Con Edison reclassified
  `oracle_hcm/detected → custom/layer2`** — their clean ORC host isn't exposed (Honeywell's vanity domain
  proxies the REST API 302→404; Con Edison stays on coned.com). This preserves the "supported `ats_type` ⟹
  has a working endpoint" seed invariant (`active_fetchable_employers` filters only on status + supported
  ATS, so an endpointless oracle_hcm row would otherwise be selected and fail). Notes say to flip back to
  `oracle_hcm` + add the endpoint when a host is curated. Coverage **41→43** (grid 30→32; aviation 11).

**Decisions:** **D-050** (SmartRecruiters via the public postings API; slug-derived; list-only + lazy
detail; apply_url constructed; 41→42). **D-051** (Oracle ORC via the CE REST API; explicit per-tenant
endpoint; list-only + lazy detail; Southern onboarded, Honeywell/ConEd → Layer 2 pending curation; 42→43).
INVARIANTS (fetcher-order line + SR/Oracle contract lines + the new resolver-map line), `docs/07` (table +
build-order + encoding + coverage math), CLAUDE Phase-8 line, `data/seed/README.md` both status blocks.

**Tests:** `tests/unit/test_smartrecruiters.py` (19) + `tests/unit/test_oracle.py` (19) — fixture mapping,
apply_url construction, pagination, paginate-or-fail/truncation, mid-pagination error, location handling,
`fetch_detail` mapping + siteNumber/host parse, every transport/parse/shape/missing-field → `FetchError`;
`tests/live/test_{smartrecruiters,oracle}_live.py` (opt-in Vitol/Southern smoke + detail-has-description);
`test_extract.py` (parametrized SR/Oracle lazy-detail dispatch); `test_registry.py` (both supported;
unsupported example switched to Jobvite); `test_endpoints.py` (SR slug-derivation); `test_employers_import.py`
counts (41→43, +SmartRecruiters/+Oracle; grid fetchable 30→32).

**Verified:** full Python gate green — ruff format/check, mypy (100 files), lint-imports (1/0), **295 pytest**
(+38), `uv lock` in sync (no new deps). Live smoke (4): Vitol 42 well-formed postings + detail body; Southern
Co 105 + detail body; both `updated_at` populated, apply_url resolves.

**Next:** **STOP for Hayden to commit + PR** (Block 3). Tier-B fetchers are now complete; next is the
**Layer-2 LLM-read tail** (the custom/portal remainder + HN/niche). Honeywell + Con Edison await curation
(canonical Oracle host + siteNumber → config-only onboard). No paid extract/match run yet.

**Branch:** `feat/smartrecruiters-oracle-fetchers` (off `main` @ `06b77e4`, post-Workable-PR-#36 merge).

---

## 2026-06-24 — Phase 8 · Block 2: Workable Tier-B fetcher via the embed-widget API (D-049)

**Did:** Built the second Phase-8 (Tier-B) fetcher — Workable — following the documented build order
(iCIMS → **Workable** → SmartRecruiters/Oracle → Layer-2 tail). Chose Workable over the other Tier-B
targets because it's the most de-risked (clean slug-derivable JSON, one tenant already verified).

- **Step 0 feasibility probe (the gate):** live-probed `apply.workable.com/api/v1/widget/accounts/{slug}`
  across both seed tenants. Clean, unauthenticated JSON, **uniform** → one generic fetcher (D-017/D-004).
  Two findings that shaped the contract: (1) the widget returns **all open jobs in one response** —
  `{"name","description","jobs":[…]}`, **no `total`/pagination** — so it's a single-response ATS like
  Greenhouse/Lever, *not* paginate-or-fail like iCIMS/Workday; (2) **`?details=true` is required** for the
  inline `description` HTML. Vortexa = 5 open, Energy Aspects = 0 (matches its historical probe). Captured
  `tests/fixtures/workable.json` (Vortexa, D-019).
- **Fetcher** (`src/vja/fetchers/workable.py`, `WorkableFetcher`): modeled on Greenhouse (single GET +
  map-all). False-closure guard = the **single-request contract** (clean 200 = complete set; empty `jobs`
  = legitimate 0 open; any transport/parse/shape error → `FetchError`, diff never runs on a partial). Map:
  `external_id = shortcode` (D-016), `apply_url = url` (public posting page), `location` = `city, state,
  country` joined (full names → better Stage-B US signal than the bare ISO codes in `locations[]`),
  `updated_at = published_on` (a D-030 freshness win — no detail fetch), `description` inline HTML.
- **Endpoint derivation:** added Workable to `endpoints.py` `_DERIVED_TEMPLATES` (slug-derived, per
  `docs/07`; host is uniform, unlike iCIMS's per-tenant careers domains), template includes `?details=true`.
  Wired into the registry.
- **Seed (config/data):** Vortexa `detected → verified` (slug `vortexa`, 5 open); Energy Aspects re-verified
  (API valid, 0 open). Both now fetchable → grid 28→30, total **39→41**.

**Decisions:** **D-049** (Workable via the embed-widget API; slug-derivable; single-response false-closure
guard; coverage 39→41). INVARIANTS (fetcher-order line + new Workable contract line), `docs/07` (table +
build-order + resolved Vortexa fixup), CLAUDE Phase-8 line, `data/seed/README.md` grid status block updated.

**Tests:** `tests/unit/test_workable.py` (11: fixture mapping, single-response/all-jobs, empty board,
`created_at` fallback, missing-location→None, transport/HTTP-500/non-JSON/missing-`jobs`/missing-`shortcode`/
empty-field → `FetchError`); `tests/live/test_workable_live.py` (opt-in Vortexa smoke); `test_endpoints.py`
(Workable slug-derivation); `test_registry.py` (Workable now supported); `test_employers_import.py` counts
(39→41, +2 Workable; grid fetchable 28→30).

**Verified:** full Python gate green — ruff format/check, mypy (94 files), lint-imports (1/0), **257 pytest**
(+12), `uv lock` in sync (no new deps). Live smoke: Vortexa returns 5 well-formed postings with populated
`updated_at`.

**Next:** **STOP for Hayden to commit + PR** (Block 2). Then the rest of Tier-B (SmartRecruiters — 1, clean
public API; Oracle HCM — 3, per-tenant ORC), then the Layer-2 LLM-read tail. No paid extract/match run yet.

**Branch:** `feat/workable-fetcher` (off `main` @ `ae5cb12`, post-Block-1 merge + Sabre/Amadeus).

---

## 2026-06-24 — Phase 8 · Block 1: iCIMS Tier-B fetcher via the Jibe `/api/jobs` API (D-048)

**Did:** Built the first Phase-8 (Tier-B) fetcher, kicked off by a coverage-research pass.

- **Research first (Hayden's three questions):** we fetch only **34%** of the seeded universe (grid 24/54,
  aviation 7/36); the aviation vertical looked empty (3 companies, only Boeing matching) purely for lack of
  coverage. **Garmin** — a near-perfect missed role — was seeded `custom`/`layer2` but is actually **iCIMS**.
  Decided iCIMS leads Phase 8 (highest coverage + fixes the felt gap). Shared the 38-row `layer2` tail with
  Hayden for parallel digging.
- **Step 0 feasibility probe (the gate):** the legacy `careers-{tenant}.icims.com` portal is a frame-busted
  SPA (domReplacement, no clean JSON), **but** the modern iCIMS **Career Sites (Jibe)** product exposes a clean,
  unauthenticated `GET {careers_base}/api/jobs?page&limit` → `{"jobs":[{"data":…}],"totalCount":…}`. Verified
  **uniform across tenants** (Garmin/Constellation/Exelon/SIG/ICE/SITA share every core field) → **one generic
  fetcher** works (D-017/D-004 risk retired). Captured `tests/fixtures/icims.json` (D-019).
- **Fetcher** (`src/vja/fetchers/icims.py`, `IcimsFetcher`): paginate-or-fail like Workday, but the rich list
  payload gives `apply_url` + full `description` (overview+responsibilities+qualifications joined) + real ISO
  `update_date` — **no detail fetch**, and `updated_at` populated (D-030 freshness win). `external_id = req_id`
  (D-016). Wired into the registry; endpoint is explicit per-tenant (careers domains vary), so no `endpoints.py`
  change.
- **Seed (config/data):** onboarded 6 Jibe tenants (Garmin custom→icims; Constellation/Exelon/SIG/ICE/SITA
  detected→verified, `+/api/jobs` endpoints + client_code slugs). **Alaska** (legacy portal, no Jibe API) and
  **Joby** (`/api/jobs` 404, custom site) reclassified detected→`layer2`. Fixed 2 pre-existing malformed CSV
  rows (Exelon stray trailing field; Enverus unquoted comma) — seed is now clean 14-col throughout.
- **Tail re-probe:** D-015 fingerprint over all 38 `layer2` rows found **no other Jibe tenants** (Garmin was
  the only misfile) but surfaced **Amadeus + Sabre = Workday** candidates → a later data-only PR.

**Decisions:** **D-048** (iCIMS via the Jibe career-site API; legacy/non-Jibe/auth-gated → Layer 2; coverage
31→37). INVARIANTS (fetcher-order + new iCIMS line), `docs/07`, CLAUDE Phase-8 line, `data/seed/README.md`
status blocks (also corrected the pre-existing post-D-046 RTX/Workday staleness) updated.

**Tests:** `tests/unit/test_icims.py` (11: fixture mapping, pagination, paginate-or-fail/truncation, transport/
parse/shape/missing-field errors); `tests/live/test_icims_live.py` (opt-in Garmin smoke); `test_registry.py`
(iCIMS now supported; unsupported-case switched to Oracle HCM); `test_employers_import.py` counts (31→37, +6
iCIMS; aviation 7→9).

**Verified:** full Python gate green — ruff format/check, mypy (38 files), lint-imports (1/0), **245 pytest**,
`uv lock`. Live smoke: Garmin returns **303** postings incl. "Software Engineer - Real Time Aviation Data" (US)
— the previously-invisible class of role now flows.

**Plus (same session, config-only Workday onboards from Hayden's probing):** Hayden pulled board URLs for the
dark tail. **Sabre** (`sabre:wd1:SabreJobs`, 150) and **Amadeus** (`amadeus:wd502:jobs`, 135) live-verified and
onboarded to the existing Workday fetcher (zero code) → aviation **9→11**, total **37→39** (Workday 18→20).
**Delta/Avature** investigated and left at Layer 2: `delta.avature.net` serves per-job schema.org JSON-LD but
returns a **202 bot-challenge** (empty body) server-side, so no clean list API. Counts/README/D-048 updated.

**Next:** **STOP for Hayden to commit + PR** (Block 1). Then the rest of Tier-B (Workable/SmartRecruiters/Oracle),
then the Layer-2 tail. No paid extract/match run yet — Hayden authorizes after reviewing fetch counts.

**Branch:** `feat/icims-fetcher` (off `main` @ merged PR #34).

---

## 2026-06-22 — Phase 7 · Blocks 3+4: aviation config + full end-to-end run (D-046) — architecture test PASSED

**Did:** Wrote the aviation vertical config and ran the **whole pipeline end-to-end** on it. **Headline: adding the
aviation vertical forced ZERO `src/` changes** — the D-004 architecture test passes. (Blocks 3+4 combined into one PR
per Hayden.)
- **Block 3 — config:** `config/verticals/aviation_software.yaml` (aviation `domain_vocabulary` + Stage-A `scope`
  with aviation-specific excludes [pilot, flight attendant, ramp, …] + Stage-B `prefilter` US/early-career).
  Auto-discovered by `available_verticals()`'s glob; loaded by the same `load_vertical_config`. Added
  `test_loads_real_aviation_config`.
- **Block 4 — end-to-end run** (local `data/vja.db`, gitignored; backup `data/vja.db.pre-aviation.bak`):
  - `vja-import-employers` → 36 aviation inserted, 54 grid updated, **ats-unresolved=0** (every ATS value a valid
    enum). `vja-load-profiles` → aviation profile active; **grid bumped to a new `resume_version`** (the re-tilt).
  - `vja-run --vertical aviation_software` → **3612 postings / 7 employers** (Airbus 2000, Boeing 1169, Shield AI
    391, Wisk 24, Beacon AI 17, OAG 10, FLYR 1). Stage-A in-scope **874 (24%)**.
  - `vja-extract` → **871/874** extracted (3 isolated failures), **$3.68** (Haiku). Stage-B persisted `in_scope`
    cut 874 → **110** (Airbus's mostly-EU + Boeing's senior roles correctly dropped on US/level).
  - `vja-match --vertical aviation_software` → **110/110**, **$1.71** (Sonnet). Verdicts: **1 yes · 16 maybe ·
    93 no**. The 17 relevant are **all US** entry-level/associate SWE roles (geo filter clean — no foreign leak);
    the 85% `no` rate is the willingness-to-say-no (D-007) working for a junior CS candidate vs whole-company
    aerospace boards.
  - **Grid re-match** (résumé changed → stale matches): `vja-match --vertical grid_power_software` → **41/41**,
    **$0.68**, 17 relevant. `/api/verticals` now returns **both** verticals (dashboard picker surfaces aviation).
  - **Total LLM spend: ~$6.07.**

**Finding (logged, not a defect):** the run **stress-tested the Workday fetcher** — Collins/RTX's whole-conglomerate
`cxs` board (4160) exceeds Workday's **~4000 offset cap**, so the paginate-or-fail guard (D-032) correctly refused
the truncated page rather than reading 160 roles as closures. Per the **Castleton precedent (D-032)**, RTX was
**reclassified to Layer 2 in config** (seed edit, no code) — so aviation fetchable is **7, not 8** (3 Workday). This
is the first Workday tenant big enough to hit the cap (grid's max was GE Vernova ~2376). Candidate future fetcher
improvement: offset-cap-aware Workday pagination. Probing also caught a Greenhouse **name collision** (`archer` = a
veterinary clinic, not Archer Aviation → Layer 2).

**Decisions:** **D-046** (Phase 7 aviation shipped config-only; the architecture test + the RTX finding). Also this
session, **D-047** — roadmap resequence: **P8 remaining coverage → P9 cloud migration + full product frontend
(promoted from the floating D-025 cutover, widened to auth/upload/vertical-toggle) → P10 discovery agent (demoted)**;
security posture for a free public launch folded in (cost-abuse is the dominant risk; `docs/11` is the P9 checklist).
CLAUDE.md build sequence + INVARIANTS (D-004/D-022/D-032 lines) updated.

**Tests:** `test_loads_real_aviation_config` (config loads via the same path); `test_employers_import` updated for the
RTX reclassification (aviation fetchable 8→7, Workday 4→3; combined 32→31/18). Data/config-count tests, not new src.

**Verified:** full Python gate green — ruff format/check, mypy, lint-imports (1/0), pytest, `uv lock`. **No `src/`
change in the entire phase.** Spot-checks: 17/17 aviation relevant matches US; `/api/verticals` lists both verticals.

**Next:** **STOP for Hayden to commit + PR** (Blocks 3+4). Then **Phase 8** (Tier-B fetchers + Layer-2 tail). The
aviation detected/Layer-2 tail (Delta/Avature, JetBlue/SuccessFactors, Joby/iCIMS, RTX cap, …) lights up there.

**Branch:** `feat/aviation-vertical` (off `main` @ the merged Block-2 PR).

---

## 2026-06-22 — Phase 7 · Block 2: re-tilt both resumes (config/data only)

**Did:** Re-tilted the matching résumés per vertical (the matching-profile half of the D-004 config —
still zero `src/` change).
- **Shared, real-experience edits to both résumés:** added **Optum (UnitedHealth Group) — Technology
  Development Intern** (current, top of Experience) with two bullets on **data ETL pipelines in
  Snowflake** + SQL transformations; **removed the LinkUp** role. Tech Stack updated to reflect the
  now-real tools (FastAPI, pandas, SQL/Snowflake, PostgreSQL, Redis, Google Cloud, TypeScript).
- **`hayden_aviation_resume.md`** (new): replaced the Nomi project with the **Flight Delay Cascade
  Simulator** (FastAPI + pandas / React + Vite; tail-cascade + connection-risk propagation over the U.S.
  DOT BTS dataset); Interests → Aviation & Flight Systems / Real-Time Data Systems. Sudoku Solver kept.
- **`hayden_grid_resume.md`** (edit): replaced Nomi with the **Strait of Hormuz Event Study** (FastAPI +
  React/Vite/TS; layered offline compute → read-only API; price-vs-transit event scatter); Interests →
  Energy Markets & Power Trading / Commodities & Quant.
- Bullets are **faithful to the facts Hayden gave** (project mechanics, Snowflake ETL) — no invented
  metrics. **Placeholders to confirm:** the Optum **location ("Remote") and start month ("June 2026")**.

**Decisions:** none new. Per Hayden: replace Nomi with the two projects, add Optum/Snowflake, drop LinkUp.
Note: re-tilting the grid résumé changes its text → a new `resume_version` on the next `vja-load-profiles`,
so existing grid matches go stale — Hayden chose to **re-match grid** in Block 4.

**Tests:** none added (résumé content isn't asserted anywhere — the config loader only checks the file
resolves). `load_vertical_config('grid_power_software')` still loads the re-tilted résumé; the new
aviation résumé file reads + parses. The aviation config that references it lands in Block 3.

**Verified:** full Python gate green — ruff format/check, **233 pytest**, lint-imports, mypy, lock.
Both résumés load through the config path. **No `src/` change.**

**Next:** Block 3 — `config/verticals/aviation_software.yaml` (matching_profile → aviation résumé +
domain vocabulary, Stage-A scope, Stage-B prefilter) + a `test_vertical_config.py` aviation case.
**STOP here for Hayden to commit + PR.**

**Branch:** `feat/resume-retilt` (off `main` @ the merged Block-1 PR).

---

## 2026-06-22 — Phase 7 · Block 1: aviation employer seed + ATS resolution (config/data only)

**Did:** Curated + ATS-resolved the **aviation vertical** employer universe — the data half of the
D-004 architecture test (config + curation only, zero `src/` change). Hayden had seeded 16 partial rows
(names + category); I completed the columns and broadened to **36 employers** across every aviation
sub-domain (airlines · avionics · OEM/manufacturers · GDS/airline-IT · flight-data/analytics ·
ATM/infrastructure · eVTOL/autonomy · travel-tech SaaS).
- **Resolution = live probing** (same pass as grid, D-015): probed Greenhouse/Lever/Ashby slugs, fetched
  careers pages to fingerprint the ATS, and POSTed candidate Workday `cxs` endpoints. Result:
  **8 verified/fetchable** — GH (OAG `oagaviationworldwide`, FLYR `flyr`), Lever (Shield AI `shieldai`,
  391 open), Ashby (Beacon AI `beaconai`), Workday (Boeing `boeing:wd1`, 1168; Collins/RTX
  `globalhr:wd5`, 4161; Airbus `ag:wd3`, 2000; Wisk `wisk:wd108`, 24) — **6 detected** (iCIMS: Alaska/
  SITA/Joby; Avature: Delta; SuccessFactors: JetBlue; Oracle: Honeywell) — **22 layer2** (Phenom/Radancy
  portals + custom JS-rendered sites).
- **Caught a name collision:** the Greenhouse `archer` board is **Archer Veterinary Clinic**, not Archer
  Aviation — exactly why we probe-and-verify instead of guessing slugs. Archer Aviation → custom/Layer 2.
- Regenerated `data/seed/employers_seed.csv` deterministically (preserved the 54 grid rows byte-for-byte,
  `csv.writer` for the new aviation block). Updated `data/seed/README.md` with the aviation status block.

**Decisions:** none new (executes D-002/D-004/D-015/D-017/D-018; ADR D-046 lands with the Block-4 result).
Mega whole-company Workday boards (RTX/Airbus/Boeing, ~7300 mostly non-US/senior postings) kept verified —
the Stage-A scope gate + Stage-B US/level pre-filter cut them to the early-career US slice, same as grid's
GE Vernova. **Heads-up for Block 4:** that ~7300-posting first fetch + its Stage-A extraction backlog will
likely run a few dollars more than the "couple dollars" estimate — I'll surface concrete counts after
`vja-run` and confirm before the paid extract/match.

**Tests:** updated `test_employers_import.py` — totals auto-adapt; bumped the fetchable assertion (24→32,
Workday 15→19) and added `test_aviation_vertical_is_fetchable_without_code_change` (aviation resolves to
8 fetchable via the same code path, no per-vertical branch). These pin data counts, not new src behavior.

**Verified:** full Python gate green — ruff format/check, mypy (37 files), lint-imports (1 kept/0 broken),
**233 pytest** (+1), `uv lock --check`. **No `src/` change** (the architecture test holds so far).

**Next:** Block 2 — re-tilt both resumes (aviation: skills/interests + flight-delay project; grid:
Strait-of-Hormuz project + energy skills/interests). **STOP here for Hayden to commit + PR.**

**Branch:** `feat/aviation-seed` (off `main` @ PR #31).

---

## 2026-06-22 — Corpus location repair + stale-match cleanup (D-043 · WS5) · Branch B

**Did:** Built + ran the one-time repair that fixes the corpus Branch A's clobber already damaged.
- **`src/vja/repair.py`** (`vja-repair` CLI, new top-layer module): per vertical, re-derives `location`
  from each posting's `raw_payload` (GH `location.name` / Lever `categories.location` / Ashby
  `location` / Workday `locationsText`), writes it L1-authoritatively (a null snapshot never nulls a
  model fill), recomputes + persists `in_scope` from `passes_prefilter` on the effective location, then
  deletes matches whose posting now fails Stage B. Idempotent, offline (no LLM). Repo helpers:
  `postings_for_repair` + `apply_location_repair` (`db/postings.py`), `delete_matches_failing_scope`
  (`db/matches.py`). `repair` added to the import-linter top layer.
- **Ran it on `data/vja.db`** (backup at `data/vja.db.pre-repair.bak`): postings=2335,
  **locations_repaired=349**, in_scope **42 true / 444 false**, **matches_deleted=48**. Blank-location
  rate on extracted-open rows went **84/266 + 48/191 + 4/22 → 0/0/0**.
- **Verified (sqlite spot-checks):** the 3 named foreign roles (Mumbai/Bangalore/Mexico City) are
  `in_scope=0` with no match; **0** matched postings have `in_scope≠1`; every matched yes/maybe role is
  now US. The 444 in_scope=False split: 312 senior/mid level + 132 genuinely foreign (Hong Kong, London
  UK, Pune, Singapore…).

**Also (D-045, found during live dashboard testing):** "rejected never shown" made *Cleaned* collapse
onto *Matched* once the corpus is fully assessed (both = 8). Redefined **Cleaned = the whole in-scope
set, every verdict incl. `no`** (the objective US-software job list, profile-independent); *Matched*
unchanged (this résumé's relevant verdicts). `open_postings_with_match_quality` drops the always-hide-`no`
clause; the `cleaned` branch now applies no verdict filter. Live: matched=8, **cleaned=41** (8 maybe + 33
no). Ran `vja-match` (1 straggler, $0.0136). `no` stays hidden from *Matched* + the digest (D-037).

**Decisions:** D-045 (Cleaned = whole in-scope set incl. rejected; amends D-043). The repair itself
executes D-043. Tests: `test_repair.py` + updated `test_dashboard_query.py`/`test_api.py` (cleaned shows
rejected; matched hides it).

**Verified:** full Python gate green — ruff, mypy (88 files), lint-imports (1/0), **232 pytest**, lock.
Frontend 14 vitest green (cleaned now renders `no` rows with their badge — kept, removable later).
**Heads-up:** a stale `vja-api` (started before these changes) serves the old API — **restart it**.

**Known residuals (coarse-gate, undecidable from a bare token):** (A) foreign cities whose 2-letter
code = a US state code pass in_scope but Sonnet rejects — `Bogota, CO`, `Buenos Aires, AR` (×2); (B)
bare US city w/o state code dropped — `Chicago` (×5). Both small; possible follow-up (city list).

**Branch:** `fix/corpus-location-repair` (off merged `main` @ PR #30). `data/vja.db` mutation is local
(gitignored); the commit is the repair code + tests + this log.

---

## 2026-06-22 — Location-blind pipeline fix + dashboard two-view redesign (D-043, D-044) · Branch A

**Did:** B2 use exposed foreign roles (Mumbai/Bangalore/Mexico City) rated yes/maybe + confusing
"unassessed"/"rejected" toggles. Root cause found: **L2 extraction was overwriting the L1 `location`
with `null`** (`save_extraction` wrote every column unconditionally; Haiku returns null location),
which blinded Stage B (coarse keep-null) *and* Sonnet (`_posting_text` omits a null location). Fixed
the pipeline + redesigned the dashboard. This is **Branch A** (code+tests+docs); the corpus repair +
re-match is Branch B (WS5, not yet done — `data/vja.db` still holds the stale matches).
- **WS1 — location L1-authoritative:** `save_extraction` now fills `location` only when the stored
  value is NULL, never overwrites a non-null L1 value (mirrors the `source_updated_at` guard).
- **WS2 — persisted `in_scope`:** new `postings.in_scope` bool (migration `d30501b4c8ab`), stamped at
  extraction from `passes_prefilter` on the *effective* L1-authoritative location (so a clobbered-null
  model read can't fake a pass). `ExtractionCandidate` now carries `location`; `run_extraction` takes
  `PrefilterConfig` (CLI + nightly callers updated).
- **WS3 — dashboard two-view:** `open_postings_with_match_quality` floors on `in_scope IS TRUE`, always
  hides `no`, and takes a single `cleaned` bool (Matched default / Cleaned). API `view` enum replaces
  `include_unassessed`/`include_rejected`. Frontend: segmented Matched/all-cleaned control (replaces
  the two checkboxes), `api.ts`/`App`/`Controls` + vitest updated.
- **WS4 — prefilter collision:** `_NON_US_COUNTRY_NAMES` override so "Bengaluru, India, IN" /
  "Cordoba, Argentina, AR" fail Stage B despite IN/AR doubling as US state codes; omits country names
  that are US places (New Mexico / Georgia); bare codes w/o a country name ("Munich, DE") stay a
  residual Sonnet backstops.

**Decisions:** D-043 (L1-authoritative location + persisted `in_scope` + dashboard Matched/Cleaned,
supersedes D-041's additive toggles), D-044 (Stage-B non-US country override). Per this session's
sign-off (delete-and-rematch for repair; persist the flag; drop the rejected axis).

**Verified:** full Python gate green — ruff format/check, mypy, lint-imports (1 kept/0 broken), **230
pytest** (+4 new: location-not-clobbered, in_scope-on-effective-location, prefilter override ×2), `uv
lock --check`. Frontend lint/typecheck/**14 vitest**/build green. Migration round-trips on a clean DB;
`alembic check` clean. (Downgrade on the *populated* `data/vja.db` hits a SQLite-batch FK artifact
shared by the existing postings migrations — upgrade is the only gated path.)

**Next:** **Branch B (WS5)** — tested idempotent repair CLI: re-derive `location` from `raw_payload`
per ATS (GH `location.name` / Lever `categories.location` / Ashby `location` / Workday `locationsText`),
recompute `in_scope`, delete matches whose posting now fails Stage B, then `vja-match`. Then the data
spot-checks (no foreign matched rows; the 3 named rows in_scope=false + no match). Open thread
(unchanged): grandfathered `db→fetchers` edge refactor.

**Branch:** `fix/location-pipeline-and-dashboard` (off merged `main` @ PR #29).

---

## 2026-06-21 — Phase 6 · Block B2: React dashboard table over `/api/postings` (D-042)

**Did:** Built the read-only dashboard SPA — the **pull** surface (D-010) — the repo's first frontend. Consumes B1's
`GET /api/postings` verbatim and renders the full D-041 surface against live `data/vja.db` (483 in-scope open / 89
matches).
- `frontend/` (new): Vite + React + TS, no router/state lib. `src/api.ts` (typed client mirroring B1's
  `PostingRow`/`PostingsResponse`; `postingsPath` is the one home for the toggle→param mapping), `theme.css`
  (DESIGN.md tokens as CSS custom properties — dark-only, one accent), `App.tsx` (resolves vertical via
  `/api/verticals`, fetch-on-toggle, loading/error/empty states), `components/{Controls,PostingsTable,Verdict}`.
  Table: company · title→apply · location · activity date · match (verdict badge + mono score, color-coded; dim `—`
  when unassessed). Row expands to fits/gaps/rationale (3px accent spine).
- Backend (`src/vja/api/app.py`): added `CORSMiddleware` (GET-only, `VJA_CORS_ORIGINS`, default `:5173`), `GET
  /api/verticals` (→ new `active_verticals` in `db/profiles.py` so no slug is hardcoded), and an optional
  `frontend/dist` `StaticFiles` mount (prod same-origin; guarded so tests/CI without a build are unaffected).
- Gates (the D-042 precedent): `frontend` CI job (Node 24 → eslint + `tsc --noEmit` + `vitest run`) + a path-filtered
  `frontend-checks` pre-commit hook. `frontend/{node_modules,dist}` gitignored; `package-lock.json` committed.
- Tests: +14 vitest/RTL (`api`, `Controls`, `PostingsTable`, `App`) pinning param mapping, control emission, render
  rules (no fake score for unassessed, rejected dimming, expand reveals detail), refetch-on-toggle. +2 Python
  (`test_api.py`: CORS header, `/api/verticals`).

**Decisions:** D-042 — stack (Vite/React/TS), styling (plain CSS vars per DESIGN.md, no Tailwind), frontend tests =
Vitest+RTL as a path-filtered gate, serving (Vite dev + CORS / prod StaticFiles), `/api/verticals` to avoid a
hardcoded vertical. Bumped Vitest 2→3 (v2 nests Vite 5, clashing with the top-level Vite 6 plugin types). All per
this session's sign-off.

**Verified:** frontend `npm run lint` + `typecheck` + `test` (14) green, `npm run build` clean (148.9 kB JS gzip
47.8). Python `test_api.py` green (11). Full gate run (Python + e2e against live DB) = next task.

**Next:** Phase 7 (aviation vertical — config + curation, any forced code change is a defect). Open thread
(unchanged): grandfathered `db→fetchers` edge refactor.

**Branch:** `feat/dashboard-react-table` (off merged `main`).

---

## 2026-06-21 — Phase 6 · Block B1: dashboard read-only API (D-041)

**Did:** Built the FastAPI read API the React table (B2) will consume. Planning surfaced that the dashboard's
"full open set" (D-030) was underspecified — `postings` holds the *raw* open set incl. out-of-scope roles
(Stage-A scope gate D-034 is on-the-fly, never stored; `extracted_at IS NOT NULL` is the only durable in-scope
marker). Resolved with three tiers and **D-041**.
- `src/vja/db/postings.py`: new `open_postings_with_match_quality(engine, vertical, profile_id, resume_version,
  *, cutoff, by_first_seen, include_unassessed, include_rejected)` + `DashboardPosting`. Floors on Tier 2
  (`extracted_at IS NOT NULL`), LEFT-JOINs `matches` on `(profile_id, resume_version)`. Two axes: match-status
  (matched-only default; `include_unassessed` → null-match rows; `include_rejected` → un-hide `no`) × recency
  (`activity_window_clause` / first_seen / all). **Retired** the A2 `open_postings_in_window`/`OpenPosting`
  (caller-less — backfill uses `postings_needing_match(since=)`).
- `src/vja/api/` (new top layer): `create_app()` + `GET /api/health` and `GET /api/postings`
  (`vertical`/`window`/`profile_id`/`include_unassessed`/`include_rejected`), Pydantic `PostingRow`/envelope,
  `_resolve_profile` thin default (404 none/unknown, 409 ambiguous). `vja-api` CLI (uvicorn, localhost).
- `models.RELEVANT_VERDICTS` lifted out of `digest/assembly.py` → one home for the digest + dashboard.
- import-linter: `api` added to the top layer (`nightly | api`).
- Tests: `test_dashboard_query.py` (DB-level: tiers, both axes, recency — folds in the retired A2 window tests)
  + `test_api.py` (HTTP: param mapping, profile resolution, health). Deleted `test_postings_window.py`.
- Docs: D-041; INVARIANTS dashboard section; fixed stale docs/11 §3.3 backfill cap (14d→5d) + marked §2 seam
  adopted.

**Decisions:** D-041 (per Hayden). Dashboard = in-scope (T2) universe, matched-default (T3); `no` hidden by
default (mirrors digest D-037); LEFT-JOIN over reuse+merge. Key clarification: the 5-day cap (D-039) is a
*matching/backfill* cost lever — the dashboard is read-only and never matches (D-005), so its window is free and
decoupled from the cap.

**Verified:** new tests pass (18); full gate run next.

**Next:** Phase 6 · B2 (React table over `/api/postings`) — `DESIGN.md` ("terminal dev-tool, dark") is the UI
spec; wire CORS for the dev server there. Open thread (unchanged): grandfathered `db→fetchers` edge refactor.

**Branch:** `feat/dashboard-read-api` (off merged `main`).

---

## 2026-06-21 — Comprehension-debt guards: enforced import layering + INVARIANTS registry (D-040)

**Did:** Interlude before Phase 6 · B1, prompted by Hayden feeling he and Claude were losing the thread.
Diagnosis from a real survey: the *code* is healthy (~4.1k LOC, max file 377, clean layered DAG, ~1:1 tests) —
what grows unbounded is the *context to change it safely* (39 ADRs, 840-line WORKLOG). Built two cheap guards:
- **#1 Import contract (`import-linter`).** Encoded the real dependency stack as a layered contract in
  `pyproject.toml` (`nightly → pipeline/extract/match/digest → fetchers/verticals → db → helpers → models`);
  wired `uv run lint-imports` into pre-commit + CI after mypy. Verified it has teeth (breaks on a synthetic
  removal of the exception). Setup surfaced a back-edge nobody knew about: `db.employers → fetchers.registry`
  (`SUPPORTED_ATS_TYPES`) — grandfathered as one documented `ignore_imports` line; new `db→fetchers` edges fail.
- **#2 `docs/INVARIANTS.md`.** Derived "what's true now" registry, mined from D-001…D-039, each rule → its ADR.
  Caught the live example: backfill cap is **5 days** (D-039), not D-024's original 2 weeks. Linked read-first
  from `CLAUDE.md` doc map; added a discipline rule (ADR that changes a live rule must update INVARIANTS same session).

**Why:** convert "good architecture by luck/discipline" into machine-guaranteed structure, and give both Hayden
and each fresh agent session a single current-truth doc instead of replaying 39 ADRs. See D-040.

**Verified:** full gate suite green — ruff format/check, mypy, `lint-imports` (1 kept / 0 broken, 86 deps),
211 tests, `uv lock --check` clean.

**Next:** Phase 6 · B1 (FastAPI read API: recency toggles→cutoffs + LEFT-join match quality on the
`(vertical, profile_id)` seam). Open thread: optionally refactor the grandfathered `db→fetchers` edge (inject
supported set from orchestration layer) — deferred to keep this chunk tight.

**Branch:** `chore/import-contract-and-invariants` (off the merged A2 state).

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
