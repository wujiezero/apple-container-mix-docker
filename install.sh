#!/bin/bash
# One-click installer for the docker -> Apple container shim.
#
# Usage: ./install.sh [target-dir]
#   target-dir  PATH directory for the `docker` symlink (default: ~/.local/bin)
#
# Steps: symlink shim -> PATH check -> shadowing-alias check -> start
# container services (installing the default kernel on first use) -> smoke test.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHIM="$SCRIPT_DIR/bin/docker"
TARGET_DIR="${1:-$HOME/.local/bin}"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
note() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. prerequisites -------------------------------------------------------
command -v container >/dev/null 2>&1 || fail \
    "Apple 'container' CLI not found. Install it first: https://github.com/apple/container/releases"
command -v python3 >/dev/null 2>&1 || fail "python3 not found on PATH"

# --- 1. symlinks --------------------------------------------------------------
COMPOSE_SHIM="$SCRIPT_DIR/bin/docker-compose"
chmod +x "$SHIM" "$COMPOSE_SHIM"
mkdir -p "$TARGET_DIR" 2>/dev/null || sudo mkdir -p "$TARGET_DIR"
if [ -w "$TARGET_DIR" ]; then
    ln -sf "$SHIM" "$TARGET_DIR/docker"
    ln -sf "$COMPOSE_SHIM" "$TARGET_DIR/docker-compose"
else
    say "$TARGET_DIR is not writable, using sudo"
    sudo ln -sf "$SHIM" "$TARGET_DIR/docker"
    sudo ln -sf "$COMPOSE_SHIM" "$TARGET_DIR/docker-compose"
fi
say "installed: $TARGET_DIR/docker -> $SHIM"
say "installed: $TARGET_DIR/docker-compose -> $COMPOSE_SHIM"

# --- 2. PATH check ----------------------------------------------------------
case ":$PATH:" in
    *":$TARGET_DIR:"*) ;;
    *) note "$TARGET_DIR is not on your PATH; add this to your shell profile:
    export PATH=\"$TARGET_DIR:\$PATH\"" ;;
esac

# --- 3. shadowing alias check -----------------------------------------------
ZSHRC="$HOME/.zshrc"
ALIAS_MATCH="$(grep -nE "^[[:space:]]*alias docker=" "$ZSHRC" 2>/dev/null | head -1 || true)"
if [ -n "$ALIAS_MATCH" ]; then
    LINE_NO="${ALIAS_MATCH%%:*}"
    ALIAS_TARGET="$(printf '%s' "$ALIAS_MATCH" | sed -E "s/.*alias docker=['\"]?([^'\" ]+).*/\1/")"
    if command -v "$ALIAS_TARGET" >/dev/null 2>&1; then
        note "~/.zshrc:$LINE_NO defines 'alias docker=$ALIAS_TARGET' which shadows the shim in interactive shells.
    Remove it manually if you want the shim to take over."
    else
        cp "$ZSHRC" "$HOME/.zshrc.docker-shim.bak"
        sed -i '' "${LINE_NO}s|^|# disabled by apple-container-docker installer: |" "$ZSHRC"
        say "commented out dead alias 'docker=$ALIAS_TARGET' in ~/.zshrc:$LINE_NO (backup: ~/.zshrc.docker-shim.bak)"
    fi
fi

# --- 4. container services + first-run kernel --------------------------------
if container system status >/dev/null 2>&1; then
    say "container services already running"
else
    say "starting container services..."
    if ! container system start </dev/null; then
        # First run: `system start` fails when no default kernel is configured
        # and it cannot prompt. Install the recommended kernel, then retry.
        say "installing the default Linux kernel (first run)..."
        container system kernel set --recommended
        container system start </dev/null
    fi
    say "container services started"
fi

# --- 5. smoke test ----------------------------------------------------------
say "smoke test:"
"$TARGET_DIR/docker" version
"$TARGET_DIR/docker" ps >/dev/null
say "all good — try: docker pull alpine && docker run --rm alpine echo hello"
