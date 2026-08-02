# The funnel block — vertical switching, then a login-free demo board

*Plan of record for the two-PR block decided with Hayden 2026-07-31. Memo-tier (authority order
unchanged): live rules go to `docs/INVARIANTS.md`, decisions to `DECISIONS.md`, and this file's
status lines get updated as each PR lands.*

## Why this block exists

The funnel, not the pipeline, is the constraint. The LinkedIn launch measured **5,000 views → 150
reactions → 15 signups → 10 résumé uploads**: Google login plus a résumé upload sits in front of
everything, so ~99.9% of interest never sees a single job. The product's whole claim is a curated,
total-coverage universe per vertical, and nobody can see it without committing first.

## Why switching comes first

The demo wants a vertical toggle — someone arriving from a robotics post should not land on grid
roles. But D-064 made a user's vertical immutable after signup, so a demo that lets a visitor browse
all four and then hands them an irreversible one-time choice teaches the opposite of what the product
does. **Hayden's rule: if we don't allow it at signup, we can't allow it in the demo.** Switching is
therefore not a demo feature; it is the demo's prerequisite. It also retires a standing promise to do
manual support work, which is reason enough on its own.

## PR 1 — self-serve vertical switching · ✅ BUILT 2026-07-31 (D-104)

`PATCH /api/me {vertical}` → `db.profiles.switch_vertical`, a Settings control behind a confirm
dialog, and `users.last_vertical_switch_at` (one additive migration). Full reasoning in **D-104**;
the live rules are in `docs/INVARIANTS.md` (Auth & identity). What is worth carrying forward:

- **Most of it was already supported.** `profiles` was keyed `(user_email, vertical,
  resume_version)` with an `active` flag; `last_sent_at` keys on `(vertical, recipient)` so the
  digest needed **zero** work; `resume_text` already lives on the profile row so a switch is never a
  re-upload. One line forbade the whole feature.
- **The correctness trap:** `_upsert_profile` deactivates only the *target* vertical's other
  versions, so a switch must explicitly deactivate the old vertical or the user goes active in two
  and the nightly bills them in both. Pinned by `test_switch_deactivates_the_old_vertical`.
- **The cost model is structural, not a guard.** Matching is idempotent per `(posting, profile,
  resume_version)` and a revisit reactivates the same profile row, so cost is once per (user,
  vertical, résumé version) — worst case ~400 matches ≈ $4 per résumé version, then exhausted.
- **The clock protects signups, not spend.** A switch spends the global `check_backfill_budget`
  ceiling, which 429s `POST /api/profiles` when exhausted (D-101's failure mode from the other
  side). Hence its own column, and charged **only when the switch creates work**.

**Requires a manual Neon migration before merge** (D-083/D-068): export `VJA_DATABASE_URL`, then
`alembic current` → `alembic upgrade head` → `alembic current`.

## PR 2 — public demo board at `/demo` · NOT STARTED

**Decided:** a new `/demo` route with Landing keeping its job (its secondary CTA changes from the
`#how-it-works` anchor to "Browse live roles"); the detail panel's match slot renders a **locked
CTA**, never a fabricated rationale; the vertical toggle is honest now that PR 1 shipped.

**The hard rule.** Match text is résumé-derived commentary about named beta users, and D-067 flipped
`VJA_AUTH_REQUIRED` on so anonymous `/api/postings` 401s. That must not be weakened. Leaking is
prevented **structurally at two layers**: `open_postings_with_match_quality` gains `profile_id: int |
None` and, when `None`, builds a statement that never references the `matches` table at all; and the
public endpoints use their own `PublicPostingRow` model which does not *declare*
`verdict`/`score`/`fits`/`gaps`/`rationale`. `_resolve_profile` is not touched.

**Endpoints:** `GET /api/public/postings?vertical=&window=` (reusing the `Window` enum and
`_window_cutoff`), `GET /api/public/postings/{id}?vertical=` (the existing `posting_description`,
which needs no profile), and `GET /api/public/verticals` → `[{vertical, count}]` so the toggle can
skip empty verticals. `/api/verticals` stays the onboarding picker's config-driven source and is left
alone — it must list joinable verticals even at zero rows, the opposite of what the toggle needs.

**Caching is the abuse guard.** There is no rate limiting anywhere in the app and the data changes at
most every 4 hours. An in-process TTL cache keyed on `(vertical, window)` keeps repeat hits off Neon;
`Cache-Control: public, max-age=300, s-maxage=900` lets Cloudflare absorb the rest. **Confirm
Cloudflare is proxying (orange-cloud) rather than DNS-only before relying on the `s-maxage` half.**

**Frontend:** `pages/Demo.tsx` on a public route (the first with no `useAuth` guard), reusing
`PostingsTable` / `PostingPanel` / `Controls` / `postingsView` / `verticalCopy`. `Controls` gains a
recency-only mode (the matched/cleaned axis is meaningless without a résumé); the table and panel gain
a `locked` prop. Plus `frontend/public/robots.txt` (allow `/` and `/demo`, disallow `/api/`) — neither
the file nor the directory exists today.

### Measure before building

The in-scope open row count per vertical is **unknown** (no Neon route in the planning session), and
it decides whether the public response ships whole or needs a cap:

```sql
SELECT e.vertical, count(*) FROM postings p JOIN employers e ON e.id = p.employer_id
WHERE p.status = 'open' AND p.in_scope IS TRUE GROUP BY 1 ORDER BY 2 DESC;
```

Under ~1,500 rows a vertical: ship whole. Above: cap at the newest N with an honest "showing the
newest N of M" line.

## Named, not fixed

- **Dead apply links go public.** D-008 verification runs only pre-digest; the dashboard is
  unverified, and `docs/18` records that a permanently-dead board is invisible while its postings stay
  `open` forever. A stranger's first impression is exactly where "one fake posting costs more trust
  than ten real ones earn" bites hardest. Its own session.
- **No analytics.** Nothing will show whether `/demo` converts better than Landing. Cheapest honest
  move is linking `/demo?src=li` from the LinkedIn post and watching signups against the baseline.
