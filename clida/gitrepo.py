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
from collections import OrderedDict

from . import transcripts

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's id of a tree with nothing in it
MARGIN = 120  # seconds after the chat's last transcript write that still count as during the chat
MAX_FILES = 200
MAX_REPOS = 5


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


def _status_entries(status: str):
    """(code, path) from `git status --porcelain -z`; a rename's old path follows as its own entry."""
    entries, out = status.split("\0"), []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        out.append((entry[:2], entry[3:]))
        if entry[0] in "RC" and i < len(entries):
            out.append(("D ", entries[i]))  # the old path is gone, and that is a change too
            i += 1
    return out


def _changed_at(path):
    """When a file last changed, renames included: mv and cp -p keep the mtime, not the ctime."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return max(st.st_mtime, st.st_ctime)


class _Lru:
    """A small cache that forgets the least recently used entries: every chat opened adds some."""

    def __init__(self, size: int):
        self._size, self._items, self._lock = size, OrderedDict(), threading.Lock()

    def get(self, slot, key):
        with self._lock:
            hit = self._items.get(slot)
            if hit is None or hit[0] != key:
                return None
            self._items.move_to_end(slot)
            return hit[1]

    def put(self, slot, key, value):
        with self._lock:
            self._items[slot] = (key, value)
            self._items.move_to_end(slot)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


class RepoChanges:
    """Cached by the repository's state: the window asks again after every turn of every chat.

    Which files changed is worked out once for the header and the view alike; the diffs are
    only made for the view, and kept per file until it changes.
    """

    def __init__(self):
        self._selections = _Lru(32)  # (top, start, end) -> (state, selection)
        self._diffs = _Lru(400)  # (top, base, rel) -> (stamp, diff fields)

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
            selection = self._select(top, start, end)
            for picked in selection["files"]:
                changed = {"path": os.path.join(top, picked["rel"]), "status": picked["status"], "note": None,
                           "known": True, "net": None, "added": None, "removed": None, "edits": 0, "steps": [],
                           "source": "git"}
                if not brief:
                    changed.update(self._diff(top, selection["base"], picked))
                files.append(changed)
            commits += [{**c, "repo": os.path.basename(top)} for c in selection["commits"]]
        commits.sort(key=lambda c: c["time"], reverse=True)
        return {"files": files, "commits": commits, "repos": tops}

    def _select(self, top: str, start: float, end) -> dict:
        head = (git(top, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
        status = git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
        entries = _status_entries(status)
        stamps = {rel: _changed_at(os.path.join(top, rel)) for _, rel in entries}
        state = (head, status, tuple(sorted(stamps.items(), key=lambda kv: kv[0])))
        slot = (top, start, end)
        hit = self._selections.get(slot, state)
        if hit is None:
            hit = _select(top, start, end, head, entries, stamps)
            self._selections.put(slot, state, hit)
        return hit

    def _diff(self, top: str, base, picked: dict) -> dict:
        rel = picked["rel"]
        stamp = (picked["status"], _changed_at(os.path.join(top, rel)))
        slot = (top, base, rel)
        hit = self._diffs.get(slot, stamp)
        if hit is None:
            hit = _fill_diff(top, base, rel, picked["status"])
            self._diffs.put(slot, stamp, hit)
        return hit


def _select(top, start, end, head, entries, stamps) -> dict:
    """The files that changed during the chat, with their status, and the commits made during it."""
    until = None if end is None else end + MARGIN
    base = _head_at(top, start) if head else None
    last = head if until is None or not head else (_head_at(top, until) or head)

    def written_during(rel):
        when = stamps.get(rel, _changed_at(os.path.join(top, rel)))
        return when is not None and start <= when and (until is None or when <= until)

    # What differs from the start, as the disk is now (tracked files). Mode changes (chmod) and
    # submodule pointers have no text to show, so they do not count.
    against = git(top, "-c", "core.fileMode=false", "diff", "--name-status", "-z", "--no-renames",
                  "--ignore-submodules", base or EMPTY_TREE) or ""
    differs = _name_status(against)
    # What HEAD moving during the chat changed: commits, reset, checkout, pull, merge, rebase.
    moved, commits = set(), []
    if last and last != base:
        moved = set(_name_status(git(top, "-c", "core.fileMode=false", "diff", "--name-status", "-z", "--no-renames",
                                     "--ignore-submodules", base or EMPTY_TREE, last) or ""))
        log = git(top, "log", "-n", "100", "--format=%H%x09%ct%x09%s", f"{base}..{last}" if base else last) or ""
        for line in log.splitlines():
            sha, when, subject = (line.split("\t", 2) + ["", ""])[:3]
            commits.append({"sha": sha[:9], "time": int(when or 0), "subject": subject})
    picked = set()
    for rel in differs:
        # A file that is gone has no time, so a deletion counts whenever it happened.
        if rel in moved or written_during(rel) or not os.path.lexists(os.path.join(top, rel)):
            picked.add(rel)
    for code, rel in entries:
        if code == "??" and written_during(rel):
            picked.add(rel)
    files = []
    for rel in sorted(picked)[:MAX_FILES]:
        # The status by what was there at the start and what is there now: git rm --cached or
        # reset --mixed leave a file on disk that git counts as deleted.
        in_base = rel in differs and differs[rel] != "A"
        exists = os.path.lexists(os.path.join(top, rel))
        status = "modified" if in_base and exists else "deleted" if in_base else "added"
        files.append({"rel": rel, "status": status})
    return {"files": files, "commits": commits, "base": base}


def _fill_diff(top: str, base, rel: str, status: str) -> dict:
    """The file at the start against now: its rows and lines added and removed, or why there are none."""
    before, before_note = None, None
    if base and status != "added":
        data = git(top, "show", f"{base}:{rel}", binary=True)
        before, before_note = transcripts.classify(data) if data is not None else (None, "unreadable")
    after, after_note = transcripts.read_text(os.path.join(top, rel)) if status != "deleted" else (None, None)
    note = before_note or after_note
    if note:
        return {"note": note}
    diff = transcripts.net_diff(before or "", after or "")
    return {"net": diff["rows"], "added": diff["added"], "removed": diff["removed"]}
