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
