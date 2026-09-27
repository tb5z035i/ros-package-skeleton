#!/bin/bash
# Preserve absolute links throughout the shared CLI and daemon installation.
set -euo pipefail

codex_dir="${HOST_CODEX_DIR:?HOST_CODEX_DIR is required}"
container_codex_dir="$HOME/.codex"
binary="$codex_dir/packages/standalone/current/bin/codex"

if [[ ! -x "$binary" ]]; then
    printf 'Codex executable is unavailable: %s\nMount the full host ~/.codex at its original absolute path and rebuild the container.\n' "$binary" >&2
    exit 1
fi

# Codex uses ~/.codex by default. This alias also keeps daemon/current and any
# other absolute host links valid, without rewriting the host's installation.
if [[ "$container_codex_dir" != "$codex_dir" ]]; then
    if [[ ! -e "$container_codex_dir" && ! -L "$container_codex_dir" ]]; then
        ln -s "$codex_dir" "$container_codex_dir"
    elif [[ $(readlink -f "$container_codex_dir") != $(readlink -f "$codex_dir") ]]; then
        printf 'Refusing to replace an existing Codex directory: %s\nRebuild the container with the updated mounts.\n' "$container_codex_dir" >&2
        exit 1
    fi
fi

# Point to current, rather than a pinned release, so host upgrades remain visible.
sudo ln -sfnT "$binary" /usr/local/bin/codex
/usr/local/bin/codex --version
