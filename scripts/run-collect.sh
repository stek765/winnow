#!/bin/bash
# Daily collection run, launched by launchd. Kept as a script so the schedule
# and the command stay separate: edit this without touching the plist.
set -euo pipefail
cd "$(dirname "$0")/.."
# The API key lives in a 600 file, never in the schedule definition.
set -a; . "$HOME/.config/winnow/env"; set +a
echo "=== $(date '+%F %T') ==="
exec .venv/bin/winnow collect
