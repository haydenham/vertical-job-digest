# Discovery CLI guide — `vja-discover` + `vja-review`

The Layer-3 discovery workflow (Phase 10, D-070/D-071): an agent finds new **employers**, writes
them as `proposed` rows, and a human promotes the good ones with a review CLI. This is the operator
reference for running it.

- `vja-discover` — GPT-5.6 Terra + web search researches new employers, resolves ATS evidence,
  then writes `proposed` rows.
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
Each `vja-discover` run makes real **GPT-5.6 Terra** Responses API + hosted-web-search calls. A run
uses an inclusive **`VJA_DISCOVER_MAX_USD` ceiling (default $4)**: after a completed response crosses
the estimate, no new research wave or ATS resolver starts. One bounded tool-free structuring call is
still allowed so paid research is not lost. The request that crosses can overshoot; its own tool/output
caps bound that overshoot. The protocol is fixed and inspectable:

- Three sequential discovery waves — capital portfolios, industry lists, and market adjacency —
  each receive at most **5** web actions.
- At most **5** candidates proceed by default. Each unresolved candidate receives a separate ATS
  resolver with at most **4** actions, low reasoning, 2k output tokens, and a 120-second timeout.
- Supported ATS status requires canonical provider-URL evidence *and* a registry fetch returning at
  least one posting. Everything else remains `unknown`/`layer2` for review.

Notes:
- `--dry-run` costs the **same** (it skips DB writes, not the LLM research loop).
- `--limit N` caps how many candidates are ATS-resolved and persisted; the three sourcing waves still run.
- The run prints `est_cost=$…`, tokens, all web actions, and billable searches. The estimate includes
  exact Sol/Terra/Luna token/cache rates plus **$0.01 per search action**.
- Tunable via env: `VJA_DISCOVER_MODEL` (only `gpt-5.6-sol|terra|luna`; default Terra),
  `VJA_DISCOVER_MAX_USD` (4), `VJA_DISCOVER_MAX_CANDIDATES` (5), and `VJA_DISCOVER_EFFORT`.
  One rolling report under `data/discovery_reports/` (or `VJA_DISCOVER_REPORT_DIR`) is updated after
  each wave and resolver, including partial failures and ATS evidence.

---

## Commands

### `vja-discover` — find employers → write proposals
```sh
uv run vja-discover --vertical <key> [--limit N] [--dry-run]
```
| flag | meaning |
|------|---------|
| `--vertical` (required) | `grid_power_software` or `aviation_software` |
| `--limit N` | cap how many candidates are ATS-resolved and persisted (waves still run) |
| `--dry-run` | run + print + meter, but **write nothing** |

Each candidate is validated by actually fetching it: a supported ATS that returns postings →
`proposed` + `detected` (fetchable); anything unresolved → `proposed` + `unknown`/`layer2` (the guess
is kept in the row's `notes` for manual triage). Duplicates of the existing universe are skipped.

The research and ATS phases log wave/resolver bookends plus the running cost after each completed
request. They intentionally use complete Responses calls rather than the SDK's high-level stream
accumulator: a live run exposed an upstream output-index crash there (D-075), and exact post-response
metering is more important than per-search progress lines. A failed wave is retried by the SDK twice,
checkpointed, and the independent remaining work continues.

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
- `OPENAI_API_KEY` in `.env` (the discovery agent only; auto-loaded). Anthropic remains the provider
  for extraction/matching elsewhere in the pipeline.
- The target database migrated (`alembic upgrade head`). Prod/Neon already is; a fresh local sqlite
  needs it before the first run.
- Verticals available: `grid_power_software`, `aviation_software` (`config/verticals/*.yaml`).

## Not yet enabled
The **weekly schedule** is ready-but-off (D-071): run `vja-discover` by hand until its live per-run
cost is known. The disabled launchd template (`deploy/launchd/com.vja.discover.plist.template`) and
Cloud Scheduler runbook (`deploy/gcp/CUTOVER.md` §8b) are the paths to turn it on later.
