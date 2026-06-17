#!/usr/bin/env bash
# Install the vja nightly LaunchAgent (macOS). Idempotent — safe to re-run (reloads in place).
set -euo pipefail

LABEL="com.vja.nightly"
# Repo root = two levels up from this script (deploy/launchd/install.sh).
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="$WORKDIR/deploy/launchd/$LABEL.plist.template"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -x "$WORKDIR/.venv/bin/vja-nightly" ]]; then
  echo "error: $WORKDIR/.venv/bin/vja-nightly not found — run 'uv sync' first." >&2
  exit 1
fi
if [[ ! -f "$WORKDIR/.env" ]]; then
  echo "warning: no $WORKDIR/.env — the run will fail without RESEND_API_KEY + VJA_DIGEST_RECIPIENT." >&2
fi

mkdir -p "$WORKDIR/logs" "$HOME/Library/LaunchAgents"
sed "s|__WORKDIR__|$WORKDIR|g" "$TEMPLATE" > "$PLIST"

# Reload if already loaded, so re-running picks up template/path changes.
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "installed $LABEL -> $PLIST (daily 06:00 local)"
echo "  fire once now:  launchctl start $LABEL"
echo "  check loaded:   launchctl list | grep vja"
echo "  logs:           tail -f $WORKDIR/logs/nightly.*.log"
