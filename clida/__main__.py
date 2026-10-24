"""Run the clida server: python3 -m clida [--port N]."""

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
    found = os.environ.get("CLIDA_CLAUDE") or shutil.which("claude")
    # A macOS app starts with a minimal PATH; these are the usual install places.
    for fallback in (Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")):
        if not found and fallback.exists():
            found = str(fallback)
    if not found:
        sys.exit("clida: `claude` not found (put it on PATH or set CLIDA_CLAUDE)")
    # Not resolved: ~/.local/bin/claude is a symlink that each auto-update points at a new version,
    # and the installer deletes old ones. A resolved path would start them long after they are gone.
    return os.path.abspath(found)


def main():
    parser = argparse.ArgumentParser(prog="clida")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CLIDA_PORT", 47321)))
    parser.add_argument("--detach", action="store_true", help="fork into the background (used by the launcher)")
    args = parser.parse_args()
    if args.detach:
        # An own session, so closing the terminal that ran `clida` does not end the server.
        # setsid(1) would do the same, but macOS does not have it.
        if os.fork():
            os._exit(0)
        os.setsid()

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
    print(f"clida runs on http://localhost:{args.port}", flush=True)
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
