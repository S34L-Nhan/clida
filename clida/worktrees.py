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
import unicodedata

from . import STATE_DIR, storage
from .gitrepo import git
from .settings import tr

WORKTREES_FILE = STATE_DIR / "worktrees.json"
BRANCH_PREFIX = "clida/"
# What a checkout is in the middle of: CLIDA's merge must neither start on top of it nor abort it.
_IN_PROGRESS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")


class WorktreeError(Exception):
    pass


def _slug(text: str, fallback: str) -> str:
    """A branch and folder name from a title: "Größe ändern" -> "groesse-aendern"."""
    text = (text or "").lower()
    for umlaut, spelled in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(umlaut, spelled)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()  # é -> e
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-")
    return slug or fallback


def _run(cwd, *args, timeout=30, ok=(0,)):
    """git's output; raises with git's own message when it fails."""
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise WorktreeError(f"git {args[0]}: {e}")
    if out.returncode not in ok:
        lines = (out.stderr or out.stdout).decode("utf-8", "replace").strip().splitlines()
        message = "\n".join(line for line in lines if not line.startswith("Preparing worktree"))
        raise WorktreeError(message or f"git {args[0]} failed ({out.returncode})")
    return out.stdout.decode("utf-8", "replace")


def _main_checkout(cwd: str):
    """The repository's main worktree, also when cwd is in a linked one: git commands about the
    chat's worktree run there, and its folder goes next to it."""
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


def _in_progress(checkout: str):
    """What the checkout is in the middle of (a merge, rebase, cherry-pick, revert), or None."""
    for name in _IN_PROGRESS:
        where = (git(checkout, "rev-parse", "--git-path", name) or "").strip()
        if where and os.path.exists(os.path.join(checkout, where)):
            return name
    return None


def _unmerged(where: str, branch: str, head: bool):
    """Commits no other branch has: what removing the worktree and branch would lose. head: the
    worktree's HEAD too (run in the worktree), where commits on a detached HEAD or another branch
    would be lost along with it. None: unknown."""
    tips = (["HEAD"] if head else []) + [f"refs/heads/{branch}"]
    # --exclude before --branches names the branch without refs/heads/ (see git rev-parse).
    count = git(where, "rev-list", "--count", *tips, "--not", f"--exclude={branch}", "--branches", timeout=5)
    return int(count) if count and count.strip().isdigit() else None


class Worktrees:
    def __init__(self):
        self._lock = threading.Lock()
        # One create at a time, so two never pick the same name; apart from _lock, as git may take
        # a while to check a large repository out, and the window asks for the others meanwhile.
        self._creating = threading.Lock()
        # session id -> {"repo", "path", "branch", "base", "created"}
        self._data = storage.load(WORKTREES_FILE) or {}

    def get(self, session_id: str):
        with self._lock:
            entry = self._data.get(session_id)
            return dict(entry) if entry else None

    def all(self) -> dict:
        """session id -> its record, for the sidebar and for chats that went on under a new id."""
        with self._lock:
            return {sid: dict(e) for sid, e in self._data.items()}

    def key_for(self, session_id: str, cwd):
        """The record a chat works in: its own, or, after /clear or /resume in the CLI gave the
        terminal another session id, the one whose folder the chat is in."""
        records = self.all()
        if session_id in records:
            return session_id
        if cwd:
            real = os.path.realpath(cwd) + "/"
            for sid, entry in records.items():
                if real.startswith(os.path.realpath(entry["path"]) + "/"):
                    return sid
        return None

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
        # A submodule's worktrees go beside the superproject (beside the submodule would be inside
        # it), named after the submodule; git still works in the submodule's own repository.
        superproject = (git(top, "rev-parse", "--show-superproject-working-tree") or "").strip()
        beside = superproject or main
        home = os.path.join(os.path.dirname(beside), os.path.basename(beside) + ".worktrees")
        slug = _slug(name, session_id[:8])
        if superproject:
            slug = f"{_slug(os.path.basename(top), 'sub')}-{slug}"
        with self._creating:
            # Nor a folder another chat's record names: deleted by hand, it would be found for both.
            recorded = {e["path"] for e in self.all().values()}
            for n in range(1, 100):
                candidate = slug if n == 1 else f"{slug}-{n}"
                branch = BRANCH_PREFIX + candidate
                path = os.path.join(home, candidate)
                taken = git(top, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", ok=(0, 1))
                if path not in recorded and not os.path.exists(path) and taken is not None and not taken.strip():
                    break
            else:
                raise WorktreeError(tr("Kein freier Name für den Worktree.", "No free name for the worktree."))
            try:
                os.makedirs(home, exist_ok=True)
            except OSError as e:
                raise WorktreeError(f"{home}: {e.strerror}")
            try:
                _run(top, "worktree", "add", "-b", branch, path, head, timeout=120)
            except WorktreeError:
                # A failing post-checkout hook (git-lfs missing, say) or the timeout can leave the
                # folder and the branch behind; nothing would list them, so they go again.
                git(top, "worktree", "remove", "--force", path, timeout=60)  # also when the folder is gone
                git(top, "branch", "-D", branch)
                try:
                    os.rmdir(home)  # if this was to be its first worktree
                except OSError:
                    pass
                raise
            with self._lock:
                self._data[session_id] = {"repo": main, "path": path, "branch": branch, "base": base,
                                          "created": time.time()}
                self._save()
        # Both resolved: git's top has symlinks resolved (~/work may be /mnt/d/work).
        inner = os.path.normpath(os.path.join(path, os.path.relpath(os.path.realpath(cwd), os.path.realpath(top))))
        return inner if inner.startswith(path) and os.path.isdir(inner) else path

    def status(self, session_id: str):
        """Where the chat's worktree stands: uncommitted files, commits ahead of its base and
        behind it, and commits that no other branch has (lost if it is removed)."""
        entry = self.get(session_id)
        if entry is None:
            return None
        path, branch, base = entry["path"], entry["branch"], entry["base"]
        out = {"path": path, "branch": branch, "base": base, "exists": os.path.isdir(path),
               "dirty": None, "ahead": None, "behind": None, "unmerged": None, "base_missing": False, "head": None}
        if not out["exists"]:
            # Gone by hand: the branch may still hold commits, which removing would delete.
            out["unmerged"] = _unmerged(entry["repo"], branch, head=False)
            return out
        status = git(path, "status", "--porcelain=v1", timeout=5)
        out["dirty"] = None if status is None else len(status.splitlines())
        out["unmerged"] = _unmerged(path, branch, head=True)
        # What is checked out there, if not the chat's branch (a checkout or rebase in it): "" detached.
        current = git(path, "symbolic-ref", "--short", "-q", "HEAD", ok=(0, 1))
        if current is not None and current.strip() != branch:
            out["head"] = current.strip()
        if base:
            out["base_missing"] = not (git(path, "rev-parse", "--verify", "-q", f"refs/heads/{base}", ok=(0, 1)) or "").strip()
            counts = (git(path, "rev-list", "--left-right", "--count", f"refs/heads/{base}...refs/heads/{branch}",
                          timeout=5) or "").split()
            if len(counts) == 2:
                out["behind"], out["ahead"] = int(counts[0]), int(counts[1])
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
        if state["head"] is not None:
            raise WorktreeError(tr(f"Im Worktree ist nicht mehr {branch} ausgecheckt; bitte zurückwechseln oder selbst mergen.",
                                   f"{branch} is no longer checked out in the worktree; please switch back or merge it yourself."))
        if state["base_missing"]:
            raise WorktreeError(tr(f"Den Branch {base} gibt es nicht mehr; bitte selbst mergen.",
                                   f"The branch {base} no longer exists; please merge it yourself."))
        n = state["dirty"]
        if n is None:
            raise WorktreeError(tr("Git antwortet nicht auf den Status des Worktrees; bitte gleich noch einmal versuchen.",
                                   "git does not report the worktree's status; please try again in a moment."))
        if n:
            raise WorktreeError(tr(f"Im Worktree {'ist 1 Datei' if n == 1 else f'sind {n} Dateien'} nicht committet. "
                                   "Bitte erst committen (oder Claude darum bitten).",
                                   f"{'1 file' if n == 1 else f'{n} files'} in the worktree {'is' if n == 1 else 'are'} "
                                   "not committed. Please commit first (or ask Claude to)."))
        if state["ahead"] is None:
            raise WorktreeError(tr("Git konnte die Branches nicht vergleichen; bitte gleich noch einmal versuchen.",
                                   "git could not compare the branches; please try again in a moment."))
        if not state["ahead"]:
            raise WorktreeError(tr(f"Nichts zu mergen: {branch} hat keine Commits, die {base} fehlen.",
                                   f"Nothing to merge: {branch} has no commits that {base} lacks."))
        target = _checked_out(entry["repo"]).get(base)
        if not target:
            raise WorktreeError(tr(f"{base} ist nirgends ausgecheckt; bitte im Repository auschecken und erneut versuchen.",
                                   f"{base} is not checked out anywhere; please check it out in the repository and try again."))
        busy = _in_progress(target)
        if busy:
            # Never on top of the user's own merge or rebase: aborting ours would take theirs along.
            raise WorktreeError(tr(f"In {target} läuft gerade etwas ({busy}); bitte erst abschließen.",
                                   f"Something is in progress in {target} ({busy}); please finish it first."))
        try:
            _run(target, "merge", "--no-edit", f"refs/heads/{branch}", timeout=120)
        except WorktreeError as e:
            conflicts = (git(target, "diff", "--name-only", "--diff-filter=U") or "").split()
            if _in_progress(target) == "MERGE_HEAD":
                git(target, "merge", "--abort")  # ours: nothing was in progress before it
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
            # Only this one: a bare prune would also drop worktrees on a drive that is not mounted.
            git(entry["repo"], "worktree", "remove", "--force", entry["path"], timeout=60)
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
