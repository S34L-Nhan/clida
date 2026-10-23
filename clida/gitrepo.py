"""What changed in the chat's git repository during the chat, for the changes view.

Edit and Write calls are in the transcript; a shell command (sed, rm, mv, a script, git reset) is
not. The repository catches those. A file counts when it differs between where HEAD was when the
chat started and the disk now, and that difference came about during the chat: HEAD moved over it
(a commit, reset, checkout, pull, merge or rebase), or it is uncommitted and was written, created,
renamed or deleted while the chat ran. Git does not know which program changed a file, so what
anything else did in the same repository at that time counts too.
"""

import os
import subprocess
import threading

from . import transcripts

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's id of a tree with nothing in it
MARGIN = 120  # seconds after the chat's last transcript write that still count as during the chat
MAX_FILES = 200
MAX_REPOS = 5
_STATUS = {"A": "added", "D": "deleted"}  # git diff --name-status letters; everything else: modified


def git(cwd, *args, binary=False, timeout=10):
    """Output of a git command in cwd, or None if it failed. Never takes optional locks: git status
    may otherwise hold index.lock, and a git commit Claude runs at that moment would fail."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-C", cwd, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode:
        return None
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def _head_at(top: str, when: float):
    """The commit HEAD pointed to at a time.

    The reflog knows where HEAD was at any time, but only since the clone; before that, the
    newest commit of the current history made before then stands in.
    """
    reflog = git(top, "reflog", "--date=unix", "--format=%H %gd") or ""
    entries = []
    for line in reflog.splitlines():
        sha, _, ref = line.partition(" ")
        try:
            entries.append((sha, int(ref[ref.index("{") + 1:ref.index("}")])))
        except ValueError:
            continue
    if entries and entries[-1][1] <= when:
        return next(sha for sha, at in entries if at <= when)  # newest first
    sha = (git(top, "rev-list", "-1", f"--before={int(when)}", "HEAD") or "").strip()
    return sha or None


def _name_status(text: str) -> dict:
    """path -> letter from `git diff --name-status -z --no-renames`: letter NUL path NUL, repeated."""
    parts = text.split("\0")
    return {parts[i + 1]: parts[i][:1] for i in range(0, len(parts) - 1, 2) if parts[i]}


def _changed_at(path):
    """When a file last changed, renames included: mv and cp -p keep the mtime, not the ctime."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return max(st.st_mtime, st.st_ctime)


class RepoChanges:
    """Cached by the repository's state: the window asks again after every turn of every chat."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}  # (top, start, end, brief) -> (key, result)

    def get(self, dirs: list, start: float, end, brief: bool = False) -> dict:
        """Over the repositories that dirs are in: the chat's folder may hold no repository itself,
        only the folders it worked in (a chat in ~ that edits ~/project). end None: still running."""
        tops = []
        for d in dirs:
            top = (git(d, "rev-parse", "--show-toplevel") or "").strip()
            if top and top not in tops:
                tops.append(top)
            if len(tops) == MAX_REPOS:
                break
        files, commits = [], []
        for top in tops:
            result = self._repo(top, start, end, brief)
            files += result["files"]
            commits += [{**c, "repo": os.path.basename(top)} for c in result["commits"]]
        commits.sort(key=lambda c: c["time"], reverse=True)
        return {"files": files, "commits": commits, "repos": tops}

    def _repo(self, top: str, start: float, end, brief: bool) -> dict:
        head = (git(top, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
        status = git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
        # The key holds what the result depends on; a running chat's end is not a time yet.
        stamps = tuple(_changed_at(os.path.join(top, entry[3:])) for entry in status.split("\0") if len(entry) > 3)
        key = (head, status, stamps)
        slot = (top, start, end, brief)
        with self._lock:
            hit = self._cache.get(slot)
        if hit and hit[0] == key:
            return hit[1]
        result = self._compute(top, start, end, head, brief)
        with self._lock:
            self._cache[slot] = (key, result)
        return result

    @staticmethod
    def _compute(top, start, end, head, brief) -> dict:
        until = None if end is None else end + MARGIN
        base = _head_at(top, start) if head else None
        last = head if until is None or not head else (_head_at(top, until) or head)
        # What differs from the start, as the disk is now (index and work tree, not untracked files).
        against = git(top, "diff", "--name-status", "-z", "--no-renames", base or EMPTY_TREE) or ""
        differs = _name_status(against)
        # What HEAD moving during the chat changed: commits, reset, checkout, pull, merge, rebase.
        moved = set(_name_status(git(top, "diff", "--name-status", "-z", "--no-renames", base or EMPTY_TREE, last) or ""))
        if not last:
            moved = set()
        commits = []
        if last:
            log = git(top, "log", "--format=%H%x09%ct%x09%s", f"{base}..{last}" if base else last) or ""
            for line in log.splitlines()[:100]:
                sha, when, subject = (line.split("\t", 2) + ["", ""])[:3]
                commits.append({"sha": sha[:9], "time": int(when or 0), "subject": subject})

        def during(rel):
            when = _changed_at(os.path.join(top, rel))
            return when is None or (start <= when and (until is None or when <= until))  # gone: no time

        picked = {rel: _STATUS.get(letter, "modified") for rel, letter in differs.items()
                  if rel in moved or during(rel)}
        untracked = git(top, "ls-files", "--others", "--exclude-standard", "-z") or ""
        for rel in filter(None, untracked.split("\0")):
            when = _changed_at(os.path.join(top, rel))
            if when is not None and start <= when and (until is None or when <= until):
                picked[rel] = "added"
        files = []
        for rel in sorted(picked)[:MAX_FILES]:
            changed = {"path": os.path.join(top, rel), "status": picked[rel], "note": None, "known": True,
                       "net": None, "added": None, "removed": None, "edits": 0, "steps": [], "source": "git"}
            if not brief:
                _fill_diff(changed, top, base, rel)
            files.append(changed)
        return {"files": files, "commits": commits}


def _fill_diff(changed: dict, top: str, base, rel: str):
    """The file at the start against now, into changed: its rows and lines added and removed."""
    before, before_note = None, None
    if base and changed["status"] != "added":
        data = git(top, "show", f"{base}:{rel}", binary=True)
        before, before_note = transcripts.classify(data) if data is not None else (None, "unreadable")
    after, after_note = transcripts.read_text(changed["path"]) if changed["status"] != "deleted" else (None, None)
    changed["note"] = before_note or after_note
    if changed["note"]:
        return
    diff = transcripts.net_diff(before or "", after or "")
    changed.update(net=diff["rows"], added=diff["added"], removed=diff["removed"])
