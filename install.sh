#!/usr/bin/env bash
# install.sh: set clida up after `git clone`, so the first `clida` opens the window at once.
# Puts the launcher on PATH, fetches the frontend libraries and offers the desktop shortcut.
# Safe to run again. Kept to bash 3.2, which is what macOS ships.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
LINK="$BIN/clida"

say() { echo "clida: $*"; }

# Python 3.9+ runs the server; without it nothing else is worth doing.
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  say "needs Python 3.9 or newer as python3 (Ubuntu/WSL: sudo apt-get install -y python3; macOS: xcode-select --install)" >&2
  exit 1
fi

mkdir -p "$BIN"
if [[ -L "$LINK" || ! -e "$LINK" ]]; then
  ln -sfn "$ROOT/bin/clida" "$LINK"
  say "launcher linked: $LINK -> $ROOT/bin/clida"
else
  say "$LINK exists and is not a symlink; left it alone. Remove it and run install.sh again." >&2
  exit 1
fi

"$ROOT/bin/clida" deps  # npm install of the frontend libraries; installs npm first if it is missing

command -v claude >/dev/null || PATH="$BIN:$PATH" command -v claude >/dev/null ||
  say "the claude CLI is not installed yet; see https://docs.claude.com/en/docs/claude-code/setup"

if [[ -t 0 ]] && { [[ -n "${WSL_DISTRO_NAME:-}" ]] || [[ "$(uname -s)" == Darwin ]]; }; then
  read -r -p "Create the CLIDA shortcut (WSL: Windows desktop, macOS: ~/Applications)? [Y/n] " answer
  [[ "$answer" =~ ^[nN] ]] || "$ROOT/bin/clida" shortcut
fi

# A ~/.local/bin created just now is not on PATH until the next login shell (~/.profile adds it).
case ":$PATH:" in
  *":$BIN:"*) say "done. Start it with: clida" ;;
  *) say "done. Open a new terminal (or run: source ~/.profile), then start it with: clida" ;;
esac
