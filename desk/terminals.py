"""Claude CLI processes running in pseudo-terminals, shared with any attached browser tabs."""

import fcntl
import os
import pty
import signal
import struct
import termios
import threading
import time
import uuid

from . import registry

SCROLLBACK_BYTES = 2 * 1024 * 1024

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
    env.setdefault("LANG", "C.UTF-8")
    return env


class Terminal:
    def __init__(self, claude: str, cwd: str, session_id: str, argv: list):
        self.id = session_id          # stable key for tabs and websockets
        self.session_id = session_id  # follows /clear and /resume inside the CLI
        self.cwd = cwd
        self.started = time.time()
        self.last_output = 0.0
        self.exit_code = None
        self._buf = bytearray()
        self._clients = []
        self._lock = threading.Lock()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                os.chdir(cwd)
                os.execve(claude, [claude, *argv], child_env())
            finally:
                os._exit(127)
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
                self._broadcast(lambda ws: ws.send_binary(data))
        _, status = os.waitpid(self.pid, 0)
        # The master fd stays open until close(), so a late write() can never hit a reused fd.
        with self._lock:
            self.exit_code = os.waitstatus_to_exitcode(status)
            self._broadcast(lambda ws: ws.send_json({"t": "exit", "code": self.exit_code}))

    def _broadcast(self, send):
        for ws in list(self._clients):
            try:
                send(ws)
            except OSError:
                self._clients.remove(ws)

    def attach(self, ws):
        """Replay the scrollback, then stream live output to ws."""
        with self._lock:
            if self._buf:
                ws.send_binary(bytes(self._buf))
            if not self.alive:
                ws.send_json({"t": "exit", "code": self.exit_code})
            self._clients.append(ws)

    def detach(self, ws):
        with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

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
                current = self._by_id.get(resume)
                if current is not None:
                    if current.alive:
                        return current
                    current.close()
                argv = ["--resume", resume]
                session_id = resume
            else:
                session_id = str(uuid.uuid4())
                argv = ["--session-id", session_id] + (["--name", name] if name else [])
            term = Terminal(self.claude, cwd, session_id, argv)
            self._by_id[session_id] = term
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

    def shutdown(self, timeout: float = 5):
        terms = [t for t in self.all() if t.alive]
        for term in terms:
            term.terminate()
        deadline = time.time() + timeout
        while time.time() < deadline and any(t.alive for t in terms):
            time.sleep(0.1)
