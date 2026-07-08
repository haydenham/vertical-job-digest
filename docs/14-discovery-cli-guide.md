# Discovery CLI guide — `vja-discover` + `vja-review`

The Layer-3 discovery workflow (Phase 10, D-070/D-071): an agent finds new **employers**, writes
them as `proposed` rows, and a human promotes the good ones with a review CLI. This is the operator
reference for running it.

- `vja-discover` — Opus 4.8 + web search researches new employers → writes `proposed` rows.
- `vja-review` — the human gate: `list` / `approve` / `reject` those proposals.

Related: `deploy/launchd/README.md` (§ "Discovery (disabled by default)" + "Running against prod"),
`deploy/gcp/CUTOVER.md` §8b (cloud schedule, not yet enabled), and D-070/D-071 in `DECISIONS.md`.

---

## First, the two things that bite people

### 1. Which database am I writing to?
Both commands read/write whatever `VJA_DATABASE_URL` points at:

- **unset** → `sqlite:///data/vja.db`, a local file on your Mac (a safe sandbox).
- **set to the Neon URL** (as it is in the committed workflow / a deployed `.env`) → **production
  Postgres**, the same DB the live app reads and the nightly Cloud Run Job writes.

Check before running writes — reads are harmless, writes are real:
```sh
grep VJA_DATABASE_URL .env      # is it pointing at neon.tech (prod) or unset (local)?
uv run vja-review list          # if it shows the prod proposals, you're on prod
```
To force a local sandbox even when `.env` points at Neon, prefix the command (a shell env var wins
over `.env`, which loads with `override=False`):
```sh
VJA_DATABASE_URL="sqlite:///data/vja.db" uv run vja-discover --vertical grid_power_software --dry-run
```

**Why writing to prod is still low-risk:** proposals land as `status=proposed` and are **inert** —
nothing is fetched or shown to users until *you* `approve` one to `active`. So the agent can't put a
bad company in front of anyone by itself.

### 2. What does a run cost?
Each `vja-discover` run makes real Opus + web-search calls — **expect a few dollars**. Notes:
- `--dry-run` costs the **same** (it skips DB writes, not the LLM research loop).
- `--limit N` caps how many candidates are *persisted*, not the research cost.
- The run prints `est_cost=$…` and a token breakdown at the end — that's the real metered number
  (Opus rates), and it's what gates whether the weekly schedule is worth enabling (D-071).

---

## Commands

### `vja-discover` — find employers → write proposals
```sh
uv run vja-discover --vertical <key> [--limit N] [--dry-run]
```
| flag | meaning |
|------|---------|
| `--vertical` (required) | `grid_power_software` or `aviation_software` |
| `--limit N` | cap how many candidates are persisted (research cost is unchanged) |
| `--dry-run` | run + print + meter, but **write nothing** |

Each candidate is validated by actually fetching it: a supported ATS that returns postings →
`proposed` + `detected` (fetchable); anything unresolved → `proposed` + `unknown`/`layer2` (the guess
is kept in the row's `notes` for manual triage). Duplicates of the existing universe are skipped.

### `vja-review` — approve / reject / list proposals
```sh
uv run vja-review list [--vertical <key>] [--status proposed|approved|active|retired]
uv run vja-review approve <id> [<id> ...]
uv run vja-review reject  <id> [<id> ...]
```
| command | effect |
|---------|--------|
| `list` | default `--status proposed`; `--status approved` = the **parked** queue |
| `approve <ids>` | → `active` if the ATS is a supported Layer-1 fetcher (fetched next nightly); else → `approved` + **parked** with a printed notice |
| `reject <ids>` | → `retired` (never deleted) |

`approve`/`reject` are batch-friendly and exit non-zero if any id fails (not found, or not in a
promotable state).

**Parked (`approved`) employers** are real companies with no Layer-1 fetcher yet. They are
*structurally* excluded from the nightly fetch, so they sit harmlessly until you resolve their ATS.
To activate one later, fix its `ats_type`/`ats_slug` (curation — e.g. via the seed CSV or SQL) so it
becomes fetchable, then it can go `active`. `vja-review list --status approved` is how you find them.

---

## Recommended first-run walkthrough

**1. Dry-run — safe, writes nothing, prints cost + candidates:**
```sh
uv run vja-discover --vertical grid_power_software --limit 5 --dry-run
```
Reads your real universe (won't re-propose companies you already have). **Judge two things:** are the
companies good, and is `est_cost` acceptable?

**2. If proposals + cost look right, persist them** (drop `--dry-run`):
```sh
uv run vja-discover --vertical grid_power_software
```

**3. Review what it found:**
```sh
uv run vja-review list
```

**4. Approve the good ones / reject the rest:**
```sh
uv run vja-review approve 57 58 61
uv run vja-review reject  59 60
```

**5. Confirm the resulting state:**
```sh
uv run vja-review list --status active     # what you just activated
uv run vja-review list --status approved   # parked: real, but no fetcher yet
```

**What happens next:** employers you set to `active` are fetched by the **next nightly run** (the
Cloud Run Job, same Neon DB) — their postings + match rationale flow into the app. No merge or deploy
is needed; the data reached prod through the database, not through code.

---

## Prerequisites
- `ANTHROPIC_API_KEY` in `.env` (the agent's web search + reasoning; auto-loaded).
- The target database migrated (`alembic upgrade head`). Prod/Neon already is; a fresh local sqlite
  needs it before the first run.
- Verticals available: `grid_power_software`, `aviation_software` (`config/verticals/*.yaml`).

## Not yet enabled
The **weekly schedule** is ready-but-off (D-071): run `vja-discover` by hand until its live per-run
cost is known. The disabled launchd template (`deploy/launchd/com.vja.discover.plist.template`) and
Cloud Scheduler runbook (`deploy/gcp/CUTOVER.md` §8b) are the paths to turn it on later.
