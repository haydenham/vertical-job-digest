# Nightly scheduling (macOS / launchd)

Runs `vja-nightly` (fetch → diff → persist → send, all verticals) once a day at **06:00 local**.
launchd is used over cron because it runs a **missed job when the Mac wakes from sleep** — a laptop
won't reliably be awake at 06:00. The scheduler is just a trigger; all logic is in the `vja-nightly`
command, so a cloud cutover (D-025) swaps this directory for a `deploy/<platform>/` trigger, not code.

## Prerequisites

1. `uv sync` — so `.venv/bin/vja-nightly` exists (the plist calls it by absolute path).
2. A `.env` in the repo root (git-ignored; see `.env.example`) with at least:
   - `RESEND_API_KEY`
   - `VJA_DIGEST_RECIPIENT` (with the sandbox sender, your Resend **account** email)
   The app loads `.env` itself, and the plist sets `WorkingDirectory` to the repo root so it's found —
   launchd does **not** read your shell profile, so `.env` is the single source of runtime config.

## First run: absorb the baseline manually

The first run sends the full open-roles inventory (the baseline; the 2-week freshness filter is
deferred — D-024). Run it by hand once, then install the schedule so the automated cadence starts at
steady state (small daily diffs):

```sh
uv run vja-nightly
```

## Install / verify / uninstall

```sh
bash deploy/launchd/install.sh        # render plist + load it
launchctl list | grep vja             # confirm it's loaded
launchctl start com.vja.nightly       # fire once now (ignores the schedule)
tail -f logs/nightly.out.log logs/nightly.err.log
bash deploy/launchd/uninstall.sh      # unload + remove
```

Re-running `install.sh` is safe — it reloads in place (pick up a new path or template).
To change the run time, edit `com.vja.nightly.plist.template` and re-run `install.sh`.

## How failures surface

A hard failure (whole pipeline failed, or a digest send failed) sends an **alert email** and exits
non-zero; details also go to `logs/nightly.err.log`. Partial fetch failures (some employers down) are
logged and included in any alert body but don't, on their own, trigger an alert (avoids alert fatigue).

## Discovery (disabled by default)

`com.vja.discover.plist.template` schedules the **weekly Layer-3 discovery agent** (`vja-discover`,
Phase 10.2) — it researches new *employers* and writes them as `proposed` rows for you to `vja-review`.
It reads `OPENAI_API_KEY` from the repo's git-ignored `.env`; Anthropic is not used by this command.
It is **ready but OFF**: `install.sh` does **not** load it, and there's no `RunAtLoad`. Discovery stays
a manual command until its live per-run cost is measured (D-071) — run it by hand when you want to
expand coverage:

```sh
uv run vja-discover --vertical grid_power_software --limit 5 --dry-run   # meter cost, write nothing
uv run vja-discover --vertical grid_power_software                        # persist proposals
uv run vja-review list                                                    # review the proposals
```

To turn the weekly cadence on later, render the template per vertical (substitute `__WORKDIR__` +
`__VERTICAL__`, one plist each) into `~/Library/LaunchAgents/` and `launchctl load` it — the same
mechanics as `install.sh`, done deliberately rather than automatically. It runs Mondays 07:00 local;
edit the template's `StartCalendarInterval` to change that. The cloud analogue (a `vja-discover` Cloud
Run Job + weekly Cloud Scheduler trigger) is documented in `deploy/gcp/CUTOVER.md` §8b, also not yet
enabled.

### Running `vja-discover` / `vja-review` against **prod** (the live app's data)

**Code and data are separate pipes.** Merging a PR ships *code* to Cloud Run; it never copies
database rows. `vja-discover` and `vja-review` write to whatever database `VJA_DATABASE_URL` points at:

- **unset** (normal local dev) → `sqlite:///data/vja.db`, a file on your Mac. The live app never sees
  these rows, and **merging will not carry them over** — they're in a different database entirely.
- **set to the Neon URL** → your **production** Postgres, the same DB the cloud app reads and the
  nightly Cloud Run Job writes. A row approved here surfaces in the app after the next nightly.

So to promote a real employer into the live app, run the CLI pointed at Neon (the `VJA_DATABASE_URL`
secret from GCP / your Neon dashboard) — **no merge needed for the data to appear**:

```sh
export VJA_DATABASE_URL="postgresql://…neon…"   # or prefix a single command with it
uv run vja-review list                           # SAFETY: confirm you see the PROD proposals first
uv run vja-review approve 42                      # this write lands in prod → next nightly fetches it
```

⚠️ With `VJA_DATABASE_URL` set to Neon you are writing to the **live production database** from your
laptop. Appropriate for admin actions (approving employers is exactly that), but be deliberate: reads
(`list`) are harmless, writes (`approve`/`reject`) are real — always `list` first to confirm the target.
Unset the variable (or open a fresh shell) to go back to local SQLite. The cleaner long-term path is
running these as Cloud Run Jobs *in* the cloud (already pointed at Neon) — see `CUTOVER.md` §8b — so no
laptop-to-prod connection is needed.
