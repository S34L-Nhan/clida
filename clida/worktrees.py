"""A git worktree of its own per chat (~/.clida/worktrees.json): parallel chats on one repository
never write into each other's files, and the changes view shows exactly one chat's branch.

CLIDA makes the worktree next to the repository, <repo>.worktrees/<name>, on a new branch
clida/<name> from where the chat's folder stood. Merging goes into the branch the chat started
from, in the worktree that has it checked out (usually the repository itself); removing takes
the folder and the branch.
"""

import os
import re
import subprocess
import threading
import time

from . import STATE_DIR, storage
from .gitrepo import git
from .settings import tr

WORKTREES_FILE = STATE_DIR / "worktrees.json"
BRANCH_PREFIX = "clida/"


class WorktreeError(Exception):
    pass


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40].strip("-")
    return slug or fallback


def _run(cwd, *args, timeout=30, ok=(0,)):
    """git's output; raises with git's own message when it fails."""
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise WorktreeError(f"git {args[0]}: {e}")
    if out.returncode not in ok:
        message = (out.stderr or out.stdout).decode("utf-8", "replace").strip()
        raise WorktreeError(message or f"git {args[0]} failed ({out.returncode})")
    return out.stdout.decode("utf-8", "replace")


def _main_checkout(cwd: str):
    """The repository's main worktree, also when cwd is in a linked one: worktrees go next to it."""
    common = (git(cwd, "rev-parse", "--git-common-dir") or "").strip()
    if not common:
        return None
    common = os.path.abspath(os.path.join(cwd, common))
    return os.path.dirname(common) if os.path.basename(common) == ".git" else None


def _checked_out(top: str) -> dict:
    """branch -> the worktree that has it checked out, from `git worktree list`."""
    out, path = {}, None
    for line in (git(top, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and path:
            out[line[len("branch refs/heads/"):]] = path
    return out


class Worktrees:
    def __init__(self):
        self._lock = threading.Lock()
        # session id -> {"repo", "path", "branch", "base", "created"}
        self._data = storage.load(WORKTREES_FILE) or {}

    def get(self, session_id: str):
        with self._lock:
            entry = self._data.get(session_id)
            return dict(entry) if entry else None

    def paths(self) -> list:
        with self._lock:
            return [e["path"] for e in self._data.values()]

    def branches(self) -> dict:
        """session id -> its branch, for the sidebar."""
        with self._lock:
            return {sid: {"branch": e["branch"], "repo": os.path.basename(e["repo"])} for sid, e in self._data.items()}

    def _save(self):
        storage.save(WORKTREES_FILE, self._data)

    def create(self, session_id: str, cwd: str, name: str) -> str:
        """Make the chat's worktree from where cwd's repository stands; returns the folder the chat
        starts in (the same place inside the new worktree as cwd is inside its repository)."""
        top = (git(cwd, "rev-parse", "--show-toplevel") or "").strip()
        if not top:
            raise WorktreeError(tr("Der Ordner liegt in keinem Git-Repository.", "The folder is not in a git repository."))
        head = (git(top, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1)) or "").strip()
        if not head:
            raise WorktreeError(tr("Das Repository hat noch keinen Commit.", "The repository has no commit yet."))
        base = (git(top, "symbolic-ref", "--short", "-q", "HEAD", ok=(0, 1)) or "").strip() or None
        main = _main_checkout(top) or top
        home = os.path.join(os.path.dirname(main), os.path.basename(main) + ".worktrees")
        slug = _slug(name, session_id[:8])
        with self._lock:
            for n in range(1, 100):
                candidate = slug if n == 1 else f"{slug}-{n}"
                branch = BRANCH_PREFIX + candidate
                path = os.path.join(home, candidate)
                taken = git(top, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", ok=(0, 1))
                if not os.path.exists(path) and taken is not None and not taken.strip():
                    break
            else:
                raise WorktreeError(tr("Kein freier Name für den Worktree.", "No free name for the worktree."))
            os.makedirs(home, exist_ok=True)
            _run(top, "worktree", "add", "-b", branch, path, head, timeout=120)
            self._data[session_id] = {"repo": main, "path": path, "branch": branch, "base": base,
                                      "created": time.time()}
            self._save()
        inner = os.path.normpath(os.path.join(path, os.path.relpath(cwd, top)))
        return inner if os.path.isdir(inner) else path

    def status(self, session_id: str):
        """Where the chat's worktree stands: uncommitted files, commits ahead of its base, merged."""
        entry = self.get(session_id)
        if entry is None:
            return None
        path, branch, base = entry["path"], entry["branch"], entry["base"]
        out = {"path": path, "branch": branch, "base": base, "exists": os.path.isdir(path),
               "dirty": None, "ahead": None, "behind": None, "merged": None}
        if not out["exists"]:
            return out
        status = git(path, "status", "--porcelain=v1", timeout=5)
        out["dirty"] = None if status is None else len(status.splitlines())
        if base:
            counts = (git(path, "rev-list", "--left-right", "--count", f"{base}...{branch}", timeout=5) or "").split()
            if len(counts) == 2:
                out["behind"], out["ahead"] = int(counts[0]), int(counts[1])
                out["merged"] = out["ahead"] == 0
        return out

    def merge(self, session_id: str) -> dict:
        """Merge the chat's branch into the branch it started from, where that is checked out."""
        entry = self.get(session_id)
        if entry is None:
            raise WorktreeError(tr("Dieser Chat hat keinen eigenen Worktree.", "This chat has no worktree of its own."))
        state = self.status(session_id)
        base, branch = entry["base"], entry["branch"]
        if not state["exists"]:
            raise WorktreeError(tr("Der Worktree existiert nicht mehr.", "The worktree no longer exists."))
        if not base:
            raise WorktreeError(tr("Der Chat startete ohne Branch (detached HEAD); bitte selbst mergen.",
                                   "The chat started without a branch (detached HEAD); please merge it yourself."))
        n = state["dirty"]
        if n:
            raise WorktreeError(tr(f"Im Worktree {'ist 1 Datei' if n == 1 else f'sind {n} Dateien'} nicht committet. "
                                   "Bitte erst committen (oder Claude darum bitten).",
                                   f"{'1 file' if n == 1 else f'{n} files'} in the worktree {'is' if n == 1 else 'are'} "
                                   "not committed. Please commit first (or ask Claude to)."))
        if not state["ahead"]:
            raise WorktreeError(tr(f"Nichts zu mergen: {branch} hat keine Commits, die {base} fehlen.",
                                   f"Nothing to merge: {branch} has no commits that {base} lacks."))
        target = _checked_out(entry["repo"]).get(base)
        if not target:
            raise WorktreeError(tr(f"{base} ist nirgends ausgecheckt; bitte im Repository auschecken und erneut versuchen.",
                                   f"{base} is not checked out anywhere; please check it out in the repository and try again."))
        try:
            _run(target, "merge", "--no-edit", branch, timeout=120)
        except WorktreeError as e:
            conflicts = (git(target, "diff", "--name-only", "--diff-filter=U") or "").split()
            if git(target, "rev-parse", "-q", "--verify", "MERGE_HEAD", ok=(0, 1)):
                git(target, "merge", "--abort")
            if conflicts:
                raise WorktreeError(tr(f"Merge-Konflikt in {', '.join(conflicts[:5])}; der Merge wurde abgebrochen. "
                                       f"Tipp: Claude bitten, {base} in den Worktree zu mergen und die Konflikte zu lösen.",
                                       f"Merge conflict in {', '.join(conflicts[:5])}; the merge was aborted. "
                                       f"Tip: ask Claude to merge {base} into the worktree and resolve the conflicts."))
            raise WorktreeError(tr("Merge fehlgeschlagen: ", "Merge failed: ") + str(e))
        return {"merged": True, "into": base, "where": target}

    def remove(self, session_id: str):
        """Delete the worktree folder and its branch, uncommitted and unmerged work included."""
        entry = self.get(session_id)
        if entry is None:
            raise WorktreeError(tr("Dieser Chat hat keinen eigenen Worktree.", "This chat has no worktree of its own."))
        if os.path.isdir(entry["path"]):
            _run(entry["repo"], "worktree", "remove", "--force", entry["path"], timeout=120)
        else:
            git(entry["repo"], "worktree", "prune")
        git(entry["repo"], "branch", "-D", entry["branch"])  # may be gone already
        try:
            os.rmdir(os.path.dirname(entry["path"]))  # <repo>.worktrees, once its last worktree is gone
        except OSError:
            pass
        with self._lock:
            self._data.pop(session_id, None)
            self._save()

    def forget(self, session_id: str):
        with self._lock:
            if self._data.pop(session_id, None) is not None:
                self._save()
