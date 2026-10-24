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
DIFF_CACHE_ROWS = 200_000  # diff rows kept in memory over all files; a diff over 1/20 of it is not kept


def git(cwd, *args, binary=False, timeout=10, stdin=None, ok=(0,)):
    """Output of a git command in cwd, or None if it failed (an exit code not in ok). Never takes
    optional locks: git status may otherwise hold index.lock, and a git commit Claude runs at that
    moment would fail."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-C", cwd, *args], capture_output=True, timeout=timeout,
                             input=stdin)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode not in ok:
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
        if (entry[0] in "RC" or entry[1] in "RC") and i < len(entries):  # index or work tree (git add -N)
            # The old path is gone, and that is a change too: staged with the index's rename,
            # in the work tree with the work tree's.
            out.append(("D " if entry[0] in "RC" else " D", entries[i]))
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
    """A small cache that forgets the least recently used entries: every chat opened adds some.

    weight, if given, measures an entry (a diff: its rows), and the entries together stay under budget.
    """

    def __init__(self, size: int, budget: int = 0, weight=None):
        self._size, self._items, self._lock = size, OrderedDict(), threading.Lock()
        self._budget, self._weight, self._total = budget, weight, 0

    def get(self, slot, key):
        with self._lock:
            hit = self._items.get(slot)
            if hit is None or hit[0] != key:
                return None
            self._items.move_to_end(slot)
            return hit[1]

    def put(self, slot, key, value):
        weigh = self._weight or (lambda value: 0)
        with self._lock:
            old = self._items.pop(slot, None)
            if old is not None:
                self._total -= weigh(old[1])
            self._items[slot] = (key, value)
            self._total += weigh(value)
            while len(self._items) > 1 and (len(self._items) > self._size or (self._budget and self._total > self._budget)):
                _, (_, dropped) = self._items.popitem(last=False)
                self._total -= weigh(dropped)


class RepoChanges:
    """Cached by the repository's state: the window asks again after every turn of every chat.

    Which files changed is worked out once for the header and the view alike; the diffs are
    only made for the view, and kept per file until it changes.
    """

    def __init__(self):
        self._selections = _Lru(32)  # (top, start, end) -> (state, selection)
        # (top, base, rel) -> (stamp, diff fields); a diff can have thousands of rows, so by rows too
        self._diffs = _Lru(400, budget=DIFF_CACHE_ROWS, weight=lambda fields: len(fields.get("net") or ()))
        self._states = _Lru(32)  # (top, start) -> (repo state, git state of its files)
        self._tops = _Lru(2000)  # folder -> its repository's top folder ("" outside one)

    def _top(self, folder: str) -> str:
        """The repository a folder is in; for a deleted file, its nearest folder that is still there."""
        while folder and not os.path.isdir(folder):
            parent = os.path.dirname(folder)
            folder = "" if parent == folder else parent
        if not folder:
            return ""
        top = self._tops.get(folder, None)
        if top is None:
            top = (git(folder, "rev-parse", "--show-toplevel") or "").strip()
            self._tops.put(folder, None, top)
        return top

    def states(self, paths: list, start) -> dict:
        """Whether each file is in a repository and where it stands there, for "will it be committed?".

        path -> {"repo": {"top", "name", "branch"} or None, "rel": path in the repository,
        "state": committed | staged | unstaged | partly | untracked | ignored | None,
        "commit": {"sha", "subject"} of the newest commit during the chat that touched it}
        """
        by_top = {}
        for path in paths:
            by_top.setdefault(self._top(os.path.dirname(path)), []).append(path)
        out = {}
        for top, members in by_top.items():
            if not top:
                out.update({p: {"repo": None, "rel": None, "state": None, "commit": None} for p in members})
                continue
            head = (git(top, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
            status = git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
            key = (head, status, tuple(sorted(members)))
            hit = self._states.get((top, start), key)
            if hit is None:
                hit = _states(top, start, head, status, members)
                self._states.put((top, start), key, hit)
            out.update(hit)
        return out

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
        state = (head, status, tuple(stamps.values()))
        slot = (top, start, end)
        hit = self._selections.get(slot, state)
        if hit is None:
            hit = _select(top, start, end, head, entries, stamps)
            self._selections.put(slot, state, hit)
        return hit

    def _diff(self, top: str, base, picked: dict) -> dict:
        rel = picked["rel"]
        stamp = (picked["status"], picked["stamp"])
        slot = (top, base, rel)
        hit = self._diffs.get(slot, stamp)
        if hit is None:
            hit = _fill_diff(top, base, rel, picked["status"])
            # One huge diff (a lockfile, generated code) would push every other one out.
            if len(hit.get("net") or ()) <= DIFF_CACHE_ROWS // 20:
                self._diffs.put(slot, stamp, hit)
        return hit


def _select(top, start, end, head, entries, stamps) -> dict:
    """The files that changed during the chat, with their status, and the commits made during it."""
    until = None if end is None else end + MARGIN
    base = _head_at(top, start) if head else None
    last = head if until is None or not head else (_head_at(top, until) or head)

    def written_during(rel):
        when = stamps[rel] if rel in stamps else _changed_at(os.path.join(top, rel))
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
    # One lstat per file: when it changed, and whether it is there at all (None: gone).
    for rel in differs:
        if rel not in stamps:
            stamps[rel] = _changed_at(os.path.join(top, rel))
    present = {rel: stamps[rel] is not None for rel in differs}
    picked = set()
    for rel in differs:
        # A file that is gone has no time, so a deletion counts whenever it happened.
        if rel in moved or not present[rel] or written_during(rel):
            picked.add(rel)
    for code, rel in entries:
        if code == "??" and written_during(rel):
            picked.add(rel)
    files = []
    for rel in sorted(picked)[:MAX_FILES]:
        # The status by what was there at the start and what is there now: git rm --cached or
        # reset --mixed leave a file on disk that git counts as deleted.
        in_base = rel in differs and differs[rel] != "A"
        exists = present.get(rel, True)  # not in differs: an untracked file, listed because it is there
        status = "modified" if in_base and exists else "deleted" if in_base else "added"
        stamp = stamps[rel] if rel in stamps else _changed_at(os.path.join(top, rel))
        files.append({"rel": rel, "status": status, "stamp": stamp})
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


def _states(top, start, head, status, paths) -> dict:
    branch = (git(top, "symbolic-ref", "--short", "-q", "HEAD", ok=(0, 1)) or "").strip() or None
    repo = {"top": top, "name": os.path.basename(top), "branch": branch}
    codes = dict((rel, code) for code, rel in _status_entries(status))
    rels = {path: os.path.relpath(path, top) for path in paths}
    # Ignored files are not in the status; check-ignore names those of ours that are (exit 1: none).
    loose = [rel for rel in rels.values() if rel not in codes]
    ignored = set(filter(None, (git(top, "check-ignore", "-z", "--stdin", stdin="\0".join(loose).encode() + b"\0",
                                    ok=(0, 1)) or "").split("\0"))) if loose else set()
    # The newest commit during the chat that touched each file (log lists newest first).
    commits = {}
    base = _head_at(top, start) if head and start else None
    if head:
        log = git(top, "log", "-n", "500", "--format=%x00%H%x09%s", "--name-only", "-z",
                  f"{base}..HEAD" if base else "HEAD") if base != head else ""
        current = None
        for part in (log or "").split("\0"):
            part = part.strip("\n")
            if "\t" in part and len(part.split("\t", 1)[0]) == 40:
                sha, subject = part.split("\t", 1)
                current = {"sha": sha[:9], "subject": subject}
            elif part and current:
                commits.setdefault(part, current)
    out = {}
    for path, rel in rels.items():
        code = codes.get(rel)
        if code == "??":
            state = "untracked"
        elif rel in ignored:
            state = "ignored"
        elif code:
            staged, unstaged = code[0] not in " ?", code[1] not in " ?"
            state = "partly" if staged and unstaged else "staged" if staged else "unstaged"
        else:
            state = "committed"
        out[path] = {"repo": repo, "rel": rel, "state": state, "commit": commits.get(rel) if state == "committed" else None}
    return out
