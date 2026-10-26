"""A git worktree of its own per chat (~/.clida/worktrees.json): parallel chats on one repository
never write into each other's files, and the changes view shows exactly one chat's branch.

CLIDA makes the worktree next to the repository, <repo>.worktrees/<name>, on a new branch
clida/<name> from where the chat's folder stood. Merging goes into the branch the chat started
from, in the worktree that has it checked out (usually the repository itself); removing takes
the folder and the branch.
"""

import os
import re
import shutil
import signal
import subprocess
import threading
import time
import unicodedata

from . import STATE_DIR, storage
from .gitrepo import git
from .settings import tr

WORKTREES_FILE = STATE_DIR / "worktrees.json"
BRANCH_PREFIX = "clida/"
EXCLUDE_LINE = "**/.claude/worktrees/"  # in info/exclude, which stays local, unlike .gitignore
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
    """git's output; raises with git's own message when it fails. On a timeout the whole process
    group goes: git worktree add runs a checkout of its own, which would go on otherwise."""
    try:
        proc = subprocess.Popen(["git", "-C", cwd, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except OSError as e:
        raise WorktreeError(tr(f"git {args[0]} ließ sich nicht starten: {e}", f"git {args[0]} did not start: {e}"))
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise WorktreeError(tr(f"git {args[0]} brauchte länger als {timeout} s und wurde abgebrochen.",
                               f"git {args[0]} took longer than {timeout} s and was stopped."))
    out = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
    if out.returncode not in ok:
        lines = (out.stderr or out.stdout).decode("utf-8", "replace").strip().splitlines()
        message = "\n".join(line for line in lines if not line.startswith("Preparing worktree"))
        raise WorktreeError(message or tr(f"git {args[0]} schlug fehl ({out.returncode})",
                                          f"git {args[0]} failed ({out.returncode})"))
    return out.stdout.decode("utf-8", "replace")


def _main_checkout(cwd: str):
    """The repository's main worktree, also when cwd is in a linked one: git commands about the
    chat's worktree run there, and its folder goes next to it."""
    common = (git(cwd, "rev-parse", "--git-common-dir") or "").rstrip("\n")  # a path may end in a space
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


def _branch_name(ref):
    """main from git's "refs/heads/main" (symbolic-ref without --short); None without a branch."""
    ref = (ref or "").strip()
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None


def _unmerged(where: str, branch: str, head: bool, own: bool = True):
    """Commits no other branch has: what removing the worktree, and with own its branch, would
    lose. head: the worktree's HEAD too (run in the worktree), where commits on a detached HEAD or
    another branch would be lost along with it. None: unknown."""
    tips = (["HEAD"] if head else []) + ([f"refs/heads/{branch}"] if own else [])
    if not tips:
        return 0  # the folder is gone and the branch stays
    # --exclude before --branches names the branch without refs/heads/ (see git rev-parse).
    exclude = [f"--exclude={branch}"] if own else []
    count = git(where, "rev-list", "--count", *tips, "--not", *exclude, "--branches", timeout=5)
    return int(count) if count and count.strip().isdigit() else None


def _exists(top: str, ref: str) -> bool:
    return bool((git(top, "rev-parse", "--verify", "-q", ref, ok=(0, 1)) or "").strip())


def _refs(top: str, prefix: str) -> list:
    """The branch names under refs/heads/ or refs/remotes/, newest commit first, without a
    remote's HEAD."""
    out = []
    # A ref name has no spaces, so the space parts it from its symref.
    for line in (git(top, "for-each-ref", "--sort=-committerdate", "--format=%(refname) %(symref)", prefix) or "").splitlines():
        ref, _, symref = line.partition(" ")
        if ref.startswith(prefix) and not symref:
            out.append(ref[len(prefix):])
    return out


def _default_base(top: str):
    """What a new branch starts from unless the chat says otherwise: the remote's default branch
    (origin/HEAD), as the local branch of that name unless that only lags behind it (a local
    development a month behind would start the work a month back). Without origin/HEAD: the branch
    the folder has checked out, None on a detached HEAD."""
    remote = (git(top, "symbolic-ref", "-q", "refs/remotes/origin/HEAD", ok=(0, 1)) or "").strip()
    if not remote.startswith("refs/remotes/origin/"):
        return _branch_name(git(top, "symbolic-ref", "-q", "HEAD", ok=(0, 1)))
    local = remote[len("refs/remotes/origin/"):]
    # No local branch of that name, or git failing, gives no counts: then the remote one.
    counts = (git(top, "rev-list", "--left-right", "--count", f"refs/heads/{local}...{remote}", timeout=5) or "").split()
    if len(counts) == 2 and not (counts[0] == "0" and counts[1] != "0"):
        return local
    return remote[len("refs/remotes/"):]


def _base_ref(top: str, base: str) -> str:
    """The full ref of a base given as development or origin/development."""
    for ref in (f"refs/heads/{base}", f"refs/remotes/{base}"):
        if _exists(top, ref):
            return ref
    raise WorktreeError(tr(f"Den Branch {base} gibt es nicht.", f"There is no branch {base}."))


def _take_branch(top: str, branch: str):
    """How git worktree add checks a branch there is already out: (options, start point, whether
    that makes the local branch). A branch only a remote has gets a local one that tracks it."""
    holder = _checked_out(top).get(branch)
    if holder:
        raise WorktreeError(tr(f"{branch} ist schon in {holder} ausgecheckt; Git gibt einen Branch nur einem Worktree.",
                               f"{branch} is checked out in {holder} already; git gives a branch to one worktree only."))
    if _exists(top, f"refs/heads/{branch}"):
        return [], [branch], False
    remotes = [r for r in (git(top, "remote") or "").split() if _exists(top, f"refs/remotes/{r}/{branch}")]
    if len(remotes) == 1:
        return ["--track", "-b", branch], [f"{remotes[0]}/{branch}"], True
    if remotes:
        raise WorktreeError(tr(f"{branch} gibt es auf mehreren Remotes ({', '.join(remotes)}); bitte den lokalen Branch selbst anlegen.",
                               f"{branch} is on several remotes ({', '.join(remotes)}); please make the local branch yourself."))
    raise WorktreeError(tr(f"Den Branch {branch} gibt es weder lokal noch auf einem Remote. Ist er neu, bitte erst git fetch.",
                           f"There is no branch {branch}, neither local nor on a remote. If it is new, please git fetch first."))


def _exclude(main: str, home: str):
    """Keep the worktrees out of the repository's own git status (and git add), unless they are
    ignored already."""
    if git(main, "check-ignore", home, ok=(0, 1)) != "":  # its name if ignored, None if git failed
        return
    where = (git(main, "rev-parse", "--git-path", "info/exclude") or "").rstrip("\n")
    if not where:
        raise WorktreeError(tr("Git nennt die exclude-Datei des Repositorys nicht.",
                               "git does not name the repository's exclude file."))
    where = os.path.join(main, where)  # relative to main, or absolute in a submodule
    os.makedirs(os.path.dirname(where), exist_ok=True)
    with open(where, "a+", encoding="utf-8") as f:
        f.seek(0)
        text = f.read()
        f.write(("" if not text or text.endswith("\n") else "\n") + EXCLUDE_LINE + "\n")


class Worktrees:
    def __init__(self):
        self._lock = threading.Lock()
        # One create at a time, so two never pick the same name; apart from _lock, as git may take
        # a while to check a large repository out, and the window asks for the others meanwhile.
        self._creating = threading.Lock()
        self._merging = threading.Lock()  # one merge at a time: a failing one must not abort another's
        # session id -> {"repo", "path", "branch", "base", "base_ref", "own_branch", "created", "sessions"};
        # "base_ref": the base's full ref, refs/heads/… or refs/remotes/…; "own_branch": CLIDA made the
        # branch (and deletes it with the worktree); "sessions": the ids the chat went on under
        # (/clear, /resume in the CLI) and its forks, which work there too.
        self._data = storage.load(WORKTREES_FILE) or {}

    def get(self, session_id: str):
        with self._lock:
            entry = self._data.get(session_id)
            return dict(entry) if entry else None

    def all(self) -> dict:
        """session id -> its record, for the sidebar and for chats that went on under a new id."""
        with self._lock:
            return {sid: dict(e) for sid, e in self._data.items()}

    def key_for(self, session_id: str):
        """The record a chat works in: its own, or the one of the chat it went on from or was forked
        from. By what was recorded, not by folder: a folder name is given out again once free."""
        with self._lock:
            return self._key(session_id)

    def _key(self, session_id):
        if session_id in self._data:
            return session_id
        return next((key for key, e in self._data.items() if session_id in e.get("sessions", ())), None)

    def follow(self, session_id: str, new_id: str):
        """new_id works in session_id's worktree from now on: the CLI went on under it, or a fork."""
        with self._lock:
            key = self._key(session_id)
            if key is None or new_id == key or self._key(new_id) is not None:
                return
            self._data[key].setdefault("sessions", []).append(new_id)
            self._save()

    def let_go(self, session_id: str, listed=lambda sid: True) -> str:
        """The chat is deleted: another of the record's chats takes it over, one that listed()
        says has a history if there is one. "kept" if one did, "dropped" if it was only one of
        them, "own" if it holds the record alone, "" if none."""
        with self._lock:
            key = self._key(session_id)
            if key is None:
                return ""
            others = self._data[key].get("sessions", [])
            if key != session_id:
                others.remove(session_id)
                self._save()
                return "dropped"
            if not others:
                return "own"
            heir = next((sid for sid in others if listed(sid)), others[0])
            entry = self._data.pop(key)
            self._data[heir] = {**entry, "sessions": [sid for sid in others if sid != heir]}
            self._save()
            return "kept"

    def _save(self):
        storage.save(WORKTREES_FILE, self._data)

    def branches(self, cwd: str):
        """For the new-chat dialog: the local and remote branches of cwd's repository, newest first,
        the base a new branch starts from by default, and the branches checked out already (git
        gives a branch to one worktree only). None outside a repository."""
        top = (git(cwd, "rev-parse", "--show-toplevel") or "").rstrip("\n")
        if not top:
            return None
        return {"default": _default_base(top), "local": _refs(top, "refs/heads/"),
                "remote": _refs(top, "refs/remotes/"), "checked_out": sorted(_checked_out(top))}

    def create(self, session_id: str, cwd: str, name: str, used=(), base=None, branch=None) -> str:
        """Make the chat's worktree in cwd's repository; returns the folder the chat starts in (the
        same place inside the new worktree as cwd is inside its repository).

        base: the local or remote branch a new branch clida/<name> starts from; without it, where
        the repository stands. branch: a branch there is already, checked out instead of a new one
        (base is then not used); CLIDA never deletes it.

        used: the folders chats have worked in. A folder in one of them is not given out again,
        even with its worktree long removed: resuming that chat, or restoring its files, would
        work in the new chat's worktree."""
        if not shutil.which("git"):
            raise WorktreeError(tr("git ist nicht installiert.", "git is not installed."))
        top = (git(cwd, "rev-parse", "--show-toplevel") or "").rstrip("\n")  # a folder may end in a space
        if not top:
            raise WorktreeError(tr("Der Ordner liegt in keinem Git-Repository.", "The folder is not in a git repository."))
        head = (git(top, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1)) or "").strip()
        if not head:
            raise WorktreeError(tr("Das Repository hat noch keinen Commit.", "The repository has no commit yet."))
        if branch:
            options, start, made = _take_branch(top, branch)
            base = base_ref = None
        elif base:
            base_ref = _base_ref(top, base)
            start, made = [base_ref], True
        else:
            # Not --short: with a tag of the same name it answers "heads/main".
            base = _branch_name(git(top, "symbolic-ref", "-q", "HEAD", ok=(0, 1)))
            base_ref, start, made = base and f"refs/heads/{base}", [head], True
        main = _main_checkout(top) or top
        # Where the CLI puts its own worktrees: inside the repository, so a container or tool that
        # mounts only the repository reaches them too. A submodule has its own.
        home = os.path.join(main, ".claude", "worktrees")
        slug = _slug(name or (branch or "").rsplit("/", 1)[-1], session_id[:8])
        with self._creating:
            # Checked here, not only by the caller: two windows can ask for one chat at once, and the
            # second record would take the first one's place.
            if self.key_for(session_id) is not None:
                raise WorktreeError(tr("Dieser Chat hat schon einen Worktree.", "This chat has a worktree already."))
            # Nor a folder another chat's record names: deleted by hand, it would be found for both.
            recorded = {e["path"] for e in self.all().values()}
            used = [u.rstrip("/") for u in used if u]
            for n in range(1, 100):
                candidate = slug if n == 1 else f"{slug}-{n}"
                new = None if branch else BRANCH_PREFIX + candidate
                path = os.path.join(home, candidate)
                worked_in = any(u == path or u.startswith(path + "/") for u in used)
                taken = git(top, "rev-parse", "--verify", "-q", f"refs/heads/{new}", ok=(0, 1)) if new else ""
                if (path not in recorded and not worked_in and not os.path.exists(path)
                        and taken is not None and not taken.strip()):
                    break
            else:
                raise WorktreeError(tr("Kein freier Name für den Worktree.", "No free name for the worktree."))
            if new:
                # No upstream: from origin/development it would be that, and git push would refuse.
                options = ["--no-track", "-b", new]
            made_dirs = [d for d in (os.path.dirname(home), home) if not os.path.isdir(d)]
            try:
                os.makedirs(home, exist_ok=True)
                _exclude(main, home)
                _run(top, "worktree", "add", *options, path, *start, timeout=120)
            except (OSError, WorktreeError) as failed:
                # A failing post-checkout hook (git-lfs missing, say) or the timeout can leave the
                # folder and the branch behind; nothing would list them, so they go again.
                # Twice --force: an interrupted add leaves the worktree locked ("initializing").
                git(top, "worktree", "remove", "--force", "--force", path, timeout=60)  # also when the folder is gone
                if made:
                    git(top, "branch", "-D", new or branch)
                for folder in reversed(made_dirs):  # if this was to be its first worktree
                    try:
                        os.rmdir(folder)
                    except OSError:
                        break
                if isinstance(failed, OSError):
                    failed = WorktreeError(f"{failed.filename}: {failed.strerror}")
                if os.path.exists(path):  # the cleanup failed too (a slow drive): say what is left
                    raise WorktreeError(f"{failed} " + tr(f"Übrig blieb der Ordner {path}; bitte selbst löschen.",
                                                          f"The folder {path} was left behind; please delete it."))
                raise failed
            with self._lock:
                self._data[session_id] = {"repo": main, "path": path, "branch": new or branch, "base": base,
                                          "base_ref": base_ref, "own_branch": not branch, "created": time.time()}
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
        # Records from before base_ref and own_branch: a local base, and a branch CLIDA made.
        base_ref = entry.get("base_ref") or (base and f"refs/heads/{base}")
        own = entry.get("own_branch", True)
        out = {"path": path, "branch": branch, "base": base, "exists": os.path.isdir(path), "own_branch": own,
               "base_local": bool(base_ref and base_ref.startswith("refs/heads/")),
               "dirty": None, "ahead": None, "behind": None, "unmerged": None, "base_missing": False, "head": None}
        if not out["exists"]:
            # Gone by hand: the branch may still hold commits, which removing would delete.
            out["unmerged"] = _unmerged(entry["repo"], branch, head=False, own=own)
            return out
        status = git(path, "status", "--porcelain=v1", timeout=5)
        out["dirty"] = None if status is None else len(status.splitlines())
        out["unmerged"] = _unmerged(path, branch, head=True, own=own)
        # What is checked out there, if not the chat's branch (a checkout or rebase in it): "" detached.
        current = git(path, "symbolic-ref", "-q", "HEAD", ok=(0, 1))
        if current is not None and _branch_name(current) != branch:
            out["head"] = _branch_name(current) or ""
        if base_ref:
            out["base_missing"] = not _exists(path, base_ref)
            counts = (git(path, "rev-list", "--left-right", "--count", f"{base_ref}...refs/heads/{branch}",
                          timeout=5) or "").split()
            if len(counts) == 2:
                out["behind"], out["ahead"] = int(counts[0]), int(counts[1])
        return out

    def merge(self, session_id: str) -> dict:
        """Merge the chat's branch into the branch it started from, where that is checked out."""
        with self._merging:
            return self._merge(session_id)

    def _merge(self, session_id: str) -> dict:
        entry = self.get(session_id)
        state = self.status(session_id)
        if entry is None or state is None:  # removed meanwhile, too
            raise WorktreeError(tr("Dieser Chat hat keinen eigenen Worktree.", "This chat has no worktree of its own."))
        base, branch = entry["base"], entry["branch"]
        if not state["exists"]:
            raise WorktreeError(tr("Der Worktree existiert nicht mehr.", "The worktree no longer exists."))
        if not state["own_branch"]:
            raise WorktreeError(tr(f"Der Chat arbeitet auf dem bestehenden Branch {branch}; den mergt CLIDA nicht. "
                                   "Bitte pushen und einen Merge Request stellen.",
                                   f"The chat works on the existing branch {branch}, which CLIDA does not merge. "
                                   "Please push it and open a merge request."))
        if not base:
            raise WorktreeError(tr("Der Chat startete ohne Branch (detached HEAD); bitte selbst mergen.",
                                   "The chat started without a branch (detached HEAD); please merge it yourself."))
        if not state["base_local"]:
            raise WorktreeError(tr(f"{base} ist ein Remote-Branch; CLIDA mergt nur in lokale. "
                                   "Bitte pushen und einen Merge Request stellen.",
                                   f"{base} is a remote branch; CLIDA merges into local ones only. "
                                   "Please push and open a merge request."))
        if state["head"] is not None:
            raise WorktreeError(tr(f"Im Worktree ist nicht mehr {branch} ausgecheckt; bitte zurückwechseln oder selbst mergen.",
                                   f"{branch} is no longer checked out in the worktree; please switch back or merge it yourself."))
        if state["base_missing"]:
            raise WorktreeError(tr(f"Den Branch {base} gibt es nicht mehr; bitte selbst mergen.",
                                   f"The branch {base} no longer exists; please merge it yourself."))
        # Untracked files do not count here: the merge takes the branch, not the folder.
        tracked = git(entry["path"], "status", "--porcelain=v1", "--untracked-files=no", timeout=5)
        n = None if tracked is None else len(tracked.splitlines())
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
        """Delete the worktree folder, uncommitted work included, and the branch if CLIDA made it,
        unmerged work included."""
        entry = self.get(session_id)
        if entry is None:
            raise WorktreeError(tr("Dieser Chat hat keinen eigenen Worktree.", "This chat has no worktree of its own."))
        if os.path.isdir(entry["path"]):
            _run(entry["repo"], "worktree", "remove", "--force", entry["path"], timeout=120)
        else:
            # Only this one: a bare prune would also drop worktrees on a drive that is not mounted.
            git(entry["repo"], "worktree", "remove", "--force", entry["path"], timeout=60)
        if entry.get("own_branch", True):
            git(entry["repo"], "branch", "-D", entry["branch"])  # may be gone already
        try:
            os.rmdir(os.path.dirname(entry["path"]))  # .claude/worktrees (<repo>.worktrees before), once its last worktree is gone
        except OSError:
            pass
        with self._lock:
            self._data.pop(session_id, None)
            self._save()

    def forget(self, session_id: str):
        with self._lock:
            if self._data.pop(session_id, None) is not None:
                self._save()
