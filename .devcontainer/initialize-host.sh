#!/usr/bin/env bash
# Runs on the local Linux desktop before container creation and subsequent starts.
set -euo pipefail
state_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.local
mkdir -p "$state_dir"
chmod 700 "$state_dir"
umask 077
authority=$(mktemp "$state_dir/Xauthority.XXXXXX")
trap 'rm -f "$authority"' EXIT

if [[ -n ${DISPLAY:-} ]]; then
    if ! command -v xauth >/dev/null; then
        echo 'Install xauth on the Linux host, then reopen the devcontainer.' >&2
        exit 1
    fi
    # FamilyWild lets the same cookie work with the container's hostname.
    # Keep authentication data out of command output and out of the Docker context.
    cookies=$(xauth nlist "$DISPLAY")
    if [[ -z $cookies ]]; then
        echo 'No X11 cookie found. Open VS Code from the desktop session with DISPLAY and XAUTHORITY set.' >&2
        exit 1
    fi
    printf '%s\n' "$cookies" | sed 's/^..../ffff/' | xauth -f "$authority" nmerge -
else
    echo 'DISPLAY is unset; GUI forwarding requires a local X11/XWayland desktop session.' >&2
fi

# Mount the directory so refreshed cookies are visible even after atomic replacement.
mv "$authority" "$state_dir/Xauthority"
