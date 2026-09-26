#!/bin/bash
# Rebase the host standalone installation without changing its shared symlinks.
set -euo pipefail

codex_dir="$HOME/.codex"
standalone_dir="$codex_dir/packages/standalone"
current="$standalone_dir/current"

if [[ -L "$current" ]]; then
    target=$(readlink "$current")
    case "$target" in
        "${HOST_CODEX_DIR:?HOST_CODEX_DIR is required}"/*)
            target="$codex_dir/${target#"$HOST_CODEX_DIR"/}"
            ;;
        /*) ;;  # Already an absolute path; validate it below.
        *) target="$standalone_dir/$target" ;;
    esac
else
    target="$current"
fi

binary="$target/bin/codex"
if [[ ! -x "$binary" ]]; then
    printf 'Codex executable is unavailable: %s\nCheck the host ~/.codex mount and standalone installation.\n' "$binary" >&2
    exit 1
fi

# Keep the link outside the shared directory; refresh it on startup and attachment.
sudo ln -sfnT "$binary" /usr/local/bin/codex
/usr/local/bin/codex --version
