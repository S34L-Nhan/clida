"""Claude CLI processes running in pseudo-terminals, shared with any attached browser tabs."""

import collections
import fcntl
import os
import sys
import pty
import signal
import struct
import termios
import threading
import time
import uuid

from . import STATE_DIR, registry

SCROLLBACK_BYTES = 2 * 1024 * 1024
UPLOADS = STATE_DIR / "uploads"  # files dropped into a session, one folder per session
VIEWER_BACKLOG_BYTES = 8 * 1024 * 1024  # a tab further behind than this is dropped and reconnects
EXITED_TTL = 600  # seconds an exited terminal waits for a tab that has not seen its end yet

# Variables that would make the child think it runs inside this server's own Claude session.
_INHERITED_SESSION_VARS = {
    "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_SSE_PORT",
    "TERM_PROGRAM", "TERM_PROGRAM_VERSION",
}


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _INHERITED_SESSION_VARS}
    env.update(TERM="xterm-256color", COLORTERM="truecolor")
    env.setdefault("LANG", "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8")  # macOS has no C.UTF-8
    return env


class _Viewer:
    """One attached browser tab. Its own thread does the sending, so a slow tab never stalls the PTY."""

    def __init__(self, ws):
        self.ws = ws
        self._items = collections.deque()  # bytes (terminal output) or dict (control message)
        self._queued = 0
        self._cond = threading.Condition()
        self._closed = False
        threading.Thread(target=self._run, name="ws-writer", daemon=True).start()

    def push(self, item):
        """Queue output for this tab; never blocks."""
        size = len(item) if isinstance(item, bytes) else 0
        with self._cond:
            if self._closed:
                return
            if self._queued + size > VIEWER_BACKLOG_BYTES:
                self._closed = True
                self._cond.notify()
                self.ws.abort()
                return
            self._items.append(item)
            self._queued += size
            self._cond.notify()

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify()

    def _next(self):
        """Wait for the next message; merge queued output into one frame."""
        with self._cond:
            while not self._items and not self._closed:
                self._cond.wait()
            if self._closed:
                return None
            item = self._items.popleft()
            if isinstance(item, bytes):
                chunks = [item]
                while self._items and isinstance(self._items[0], bytes) and len(chunks) < 256:
                    chunks.append(self._items.popleft())
                item = b"".join(chunks)
                self._queued -= len(item)
            return item

    def _run(self):
        while (item := self._next()) is not None:
            try:
                if isinstance(item, bytes):
                    self.ws.send_binary(item)
                else:
                    self.ws.send_json(item)
            except OSError:
                self.close()
                self.ws.abort()


class Terminal:
    def __init__(self, claude: str, cwd: str, session_id: str, argv: list, uploads):
        # Its own id, not the session's: after /clear the terminal runs another session, and the
        # old chat must still open (and resume) on its own.
        self.id = str(uuid.uuid4())   # key for tabs and websockets
        self.session_id = session_id  # follows /clear and /resume inside the CLI
        self.uploads = uploads        # the folder passed with --add-dir
        self.cwd = cwd
        self.started = time.time()
        self.last_output = 0.0
        self.exit_code = None
        self.exited_at = None
        self._buf = bytearray()
        self._viewers = {}  # websocket -> _Viewer
        self._lock = threading.Lock()
        env = child_env()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                # This server ignores SIGHUP and Python ignores SIGPIPE; ignored signals survive exec,
                # and a CLI that ignores SIGHUP would not end on "Stop".
                signal.signal(signal.SIGHUP, signal.SIG_DFL)
                signal.signal(signal.SIGPIPE, signal.SIG_DFL)
                os.chdir(cwd)
                os.execve(claude, [claude, *argv], env)
            except OSError as e:
                os.write(1, f"clida: {claude}: {e.strerror}\r\n".encode())  # the PTY, so the tab shows why
            finally:
                os._exit(127)
        # pty.fork() leaves the master inheritable: every later session would get a copy.
        os.set_inheritable(self.fd, False)
        self.resize(120, 32)
        threading.Thread(target=self._pump, name=f"pty-{self.id[:8]}", daemon=True).start()

    @property
    def alive(self) -> bool:
        return self.exit_code is None

    def status(self, entry) -> str:
        if not self.alive:
            return "exited"
        if entry is not None:
            return registry.cli_status(entry)
        if time.time() - self.started < 15:
            return "starting"
        return "busy" if time.time() - self.last_output < 2 else "idle"

    def _pump(self):
        while True:
            try:
                data = os.read(self.fd, 65536)
            except OSError:
                data = b""
            if not data:
                break
            with self._lock:
                self.last_output = time.time()
                self._buf += data
                if len(self._buf) > SCROLLBACK_BYTES:
                    cut = self._buf.find(b"\n", len(self._buf) - SCROLLBACK_BYTES)
                    del self._buf[:cut + 1 if cut >= 0 else len(self._buf) - SCROLLBACK_BYTES]
                for viewer in self._viewers.values():
                    viewer.push(data)
        _, status = os.waitpid(self.pid, 0)
        # The master fd stays open until close(), so a late write() can never hit a reused fd.
        with self._lock:
            self.exited_at = time.time()  # before exit_code: reap() reads it once alive is False
            self.exit_code = os.waitstatus_to_exitcode(status)
            for viewer in self._viewers.values():
                viewer.push({"t": "exit", "code": self.exit_code})

    @property
    def watched(self) -> bool:
        with self._lock:
            return bool(self._viewers)

    def attach(self, ws):
        """Replay the scrollback, then stream live output to ws."""
        viewer = _Viewer(ws)
        with self._lock:
            if self._buf:
                viewer.push(bytes(self._buf))
            if not self.alive:
                viewer.push({"t": "exit", "code": self.exit_code})
            self._viewers[ws] = viewer

    def detach(self, ws):
        with self._lock:
            viewer = self._viewers.pop(ws, None)
        if viewer:
            viewer.close()

    def write(self, data: bytes):
        if not self.alive:
            return
        view = memoryview(data)
        while view:
            try:
                n = os.write(self.fd, view)
            except OSError:
                return
            view = view[n:]

    def resize(self, cols: int, rows: int):
        if self.alive and 0 < cols < 1000 and 0 < rows < 1000:
            try:
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            except OSError:
                pass

    def terminate(self):
        """SIGHUP lets the CLI save its transcript; SIGKILL if it hangs."""
        if not self.alive:
            return
        try:
            os.killpg(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            return

        def force():
            if self.alive:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        threading.Timer(5, force).start()

    def close(self):
        if not self.alive:
            try:
                os.close(self.fd)
            except OSError:
                pass


class Terminals:
    def __init__(self, claude: str):
        self.claude = claude
        self._lock = threading.Lock()
        self._by_id = {}

    def start(self, cwd: str, resume: str = None, name: str = None) -> Terminal:
        with self._lock:
            if resume:
                for current in self._by_id.values():
                    if current.alive and current.session_id == resume:
                        return current
                argv = ["--resume", resume]
                session_id = resume
            else:
                session_id = str(uuid.uuid4())
                argv = ["--session-id", session_id] + (["--name", name] if name else [])
            # The CLI only reads pasted file paths inside its directories; this one gets the uploads.
            uploads = UPLOADS / session_id
            uploads.mkdir(mode=0o700, parents=True, exist_ok=True)
            argv += ["--add-dir", str(uploads)]
            term = Terminal(self.claude, cwd, session_id, argv, uploads)
            self._by_id[term.id] = term
            return term

    def get(self, terminal_id: str):
        with self._lock:
            return self._by_id.get(terminal_id)

    def all(self) -> list:
        with self._lock:
            return list(self._by_id.values())

    def stop(self, terminal_id: str) -> bool:
        """Terminate a running terminal, or forget an exited one."""
        with self._lock:
            term = self._by_id.get(terminal_id)
            if term is None:
                return False
            if not term.alive:
                del self._by_id[terminal_id]
                term.close()
                return True
        term.terminate()
        return True

    def reap(self):
        """Forget exited terminals that no tab watches any more."""
        now = time.time()
        with self._lock:
            for terminal_id, term in list(self._by_id.items()):
                if not term.alive and now - term.exited_at > EXITED_TTL and not term.watched:
                    del self._by_id[terminal_id]
                    term.close()

    def shutdown(self, timeout: float = 5):
        terms = [t for t in self.all() if t.alive]
        for term in terms:
            term.terminate()
        deadline = time.time() + timeout
        while time.time() < deadline and any(t.alive for t in terms):
            time.sleep(0.1)
