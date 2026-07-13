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

## PR 1 — Landing page (Linear-style marketing)

- [ ] `Landing.tsx` → full page: viewport **hero** (sharp claim + subline + Google CTA +
  product visual) · **how-it-works** 3-step (bounded employer universe → nightly diff →
  written match verdict that will say *no*) · **verticals** section (grid/power + aviation) ·
  honest **footer**.
- [ ] Product visual = a **CSS-built dashboard mock** (mini table on real v2 tokens), not a
  binary screenshot — stays current with the design system, no asset pipeline.
- Static, no new endpoints; stays the logged-out branch of the D-065 smart root.
- **DoD:** gates green · screenshots · route guards untouched (`App.test.tsx` green).

## PR 2 — Login + onboarding polish

- [ ] `Login.tsx` → proper auth card: brand, 2–3 benefit lines, Google button. **Fix stale
  copy:** it claims you can browse without signing in — false since `VJA_AUTH_REQUIRED` went
  ON at go-live (D-067).
- [ ] `Upload.tsx` onboarding mode → vertical choice as **descriptive cards** (not a bare
  `<select>`) + drag-and-drop file zone (type hints, selected-file state) + clearer
  submit/error states (typed `ApiError` messages styled, incl. the 409 second-vertical).
- [ ] `/upload` update mode gets the same treatment with the vertical locked (D-064).
  Two-mode logic + guards unchanged.
- **DoD:** gates green · screenshots · Login/Upload test suites updated for the new
  interactions.

## PR 3 — Dashboard rework

- [ ] **Row redesign:** verdict + score + a truncated one-line rationale snippet visible **in
  the row** (today all match info is behind a click); title prominent; verdict-colored spine.
- [ ] **Side-panel detail** (Linear-style): row click opens a right-hand panel — full
  rationale, fits/gaps, location/date meta, apply CTA; Esc/click-away closes. Replaces the
  inline row expansion.
- [ ] **Sortable columns:** company / title / location / activity date / match score with
  direction toggle, client-side; default stays freshness-desc (today's server order).
- [ ] **Text search/filter:** filter-as-you-type over company/title/location, client-side.
- [ ] Controls/subbar restyle on v2 tokens; redesigned loading/empty/error states.
- Untouched behavior: window/view → API param mapping (`postingsPath`), the D-057 backfill
  poll, D-064/D-065 routing.
- **DoD:** gates green · vitest covers sorting, filtering, panel open/close, row-snippet
  rendering · screenshots.

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
