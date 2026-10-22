"""HTTP + WebSocket front door. Only reachable from this machine, and only with the token cookie."""

import hmac
import json
import mimetypes
import re
import secrets
import sys
import threading
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import ROOT, ws
from .app import HttpError

STATIC = ROOT / "static"
MODULES = ROOT / "node_modules"
VENDOR = {
    "xterm.mjs": "@xterm/xterm/lib/xterm.mjs",
    "xterm.css": "@xterm/xterm/css/xterm.css",
    "addon-fit.mjs": "@xterm/addon-fit/lib/addon-fit.mjs",
    "addon-web-links.mjs": "@xterm/addon-web-links/lib/addon-web-links.mjs",
    "marked.esm.js": "marked/lib/marked.esm.js",
    "purify.es.mjs": "dompurify/dist/purify.es.mjs",
    "highlight.mjs": "@highlightjs/cdn-assets/es/highlight.min.js",
}
COOKIE = "claude_desk_token"
TICKET_TTL = 60  # seconds a launcher login link stays valid
_TICKETS = {}  # one-time login ticket -> expiry (monotonic)
_TICKET_LOCK = threading.Lock()
SID = r"(?P<sid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
FID = r"(?P<fid>f[0-9a-f]{12})"
ROUTES = [(method, re.compile(pattern + r"\Z"), name) for method, pattern, name in [
    ("GET", r"/", "index"),
    ("GET", r"/static/(?P<name>[\w.-]+)", "static"),
    ("GET", r"/vendor/(?P<name>[\w.-]+)", "vendor"),
    ("GET", r"/api/sessions", "sessions"),
    ("GET", r"/api/status", "status"),
    ("GET", r"/api/cwds", "cwds"),
    ("GET", rf"/api/sessions/{SID}/messages", "messages"),
    ("PUT", rf"/api/sessions/{SID}/title", "rename"),
    ("PUT", rf"/api/sessions/{SID}/folder", "move_session"),
    ("PUT", rf"/api/sessions/{SID}/archived", "archive_session"),
    ("DELETE", rf"/api/sessions/{SID}", "delete_session"),
    ("POST", r"/api/folders", "create_folder"),
    ("PUT", rf"/api/folders/{FID}", "rename_folder"),
    ("DELETE", rf"/api/folders/{FID}", "delete_folder"),
    ("POST", r"/api/terminals", "start_terminal"),
    ("POST", r"/api/login-ticket", "login_ticket"),
    ("DELETE", rf"/api/terminals/{SID}", "stop_terminal"),
    ("GET", rf"/ws/terminals/{SID}", "attach"),
]]
mimetypes.add_type("text/javascript", ".mjs")

LOCKED_PAGE = """<!doctype html><meta charset="utf-8"><title>Claude Desk</title>
<body style="font:15px system-ui;padding:40px;background:#262624;color:#ecebe6">
<h2>Claude Desk</h2><p>Bitte über <code>claude-desk</code> öffnen, damit das Fenster angemeldet wird.</p>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "claude-desk"
    desk = None
    token = ""
    port = 0
    csp = ""

    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # -- plumbing ---------------------------------------------------------------------------

    def _dispatch(self, method):
        try:
            url = urlsplit(self.path)
            if url.path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            # A foreign Host header means DNS rebinding; a foreign Origin means another site.
            if self.headers.get("Host") not in (f"localhost:{self.port}", f"127.0.0.1:{self.port}"):
                return self._send(403, b"forbidden", "text/plain")
            origin = self.headers.get("Origin")
            if origin is not None and origin not in (f"http://localhost:{self.port}", f"http://127.0.0.1:{self.port}"):
                return self._send(403, b"forbidden", "text/plain")
            query = parse_qs(url.query)
            if method == "GET" and url.path == "/" and "ticket" in query:
                return self._login(query["ticket"][0])
            if not self._authed():
                return self._send(403, LOCKED_PAGE.encode(), "text/html; charset=utf-8")
            for route_method, pattern, name in ROUTES:
                match = pattern.match(url.path)
                if match and route_method == method:
                    return getattr(self, "route_" + name)(**match.groupdict())
            self._send_json(404, {"error": "Nicht gefunden"})
        except HttpError as e:
            self._send_json(e.status, {"error": e.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._send_json(500, {"error": "Interner Fehler, siehe server.log"})
            except OSError:
                pass

    def _authed(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        value = cookie[COOKIE].value if COOKIE in cookie else ""
        return hmac.compare_digest(value.encode(), self.token.encode())

    def _login(self, ticket):
        """Swap a one-time ticket from the launcher for the session cookie.

        Tickets keep the real token out of URLs, so browser history and process lists
        only ever see a link that is already used up.
        """
        with _TICKET_LOCK:
            expiry = _TICKETS.pop(ticket, 0)
        valid = expiry > time.monotonic()
        if not valid and not self._authed():
            return self._send(403, LOCKED_PAGE.encode(), "text/html; charset=utf-8")
        self.send_response(303)
        self.send_header("Location", "/")
        if valid:
            self.send_header("Set-Cookie", f"{COOKIE}={self.token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, status, body: bytes, ctype, cache=False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", self.csp)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1024 * 1024:
            raise HttpError(413, "Anfrage zu groß")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise HttpError(400, "Ungültiges JSON")
        if not isinstance(body, dict):
            raise HttpError(400, "Ungültiges JSON")
        return body

    def _file(self, path, cache=False):
        try:
            body = path.read_bytes()
        except OSError:
            raise HttpError(404, "Nicht gefunden")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype, cache=cache)

    # -- routes -----------------------------------------------------------------------------

    def route_index(self):
        self._file(STATIC / "index.html")

    def route_static(self, name):
        if name.startswith("."):
            raise HttpError(404, "Nicht gefunden")
        self._file(STATIC / name)

    def route_vendor(self, name):
        if name not in VENDOR:
            raise HttpError(404, "Nicht gefunden")
        self._file(MODULES / VENDOR[name], cache=True)

    def route_sessions(self):
        self._send_json(200, self.desk.sessions())

    def route_status(self):
        self._send_json(200, self.desk.status())

    def route_cwds(self):
        self._send_json(200, {"cwds": self.desk.cwds()})

    def route_messages(self, sid):
        self._send_json(200, self.desk.messages(sid))

    def route_rename(self, sid):
        self._send_json(200, self.desk.rename(sid, self._body().get("title")))

    def route_move_session(self, sid):
        self._send_json(200, self.desk.move_session(sid, self._body().get("folder")))

    def route_archive_session(self, sid):
        self._send_json(200, self.desk.archive_session(sid, self._body().get("archived")))

    def route_delete_session(self, sid):
        self._send_json(200, self.desk.delete_session(sid))

    def route_create_folder(self):
        self._send_json(200, self.desk.create_folder(self._body().get("name")))

    def route_rename_folder(self, fid):
        self._send_json(200, self.desk.rename_folder(fid, self._body().get("name")))

    def route_delete_folder(self, fid):
        self._send_json(200, self.desk.delete_folder(fid))

    def route_start_terminal(self):
        self._send_json(200, self.desk.start_terminal(self._body()))

    def route_login_ticket(self):
        ticket = secrets.token_urlsafe(24)
        with _TICKET_LOCK:
            now = time.monotonic()
            for stale in [t for t, expiry in _TICKETS.items() if expiry <= now]:
                del _TICKETS[stale]
            _TICKETS[ticket] = now + TICKET_TTL
        self._send_json(200, {"ticket": ticket})

    def route_stop_terminal(self, sid):
        self._send_json(200, self.desk.stop_terminal(sid))

    def route_attach(self, sid):
        term = self.desk.terminals.get(sid)
        key = self.headers.get("Sec-WebSocket-Key")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
            raise HttpError(400, "WebSocket erwartet")
        if self.headers.get("Origin") is None:
            raise HttpError(403, "Origin fehlt")
        if term is None:
            raise HttpError(404, "Terminal läuft nicht")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", ws.accept_value(key))
        self.end_headers()
        sock = ws.WebSocket(self.connection, self.rfile)
        self.close_connection = True
        term.attach(sock)
        try:
            while True:
                is_text, payload = sock.recv()
                if not is_text:
                    term.write(payload)
                    continue
                msg = json.loads(payload)
                if msg.get("t") == "i":
                    term.write(str(msg.get("d", "")).encode())
                elif msg.get("t") == "r":
                    term.resize(int(msg.get("c", 0)), int(msg.get("r", 0)))
        except (ws.Closed, OSError, ValueError):
            pass
        finally:
            term.detach(sock)
            sock.close()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _csp(port: int) -> str:
    # Script only from this server: even if sanitizing ever failed, injected markup could not run.
    sockets = f"ws://localhost:{port} ws://127.0.0.1:{port}"
    return ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            f"connect-src 'self' {sockets}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'")


def make_server(desk, token: str, host: str, port: int) -> Server:
    handler = type("BoundHandler", (Handler,), {"desk": desk, "token": token, "port": port, "csp": _csp(port)})
    return Server((host, port), handler)
