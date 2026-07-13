# UI rework — plan of record (beta-hardening Day 1, expanded to a 4-PR block)

*Working execution plan for the docs/15 Day-1 "UI rework" item, scoped by **D-080**. Read
`docs/INVARIANTS.md` → `WORKLOG.md` top → this file to continue the rework after a chat reset.
Memo-tier plan (authority order unchanged): when a PR lands, its decisions go to `DECISIONS.md`,
live rules to `docs/INVARIANTS.md`, and this file's checkboxes get ticked.*

## What this is

The deployed Rolefeed SPA works but doesn't sell: a 20-line placeholder landing, bare
login/onboarding panels, and a functional-but-spartan dashboard. Before broader beta invites,
the surface gets reworked **modeled on a proven leader — Linear** (copy what works rather than
invent). Scope decisions were run through Hayden 2026-07-12 (D-080).

**Decisions locked (Hayden):**

- **Reference = Linear** — dark, dense, dev-native marketing + app UX.
- **Design language v2: everything on the table** — the accent (`#f6821f` orange), the fonts
  (Space Grotesk / JetBrains Mono), and the terminal motifs (`$` prompt, blinking ▮,
  `//comments`) are all up for revision toward **softer, more premium dark**. Claude drafts;
  Hayden signs off accent + font from screenshots before they land.
- **Landing = full marketing page** (hero + how-it-works + verticals + footer), static only.
- **Dashboard rework**: sortable columns · text search/filter · Linear-style side-panel detail ·
  match info surfaced **at row level** (verdict/score + rationale snippet visible without a
  click; the click opens fits/gaps). Keyboard nav: explicitly out.
- **4 PRs, strict merge order**: foundation → landing → auth pages → dashboard.

**Constraints that hold throughout:**

- **No backend/API contract changes** — the `/api/me`, `/api/postings`, `POST /api/profiles`
  shapes stay put. Enabling fact (verified): `GET /api/postings` returns the **full** filtered
  set, server-sorted by freshness, no pagination (`src/vja/db/postings.py:470`) — all new
  sorting/filtering is client-side.
- Rolefeed brand stays; D-065 route guards + D-064 one-vertical stay (no cross-user picker).
- Frontend gate (eslint + `tsc --noEmit` + vitest, D-042) green per PR; before/after
  screenshots in each PR body; branch-only — Hayden commits/PRs (repo DoD, D-021).
- `main` auto-deploys (D-068): each merge ships alone, so tokens land wholesale in PR 0 and the
  site upgrades progressively but coherently.

---

## PR 0 — Design-language foundation ✅ (built 2026-07-12; D-081)

- [x] **Accent + font sign-off:** three candidates (A Indigo·Inter / B Amber·Geist /
  C Violet·Space Grotesk) rendered on the live dashboard with real data and screenshot-compared
  against baseline — **Hayden picked A: indigo `#6e79d6` · Inter**, JetBrains Mono retained for
  data (D-081).
- [x] **`DESIGN.md` rewritten** → v2 "premium dark product": blue-tinted near-black ground,
  muted indigo accent, Inter UI + mono-for-true-data-only, soft `--shadow-raised` on raised
  containers, radius 10/6; the retired terminal motifs moved to the don'ts. The landing-hero
  glow allowance and marketing type scale carry forward to PR 1.
- [x] **`frontend/src/theme.css` reworked** to the v2 tokens + type roles; shell restyled
  (`App.tsx`: indigo mark + "Rolefeed" wordmark replaces `$`+▮; sentence-case nav) and motifs
  retired in `Dashboard.tsx`/`Upload.tsx` (`//` prefixes dropped, `~/vertical` → tint chip,
  footer's decorative `↵ open` hint → honest "Click a row to expand"). Every page renders
  coherently on v2.
- **DoD met:** eslint + tsc + vitest green (45/45) · candidate + after screenshots on the
  comparison artifact · DESIGN.md v2 in the diff.

## PR 1 — Landing page (Linear-style marketing) ✅ (built 2026-07-13)

*Copy decisions locked by Hayden 2026-07-13 from his business thesis (recorded here + WORKLOG,
no new ADR — D-080 governs the block): hero = **coverage-led** ("The engineering jobs the big
boards miss."); sections expanded beyond the original four to also include a **stats band**,
**three-pillar value props** (the thesis talking points), and a **founder story**; brand stays
**"Rolefeed"** (D-058), not the thesis's "RoleFeed"; the verticals section **lists robotics as
served alongside aerospace + energy** — Hayden is adding the robotics vertical before the beta
drops. ⚠️ Until that vertical's config lands, the deployed landing advertises a vertical the
onboarding picker doesn't offer (`main` auto-deploys, D-068) — Hayden owns merge timing.*

- [x] `Landing.tsx` → full page: viewport **hero** (coverage-led claim + subline + Google CTA +
  product visual + the one DESIGN.md-allowed glow) · **stats band** (100+ employers · 3
  verticals · nightly link verification · the LinkedIn first-day stat) · **three pillars** ·
  **how-it-works** 3-step (bounded universe → nightly diff → verdict that will say *no*) ·
  **verticals** (aerospace + energy + robotics) · **founder story** · honest **footer**
  (no-auto-apply line).
- [x] Product visual = a **CSS-built dashboard mock** (mini table on real v2 tokens mirroring
  `PostingsTable` markup — verdict chips + mono scores), no binary asset.
- Static, no new endpoints; stays the logged-out branch of the D-065 smart root (rendered
  inside the App shell — header/nav above, Linear-like).
- **DoD met:** eslint + tsc + vitest green (50/50, incl. the new `Landing.test.tsx` pinning the
  section skeleton + CTA) · before/after screenshots (1440 + 720 sanity, no horizontal
  overflow) · route guards untouched (`App.test.tsx` green, `App.tsx` not in the diff).

## PR 2 — Login + onboarding polish ✅ (built 2026-07-13)

*Decisions locked by Hayden 2026-07-13 (recorded here + WORKLOG, no new ADR — D-080 governs):
**centered** auth-card layout for /login, /onboarding, /upload · login card = mark + heading +
**3 benefit lines** + Google button · vertical display copy = a **frontend slug→{name, blurb}
map** (`frontend/src/verticalCopy.ts`; `/api/verticals` returns slugs only and the API is frozen
this block) reusing the landing's vertical copy, with a prettified-slug fallback so an unknown
vertical still renders · **robotics pre-added** under slug `robotics_software` (Hayden's naming).*

- [x] `Login.tsx` → proper auth card: brand, 3 benefit lines, Google button. **Stale copy
  fixed:** the browse-without-signing-in claim (false since `VJA_AUTH_REQUIRED` went ON at
  go-live, D-067) is deleted and pinned gone by a test.
- [x] `Upload.tsx` onboarding mode → vertical choice as **descriptive cards** (visually-hidden
  native radios, accessible) + drag-and-drop file zone (native DnD, no new deps; type hints,
  selected-file state) + clearer submit/error states (typed `ApiError` statuses get a friendly
  lead before the server detail — 409 second-vertical, 413, 422, 429).
- [x] `/upload` update mode gets the same treatment with the vertical locked (D-064), shown as
  a static card (display name + mono slug). Two-mode logic + guards unchanged.
- **DoD met:** eslint + tsc + vitest green (57/57) · before/after screenshots (1440 + 720, no
  horizontal overflow; interactive states — file-selected, 409 — driven in a real headless
  Chrome against the live API) · Login/Upload suites updated + new `verticalCopy` unit test.

## PR 3 — Dashboard rework ✅ (built 2026-07-13)

*Layout decisions locked by Hayden 2026-07-13 (recorded here + WORKLOG, no new ADR — D-080
governs): rationale snippet = **two-line row** (columns on line 1, truncated muted snippet under
the title — not a sixth column) · detail = **overlay panel** (Linear peek floating over the
right of the table; table never reflows — not a docked split).*

- [x] **Row redesign:** verdict + score + a truncated one-line rationale snippet visible **in
  the row**; title prominent; verdict-colored spine (`.row.v-{verdict}`: strong_yes/yes green,
  maybe indigo-tint, no dim; unassessed transparent).
- [x] **Side-panel detail** (Linear-style): row click opens `PostingPanel` (`role="dialog"`) —
  title/company head, meta card (match/location/activity), full rationale, fits/gaps, apply
  CTA, ✕; Esc/click-away closes; clicking another row switches the panel in place. Replaces the
  inline row expansion (`DetailPanel` deleted). Selection keys on `posting_id`, so a poll or
  toggle that drops the posting closes the panel naturally.
- [x] **Sortable columns:** company / title / location / activity / match score; first click =
  the column's natural direction (text asc, date/score desc), second flips; nulls sink last in
  both directions; default stays freshness-desc (= the server order). Pure helpers in
  `postingsView.ts` (`sortPostings`/`filterPostings`), unit-tested.
- [x] **Text search/filter:** filter-as-you-type over company/title/location in the subbar;
  count meta shows `X of N` while filtering; filter-empty state names the query.
- [x] Controls/subbar restyle on v2 tokens (search input); notices get card treatment; footer
  copy → "Click a row for details". Bonus (within table CSS, not a mobile pass): narrow
  viewports now scroll the table horizontally (`minmax(280px,1fr)` title + `overflow-x: auto`)
  instead of crushing the title column — the pre-existing 720px overlap is gone.
- Untouched behavior held: window/view → API param mapping (`postingsPath`), the D-057 backfill
  poll, D-064/D-065 routing — all pinned by the unmodified existing tests.
- **DoD met:** gates green (eslint + tsc + vitest **73/73**; was 57 — new `postingsView`,
  `PostingPanel` suites + reworked table/dashboard coverage) · before/after screenshots at
  1440 + 720 (panel open, filter active, sorted, cleaned view; landing shared-class regression
  checked; no horizontal page overflow, no new console errors).

---

## Verification (every build PR)

`npm run lint && npm run typecheck && npm run test` in `frontend/`; backend suite untouched
(no contract change); visual check via the Vite dev server against the local DB; before/after
screenshots in the PR body.

## Out of scope (parked, tracked)

- **Mobile pass** — explicitly deferred (Hayden, D-080); beta users open digest links on
  phones, so it's a strong candidate for a later block.
- **Keyboard navigation** (↑↓/↵/o) — offered, not selected.
- Any backend-assisted sorting/pagination — revisit only if the in-scope open set outgrows
  client-side handling.
- Dashboard windows/views semantics (D-045) — presentation changes only.
