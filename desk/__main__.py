"""Run the claude-desk server: python3 -m desk [--port N]."""

import argparse
import os
import secrets
import shutil
import signal
import sys
import threading
from pathlib import Path

from . import STATE_DIR
from .app import Desk
from .web import make_server


def _token() -> str:
    path = STATE_DIR / "token"
    try:
        token = path.read_text().strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    return token


def _claude_binary() -> str:
    found = os.environ.get("CLAUDE_DESK_CLAUDE") or shutil.which("claude")
    fallback = Path.home() / ".local/bin/claude"
    if not found and fallback.exists():
        found = str(fallback)
    if not found:
        sys.exit("claude-desk: `claude` nicht gefunden (PATH oder CLAUDE_DESK_CLAUDE setzen)")
    return os.path.realpath(found)


def main():
    parser = argparse.ArgumentParser(prog="claude-desk")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CLAUDE_DESK_PORT", 47321)))
    args = parser.parse_args()

    # Index, titles and log quote your prompts, so keep the folder private.
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)
    desk = Desk(_claude_binary())
    server = make_server(desk, _token(), args.host, args.port)
    (STATE_DIR / "server.pid").write_text(str(os.getpid()))
    threading.Thread(target=desk.index.scan, name="initial-scan", daemon=True).start()

    def stop(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    print(f"claude-desk läuft auf http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        desk.terminals.shutdown()
        server.server_close()
        try:
            (STATE_DIR / "server.pid").unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
