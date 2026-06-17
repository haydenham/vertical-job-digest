#!/usr/bin/env bash
# Remove the vja nightly LaunchAgent (macOS). Leaves logs in place.
set -euo pipefail

LABEL="com.vja.nightly"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled $LABEL (logs left in place)"
