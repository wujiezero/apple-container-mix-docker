#!/bin/bash
# One-click uninstaller for the docker -> Apple container shim.
#
# Usage: ./uninstall.sh [--stop-services] [extra-dir...]
#   Removes every `docker` symlink pointing at this project from the common
#   install locations (~/.local/bin, ~/bin, /usr/local/bin, /opt/homebrew/bin)
#   plus any extra directories given as arguments.
#   --stop-services  also stop the `container` system services afterwards.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
note() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }

STOP_SERVICES=0
DIRS=("$HOME/.local/bin" "$HOME/bin" "/usr/local/bin" "/opt/homebrew/bin")
for arg in "$@"; do
    if [ "$arg" = "--stop-services" ]; then
        STOP_SERVICES=1
    else
        DIRS+=("$arg")
    fi
done

REMOVED=0
for dir in "${DIRS[@]}"; do
    for name in docker docker-compose; do
        LINK="$dir/$name"
        [ -L "$LINK" ] || continue
        case "$(readlink "$LINK")" in
            "$SCRIPT_DIR/bin/"*)
                if [ -w "$dir" ]; then
                    rm "$LINK"
                else
                    sudo rm "$LINK"
                fi
                say "removed: $LINK"
                REMOVED=1
                ;;
        esac
    done
done
[ "$REMOVED" = 1 ] || note "no shim symlink found (nothing removed)"

if grep -qE "^# disabled by apple-container-docker installer:" "$HOME/.zshrc" 2>/dev/null; then
    note "the installer had commented out an 'alias docker=...' line in ~/.zshrc;
    restore it manually if you still need it (search for 'disabled by apple-container-docker')."
fi

if [ "$STOP_SERVICES" = 1 ]; then
    say "stopping container services..."
    container system stop || note "failed to stop container services"
fi

say "uninstalled. The Apple container CLI itself and your images/containers are untouched."
