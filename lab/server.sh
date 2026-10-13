#!/bin/sh
# Instructor shortcut for the existing public game host's SSH profile.
set -eu
HP_LAB_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
HP_KNOWN_HOSTS="$HP_LAB_DIR/../.lab/remote-known-hosts"
if [ -f "$HP_KNOWN_HOSTS" ]; then
    exec python3 "$HP_LAB_DIR/tools/server_console.py" "$@" \
        --ssh "${HACKPACK_SERVER_SSH:-honohono-local}" --known-hosts "$HP_KNOWN_HOSTS"
fi
exec python3 "$HP_LAB_DIR/tools/server_console.py" "$@" \
    --ssh "${HACKPACK_SERVER_SSH:-honohono-local}"
