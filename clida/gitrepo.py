"""What changed in the chat's git repository while the chat ran, for the changes view.

Edit and Write calls are in the transcript; a shell command (sed, rm, a script, git revert) is
not. The repository catches those: every file a commit made during the chat touched, and every
uncommitted file last written during it, compared from where HEAD was when the chat started to
the file on disk now. Git does not know which program changed a file, so changes that anything
else made in the same repository and time count too.
"""

import os
import re
import subprocess
import threading

from . import transcripts

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's id of a tree with nothing in it
MARGIN = 120  # seconds after the chat's last transcript write that still count as during the chat
MAX_FILES = 200
MAX_REPOS = 5


def git(cwd, *args, binary=False):
    """Output of a git command in cwd, or None if it failed. Never takes optional locks: git status
    may otherwise hold index.lock, and a git commit Claude runs at that moment would fail."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-C", cwd, *args], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode:
        return None
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def _base(top: str, start: float):
    """The commit HEAD pointed to when the chat started.

    The reflog knows where HEAD was at any time, but only since the clone; before that, the
    newest commit of the current history made before the chat stands in.
    """
    reflog = git(top, "reflog", "--date=unix", "--format=%H %gd") or ""
    entries = []
    for line in reflog.splitlines():
        sha, _, ref = line.partition(" ")
        try:
            entries.append((sha, int(ref[ref.index("{") + 1:ref.index("}")])))
        except ValueError:
            continue
    if entries and entries[-1][1] <= start:
        return next(sha for sha, when in entries if when <= start)  # newest first
    sha = (git(top, "rev-list", "-1", f"--before={int(start)}", "HEAD") or "").strip()
    return sha or None


_COMMIT = re.compile(r"([0-9a-f]{40})\t(\d+)\t(.*)")


def _dirty_paths(status: str) -> list:
    """The paths in `git status --porcelain -z`: "XY path" each, a rename followed by its old path."""
    entries, paths = status.split("\0"), []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            if i < len(entries) and entries[i]:
                paths.append(entries[i])  # the old path: it is gone, and that is a change too
            i += 1
    return paths


class RepoChanges:
    """Cached by the repository's state and the chat's time window: the window polls after each turn."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}  # (top, start) -> (key, result)

    def get(self, dirs: list, start: float, end: float) -> dict:
        """Over the repositories that dirs are in: the chat's folder may hold no repository itself,
        only the folders it worked in (a chat in ~ that edits ~/project)."""
        tops = []
        for d in dict.fromkeys(dirs):
            top = (git(d, "rev-parse", "--show-toplevel") or "").strip() if os.path.isdir(d) else ""
            if top and top not in tops:
                tops.append(top)
            if len(tops) == MAX_REPOS:
                break
        files, commits = [], []
        for top in tops:
            result = self._repo(top, start, end)
            files += result["files"]
            commits += [{**c, "repo": os.path.basename(top)} for c in result["commits"]]
        commits.sort(key=lambda c: c["time"], reverse=True)
        return {"files": files, "commits": commits, "repos": tops}

    def _repo(self, top: str, start: float, end: float) -> dict:
        head = (git(top, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
        status = git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
        dirty = sorted(set(_dirty_paths(status)))
        stamps = tuple(_mtime(os.path.join(top, p)) for p in dirty)
        key = (head, status, stamps, int(end))
        with self._lock:
            hit = self._cache.get((top, start))
        if hit and hit[0] == key:
            return hit[1]
        result = self._compute(top, start, end, head, dirty)
        with self._lock:
            self._cache[(top, start)] = (key, result)
        return result

    @staticmethod
    def _compute(top, start, end, head, dirty) -> dict:
        until = end + MARGIN
        base = _base(top, start) if head else None
        commits, touched = [], set()
        if head:
            # -z: the header line of each commit, then its file names, all ended by NUL.
            log = git(top, "log", f"--since={int(start)}", f"--until={int(until)}", "--format=%H%x09%ct%x09%s",
                      "--name-only", "-z", f"{base}..HEAD" if base else "HEAD") or ""
            for part in log.split("\0"):
                part = part.strip("\n")
                commit = _COMMIT.fullmatch(part)
                if commit:
                    commits.append({"sha": commit.group(1)[:9], "time": int(commit.group(2)), "subject": commit.group(3)})
                elif part:
                    touched.add(part)
        # Uncommitted: only what was written during the chat. A file that is gone has no time;
        # it counts when the chat's starting commit still had it.
        for rel in dirty:
            when = _mtime(os.path.join(top, rel))
            if (when is not None and start <= when <= until) or (when is None and base):
                touched.add(rel)
        files = []
        for rel in sorted(touched)[:MAX_FILES]:
            before = git(top, "show", f"{base}:{rel}", binary=True) if base else None
            changed = _compare(os.path.join(top, rel), before)
            if changed:
                files.append(changed)
        return {"files": files, "commits": commits}


def _mtime(path):
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return None


def _compare(path: str, before_bytes) -> dict:
    """The file from before the chat (bytes, None: did not exist) against now; None if the same."""
    after, after_note = transcripts._read(path)
    exists = os.path.lexists(path)
    if before_bytes is None and not exists:
        return None
    before_note = None
    before = None
    if before_bytes is not None:
        if len(before_bytes) > transcripts.NET_SIZE_LIMIT:
            before_note = "large"
        elif b"\0" in before_bytes[:8192]:
            before_note = "binary"
        else:
            try:
                before = before_bytes.decode("utf-8")
            except UnicodeDecodeError:
                before_note = "binary"
    note = before_note or after_note
    status = "deleted" if not exists else "added" if before_bytes is None else "modified"
    out = {"path": path, "status": status, "note": note, "known": True, "net": None, "added": None,
           "removed": None, "edits": 0, "steps": [], "source": "git"}
    if note:
        if status == "modified" and before_bytes == _bytes(path):
            return None
        return out
    diff = transcripts._net_diff(before or "", after or "")
    if not diff["rows"]:
        return None  # the same as before the chat
    out.update(net=diff["rows"], added=diff["added"], removed=diff["removed"])
    return out


def _bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None
