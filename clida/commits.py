"""Commit the files picked in the changes view, and push the branch.

A commit takes the picked files as they are on disk now, staged or not; whatever else is staged
stays staged and out of it (git commit --only). A push goes to the branch of the same name on the
remote git would push to, never to an upstream of another name (a branch made from
origin/development tracks that). A branch without an upstream gets that one. Never by force: a
remote that has commits the branch lacks rejects the push, with git's message. Into the remote's
default branch only when asked for: the window asks first.
"""

import os

from .gitrepo import GitError, git, run
from .settings import tr

COMMIT_TIMEOUT = 120  # the repository's hooks (lint-staged, tests) take their time
PUSH_TIMEOUT = 120
USUAL_DEFAULTS = ("main", "master")  # a remote's default branch when git does not know it


class DefaultBranchError(GitError):
    pass


def _env() -> dict:
    """No prompt for a login: the server has no terminal to ask in, so git fails at once instead."""
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def _literal(rels) -> list:
    """Paths as they are, a file named *.php being that file, not a pattern. Per path, not with
    GIT_LITERAL_PATHSPECS: the repository's hooks would inherit that, and their patterns match nothing."""
    return [f":(literal){rel}" for rel in rels]


def commit(top: str, rels: list, message: str) -> dict:
    """Commit the files rels (paths in top's repository) with message: {"sha", "subject"}."""
    env = _env()
    # A file git does not know yet is added first, and taken out again if the commit fails. One
    # that is neither in the index nor on disk is a staged deletion: the commit takes it as it is.
    indexed = set(run(top, "ls-files", "-z", "--", *_literal(rels), env=env).split("\0"))
    new = [rel for rel in rels if rel not in indexed and os.path.lexists(os.path.join(top, rel))]
    if new:
        run(top, "add", "--", *_literal(new), env=env)
    try:
        run(top, "commit", "--only", "-m", message, "--", *_literal(rels), timeout=COMMIT_TIMEOUT, env=env)
    except GitError:
        if new:
            try:
                run(top, "rm", "--cached", "-q", "--", *_literal(new), env=env)  # works without a commit too, unlike reset
            except GitError:
                pass
        raise
    sha = (git(top, "rev-parse", "HEAD") or "").strip()
    return {"sha": sha[:9], "subject": message.splitlines()[0]}


def _branch(top: str):
    ref = (git(top, "symbolic-ref", "-q", "HEAD", ok=(0, 1)) or "").strip()  # not --short: a tag may share the name
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None


def _push_remote(top: str, branch: str):
    """The remote git pushes the branch to: its pushRemote, remote.pushDefault, the remote it
    tracks, else origin, else the only one there is."""
    remotes = (git(top, "remote") or "").split()
    for key in (f"branch.{branch}.pushRemote", "remote.pushDefault", f"branch.{branch}.remote"):
        value = (git(top, "config", "--get", key, ok=(0, 1)) or "").strip()
        if value in remotes:  # not ".", the repository itself
            return value
    return "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else None


def _is_default(top: str, remote: str, branch: str) -> bool:
    """Whether branch is the remote's default branch, the one everybody works from: what
    <remote>/HEAD points to (set by git clone), else main or master (a remote added by hand)."""
    head = (git(top, "symbolic-ref", "-q", f"refs/remotes/{remote}/HEAD", ok=(0, 1)) or "").strip()
    prefix = f"refs/remotes/{remote}/"
    return head[len(prefix):] == branch if head.startswith(prefix) else branch in USUAL_DEFAULTS


def push_state(top: str):
    """Where a push of the checked-out branch goes: {"target": "origin/x", "default": the remote's
    default branch, "new": not on the remote yet, "unpushed": commits the remote lacks (None:
    unknown)}; None without a branch or a remote."""
    branch = _branch(top)
    remote = branch and _push_remote(top, branch)
    if not remote:
        return None
    out = {"target": f"{remote}/{branch}", "default": _is_default(top, remote, branch), "new": False, "unpushed": None}
    ref = f"refs/remotes/{remote}/{branch}"
    there = git(top, "rev-parse", "--verify", "-q", ref, ok=(0, 1))
    if there is None:
        return out
    # A branch new on the remote brings what no remote branch has yet.
    against = [f"^{ref}"] if there.strip() else ["--not", "--remotes"]
    count = (git(top, "rev-list", "--count", f"refs/heads/{branch}", *against) or "").strip()
    return {**out, "new": not there.strip(), "unpushed": int(count) if count.isdigit() else None}


def push(top: str, to_default: bool = False) -> dict:
    """Push the checked-out branch to the branch of the same name on its push remote: {"target"}.
    Into the remote's default branch only with to_default: the window asks first, and what it
    showed may be older than the branch checked out now."""
    branch = _branch(top)
    if not branch:
        raise GitError(tr("Kein Branch ausgecheckt (detached HEAD); bitte selbst pushen.",
                          "No branch is checked out (detached HEAD); please push it yourself."))
    remote = _push_remote(top, branch)
    if not remote:
        raise GitError(tr("Das Repository hat kein Remote, auf das sich pushen ließe.",
                          "The repository has no remote to push to."))
    if not to_default and _is_default(top, remote, branch):
        raise DefaultBranchError(tr(f"Nicht gepusht: {remote}/{branch} ist der Standard-Branch des Remotes. "
                                    "„Pushen“ fragt vorher nach.",
                                    f"Not pushed: {remote}/{branch} is the remote's default branch. "
                                    "\"Push\" asks first."))
    tracks = (git(top, "config", "--get", f"branch.{branch}.merge", ok=(0, 1)) or "").strip()
    run(top, "push", *([] if tracks else ["--set-upstream"]), remote, f"refs/heads/{branch}:refs/heads/{branch}",
        timeout=PUSH_TIMEOUT, env=_env())
    return {"target": f"{remote}/{branch}"}
