"""Running Claude CLI processes, as announced in ~/.claude/sessions/<pid>.json."""

import json
import os
import subprocess

from . import CLAUDE_HOME

SESSIONS_DIR = CLAUDE_HOME / "sessions"
HAVE_PROC = os.path.exists("/proc/self/stat")  # Linux and WSL; macOS has no /proc


def _alive(pid, proc_start) -> bool:
    try:
        with open(f"/proc/{int(pid)}/stat") as f:
            stat = f.read()
    except (OSError, ValueError, TypeError):
        return False
    if proc_start is None:
        return True
    # Field 22 (starttime) guards against a recycled pid; fields after "(comm)" start at 3.
    fields = stat[stat.rindex(")") + 2:].split()
    return len(fields) > 19 and fields[19] == str(proc_start)


def _process_table() -> dict:
    """pid -> command line of every process, from ps(1). For systems without /proc."""
    try:
        listing = subprocess.run(["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True,
                                 timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table = {}
    for line in listing.splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit():
            table[int(pid)] = command
    return table


def running() -> dict:
    """Live CLI processes keyed by pid; stale files from dead processes are skipped."""
    # Without /proc there is no start time to compare, so a recycled pid must at least run claude.
    table = None if HAVE_PROC else _process_table()
    out = {}
    for path in SESSIONS_DIR.glob("*.json"):
        if not path.stem.isdigit():
            continue
        try:
            entry = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        pid = entry.get("pid")
        if not isinstance(pid, int):
            continue
        alive = _alive(pid, entry.get("procStart")) if table is None else "claude" in table.get(pid, "")
        if alive:
            out[pid] = entry
    return out


def cli_status(entry: dict) -> str:
    if entry.get("waitingFor"):
        return "waiting"
    return "busy" if entry.get("status") == "busy" else "idle"
