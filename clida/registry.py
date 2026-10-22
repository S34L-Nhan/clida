"""Running Claude CLI processes, as announced in ~/.claude/sessions/<pid>.json."""

import json

from . import CLAUDE_HOME

SESSIONS_DIR = CLAUDE_HOME / "sessions"


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


def running() -> dict:
    """Live CLI processes keyed by pid; stale files from dead processes are skipped."""
    out = {}
    for path in SESSIONS_DIR.glob("*.json"):
        if not path.stem.isdigit():
            continue
        try:
            entry = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        pid = entry.get("pid")
        if isinstance(pid, int) and _alive(pid, entry.get("procStart")):
            out[pid] = entry
    return out


def cli_status(entry: dict) -> str:
    if entry.get("waitingFor"):
        return "waiting"
    return "busy" if entry.get("status") == "busy" else "idle"
