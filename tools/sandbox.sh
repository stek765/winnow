#!/usr/bin/env bash
# A throwaway winnow, in its own config and data directories.
#
# Every path winnow uses comes from paths.py, and every one of them is
# overridable by environment variable — so a full first-run can be rehearsed
# without touching the real config, the real seen.json or the real findings.
#
#   tools/sandbox.sh            make one and print how to enter it
#   tools/sandbox.sh --link     reuse the real Instagram session and API key
#   tools/sandbox.sh --wipe     delete it
#
# ⚠️ `winnow schedule` is NOT sandboxed. The launch agent has one label per
#    machine, so running it in here replaces the real one. Leave it alone.
set -euo pipefail

BOX="${WINNOW_SANDBOX:-${TMPDIR:-/tmp}/winnow-sandbox}"
REAL_CONFIG="${HOME}/.config/winnow"
REAL_DATA="${HOME}/.local/share/winnow"

if [ "${1:-}" = "--wipe" ]; then
    # The browser profile is a symlink to the real one when --link was used:
    # remove the link, never what it points at.
    rm -rf "$BOX"
    echo "  gone: $BOX"
    exit 0
fi

mkdir -p "$BOX/config" "$BOX/data"
chmod 700 "$BOX/config"

if [ "${1:-}" = "--link" ]; then
    if [ -f "$REAL_CONFIG/env" ]; then
        cp "$REAL_CONFIG/env" "$BOX/config/env"
        chmod 600 "$BOX/config/env"
        echo "  API key copied — 'winnow init' will find it already there."
    fi
    if [ -d "$REAL_DATA/browser-profile" ] && [ ! -e "$BOX/data/browser-profile" ]; then
        # 1.3 GB of Chromium profile: linked, not copied. It carries the
        # Instagram session, so 'winnow login' can be skipped.
        ln -s "$REAL_DATA/browser-profile" "$BOX/data/browser-profile"
        echo "  Instagram session linked — no need to log in again."
        echo "  ⚠️  it is the real session: do not run a real collect at the"
        echo "      same time, one Chromium profile cannot serve two."
    fi
fi

cat <<EOF

  Sandbox ready:  $BOX

  Open a shell in it and run the whole sequence from nothing:

    export WINNOW_CONFIG_DIR="$BOX/config"
    export WINNOW_DATA_DIR="$BOX/data"

    winnow where            # check both paths point in here BEFORE anything
    winnow init             # the guided setup, from zero
    winnow collect --posts 2
    winnow status
    winnow recap --days 1

  Close the shell and the real winnow is exactly as it was.
  Delete it with:  tools/sandbox.sh --wipe

EOF
