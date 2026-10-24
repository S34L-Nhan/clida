"""What the UI can ask for: sessions, titles, live status and terminals."""

import datetime
import itertools
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import STATE_DIR, browser, gitrepo, locate, registry, storage, transcripts
from .keybindings import Keybindings, KeysError
from .library import Library
from .notes import BODY_MAX, PREVIEW_MAX, Notes
from .search import Search
from .settings import Settings, tr
from .terminals import UPLOADS, Terminals, child_env
from .worktrees import WorktreeError, Worktrees

UPLOAD_LIMIT = 50 * 1024 * 1024
ANCHOR = re.compile(r"[0-9a-f-]{36}#\d{1,4}")  # a message in the history: entry uuid # its place in it
REWIND_TIMEOUT = 120
PROMPT_MAX = 100_000  # characters a prompt from the window may have
TYPED_MAX = 8_000  # characters typed in rather than pasted (see send_prompt): a few seconds of typing; as in app.js
WINDOW_TTL = 90  # seconds a window counts as open after its last request; a hidden one polls once a minute

TITLES_FILE = STATE_DIR / "titles.json"


class HttpError(Exception):
    def __init__(self, status: int, message: str, code: str = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code  # for the window to tell this case from others with the same status


class Titles:
    """Titles set in the UI. They win over the CLI's own titles, which a running CLI may re-append."""

    def __init__(self):
        self._lock = threading.Lock()
        self._titles = storage.load(TITLES_FILE) or {}

    def get(self, session_id: str):
        with self._lock:
            return self._titles.get(session_id)

    def set(self, session_id: str, title):
        """Store a title; None removes it."""
        with self._lock:
            if title is None:
                self._titles.pop(session_id, None)
            else:
                self._titles[session_id] = title
            storage.save(TITLES_FILE, self._titles)


def _home_label(path):
    if not path:
        return None
    home = str(Path.home())
    if path == home:
        return "~"
    return "~" + path[len(home):] if path.startswith(home + "/") else path


def _clean_name(value, limit: int, empty: str) -> str:
    name = " ".join(str(value or "").split())[:limit]
    if not name:
        raise HttpError(400, empty)
    return name


def _folder_name(value) -> str:
    return _clean_name(value, 80, tr("Ordnername darf nicht leer sein", "The folder name must not be empty"))


def _upload_name(name) -> str:
    """A safe, unique-ish file name: no directories, no spaces (the CLI splits pasted paths there)."""
    base = os.path.basename(str(name or "").replace("\\", "/"))
    base = re.sub(r"[^\w.-]+", "-", base).strip(".-") or "datei"
    stem, ext = os.path.splitext(base)
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{stem[:60]}{ext[:12].lower()}"


def _git_state(cwd):
    """Branch and number of changed files of the repository cwd is in; None outside one."""
    lines = (gitrepo.git(cwd, "status", "--porcelain=v1", "--branch", timeout=3) or "").splitlines()
    if not lines or not lines[0].startswith("## "):
        return None
    head = lines[0][3:]
    for prefix in ("No commits yet on ", "Initial commit on "):
        head = head[len(prefix):] if head.startswith(prefix) else head
    branch = head.split("...")[0].split(" ")[0]
    return {"branch": None if branch == "HEAD" else branch, "dirty": len(lines) - 1}


def _first_line(text: str, limit: int = 80) -> str:
    line = text.strip().splitlines()[0] if text and text.strip() else ""
    return line if len(line) <= limit else line[:limit - 1] + "…"


class Desk:
    def __init__(self, claude: str):
        self.index = transcripts.Index()
        self.titles = Titles()
        self.library = Library()
        self.notes = Notes()
        self.settings = Settings()
        self.terminals = Terminals(claude)
        self.changes_cache = transcripts.ChangesCache()
        self.repo_changes = gitrepo.RepoChanges()
        self.worktrees = Worktrees()
        self.search = Search()
        self.keybindings = Keybindings()
        self._status_seq = itertools.count(1)
        self._rewinding = set()  # chats whose files the CLI is putting back now
        self._rewinding_lock = threading.Lock()
        # New on every start: an open window that sees it change reloads, with the new code.
        self.boot = secrets.token_hex(6)
        self._windows = {}  # window id -> time of its last request (monotonic)
        self._windows_lock = threading.Lock()

    def _info(self, session_id: str):
        """The chat's index entry, with a fresh scan if it is not known yet; None without a transcript."""
        info = self.index.get(session_id)
        if info is None:
            self.index.scan()
            info = self.index.get(session_id)
        return info

    def _require_session(self, session_id: str) -> dict:
        info = self._info(session_id)
        if info is None:
            raise HttpError(404, tr("Chat nicht gefunden", "Chat not found"))
        return info

    def _title(self, session_id: str, info) -> str:
        override = self.titles.get(session_id)
        if override:
            return override
        if info:
            for key in ("custom_title", "ai_title", "summary"):
                if info.get(key):
                    return info[key]
            if info.get("first_prompt"):
                return _first_line(info["first_prompt"])
        return tr("Neuer Chat", "New chat")

    def status(self) -> dict:
        self.terminals.reap()
        running = registry.running()
        ours = {}
        terminals = []
        for term in self.terminals.all():
            entry = running.get(term.pid) if term.alive else None
            if entry and entry.get("sessionId"):
                if entry["sessionId"] != term.session_id:
                    # /clear or /resume in the CLI: the new session works in the old one's worktree.
                    self.worktrees.follow(term.session_id, entry["sessionId"])
                term.session_id = entry["sessionId"]
            ours[term.pid] = term
            terminals.append({
                "id": term.id, "session_id": term.session_id, "cwd": term.cwd,
                "status": term.status(entry), "exit_code": term.exit_code, "started": term.started,
                "reported": entry is not None,  # the CLI's own report, not CLIDA's guess from its output
            })
        live_ids = {t["session_id"] for t in terminals if t["status"] != "exited"}
        external = []
        for pid, entry in running.items():
            sid = entry.get("sessionId")
            if pid in ours or not sid or sid in live_ids:
                continue
            external.append({"session_id": sid, "pid": pid, "status": registry.cli_status(entry),
                             "kind": entry.get("kind"), "cwd": entry.get("cwd")})
        # Numbered as taken: an answer that overtakes a later one on the way must not undo it.
        return {"terminals": terminals, "external": external, "boot": self.boot, "windows": self.windows_open(),
                "seq": next(self._status_seq)}

    # -- windows: `clida restart` opens one only when none is open --------------------------

    def window_seen(self, window_id: str):
        with self._windows_lock:
            self._windows[window_id] = time.monotonic()

    def window_closed(self, window_id: str) -> dict:
        with self._windows_lock:
            self._windows.pop(window_id, None)
        return {"ok": True}

    def windows_open(self) -> int:
        now = time.monotonic()
        with self._windows_lock:
            for window_id in [w for w, seen in self._windows.items() if now - seen > WINDOW_TTL]:
                del self._windows[window_id]
            return len(self._windows)

    def sessions(self) -> dict:
        infos = self.index.scan()
        library = self.library.snapshot()
        notes = self.notes.session_previews()
        usage = self.index.usage()
        worktrees = self.worktrees.all()
        owners = {member: key for key, e in worktrees.items() for member in [key, *e.get("sessions", ())]}

        def worktree_of(sid):
            # Its own, or the one of the chat it went on from (/clear, /resume) or was forked from.
            entry = worktrees.get(owners.get(sid))
            return {"branch": entry["branch"], "repo": os.path.basename(entry["repo"])} if entry else None

        out = []
        for info in infos:
            out.append({
                "id": info["id"], "title": self._title(info["id"], info), "cwd": info["cwd"],
                "cwd_label": _home_label(info["cwd"]) or info["project"], "mtime": info["mtime"],
                "first_prompt": info["first_prompt"], "last_prompt": info["last_prompt"],
                "folder": library["folder_of"].get(info["id"]), "archived": info["id"] in library["archived"],
                "note": notes.get(info["id"]), "usage": usage["chats"].get(info["id"]),
                "worktree": worktree_of(info["id"]),
            })
        known = {s["id"] for s in out}
        for term in self.terminals.all():
            if term.alive and term.session_id not in known:
                known.add(term.session_id)
                out.append({
                    "id": term.session_id, "title": self._title(term.session_id, None), "cwd": term.cwd,
                    "cwd_label": _home_label(term.cwd), "mtime": term.started,
                    "first_prompt": None, "last_prompt": None,
                    "folder": library["folder_of"].get(term.session_id),
                    "archived": term.session_id in library["archived"],
                    "note": notes.get(term.session_id), "usage": None,
                    "worktree": worktree_of(term.session_id),
                })
        for sid, entry in worktrees.items():
            if sid not in known:
                # Stopped before its first message, so without a transcript: listed for its worktree,
                # which would otherwise be out of reach.
                out.append({
                    "id": sid, "title": self._title(sid, None), "cwd": entry["path"],
                    "cwd_label": _home_label(entry["path"]), "mtime": entry["created"],
                    "first_prompt": None, "last_prompt": None, "folder": library["folder_of"].get(sid),
                    "archived": sid in library["archived"], "note": notes.get(sid), "usage": None,
                    "worktree": worktree_of(sid),
                })
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return {"sessions": out, "folders": library["folders"], "home": str(Path.home()),
                "cost_today": usage["today"], **self.status()}

    def messages(self, session_id: str) -> dict:
        info = self._info(session_id)
        if info is None:
            if any(t.session_id == session_id for t in self.terminals.all()) or self.worktrees.get(session_id):
                return {"items": [], "truncated": False}
            raise HttpError(404, tr("Chat nicht gefunden", "Chat not found"))
        return transcripts.render(info["path"])

    def search_messages(self, query) -> dict:
        """The chats whose messages hold every word of query, each with its best match."""
        # Only the transcript each chat's history shows: a hit elsewhere could not be opened.
        shown = {info["path"] for info in self.index.scan()}
        hits = self.search.find(str(query or "")[:200], shown)
        return {"hits": hits or {}, "indexing": hits is None}

    def changes(self, session_id: str, brief: bool = False) -> dict:
        """What the chat changed, like a merge request: each file as before the chat against now.

        The files come from the chat's Edit and Write calls, and from its git repository: what
        commits during the chat touched, and uncommitted files written during it (shell commands
        leave no other trace). For a file in both, the CLI's own backup gives the state before.
        brief leaves the diffs and steps out: the header and the switch only need the counts.
        """
        info = self._info(session_id)
        cwd = self._chat_cwd(session_id, info)
        if info is None and cwd is None:
            raise HttpError(404, tr("Chat nicht gefunden", "Chat not found"))
        files = self.changes_cache.get(session_id, self.index.paths(session_id)) if info else []
        repo = {"files": [], "commits": [], "repos": []}
        window = self._chat_window(session_id, info)
        if window:
            # Deduplicated first: a chat edits many files in few folders, and the limit is on folders.
            dirs = list(dict.fromkeys(d for d in ([cwd] if cwd else []) + [os.path.dirname(f["path"]) for f in files]
                                      if os.path.isdir(d)))[:20]
            repo = self.repo_changes.get(dirs, *window, brief=brief)
            # Matched by real path: git reports /mnt/d/work/x for a file Claude edited as ~/work/x.
            tool = {os.path.realpath(f["path"]): f for f in files}
            for found in repo["files"]:
                mine = tool.get(os.path.realpath(found["path"]))
                if mine is None:
                    files.append(found)
                elif (not mine["backup"] or not mine["known"]
                      or (mine["status"] in ("added", "gone") and found["status"] != "added")):
                    # No CLI backup of it (or the backup is gone: the CLI cleans its file history up),
                    # or the CLI's backups say "created" but git had the file when the chat started:
                    # git knows how it was, so its diff, with the chat's steps.
                    mine.update({k: found[k] for k in ("status", "note", "known", "net", "added", "removed")})
            files.sort(key=lambda f: f["path"])
        # Where each file stands in git: committed, not yet, ignored, or outside any repository.
        states = ({} if brief else
                  self.repo_changes.states([f["path"] for f in files], window[0] if window else None))
        out = []
        for changed in files:
            out.append({**changed, "label": self._change_label(changed["path"], cwd), **states.get(changed["path"], {}),
                        **({"net": None, "steps": []} if brief else {})})
        # The branch of the chat's folder, or else of the first repository it worked in.
        where = cwd if cwd and os.path.isdir(cwd) else None
        git = (_git_state(where) if where else None) or (_git_state(repo["repos"][0]) if repo["repos"] else None)
        return {"files": out, "git": git, "commits": repo["commits"],
                "worktree": self.worktrees.status(self.worktrees.key_for(session_id))}

    def _chat_cwd(self, session_id: str, info):
        """The chat's folder: from its transcript, its terminal, or (said nothing yet) its worktree."""
        if info:
            return info["cwd"]
        term = next((t.cwd for t in self.terminals.all() if t.session_id == session_id), None)
        return term or (self.worktrees.get(session_id) or {}).get("path")

    @staticmethod
    def _change_label(path: str, cwd) -> str:
        """The path relative to the chat's folder, also when one of them is reached through a symlink."""
        if cwd:
            for root, target in ((cwd, path), (os.path.realpath(cwd), os.path.realpath(path))):
                if target.startswith(root.rstrip("/") + "/"):
                    return os.path.relpath(target, root)
        return _home_label(path)

    def _chat_window(self, session_id: str, info):
        """(start, end) of the chat in seconds: its first prompt, and its last write; end None while it runs."""
        term = next((t for t in self.terminals.all() if t.session_id == session_id), None)
        starts = [term.started] if term else []
        try:
            if info and info.get("created"):
                starts.append(datetime.datetime.fromisoformat(info["created"].replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
        if not starts:
            return None
        end = None if term and term.alive else max(info["mtime"] if info else 0, min(starts))
        return min(starts), end

    def rename(self, session_id: str, title) -> dict:
        title = _clean_name(title, 200, tr("Titel darf nicht leer sein", "The title must not be empty"))
        self.titles.set(session_id, title)
        info = self.index.get(session_id)
        if info:
            transcripts.append_custom_title(info["path"], session_id, title)
        return {"id": session_id, "title": title}

    def cwds(self) -> list:
        home = str(Path.home())
        seen, out = set(), []
        # Not another chat's worktree: a new chat there would work on that chat's branch.
        worktrees = tuple(e["path"].rstrip("/") + "/" for e in self.worktrees.all().values())
        for info in sorted(self.index.scan(), key=lambda i: i["mtime"], reverse=True):
            cwd = info["cwd"]
            if cwd and cwd not in seen and not (cwd + "/").startswith(worktrees) and os.path.isdir(cwd):
                seen.add(cwd)
                out.append(cwd)
        if home not in seen:
            out.append(home)
        return out[:40]

    def start_terminal(self, body: dict) -> dict:
        resume = body.get("resume")
        if resume:
            if not transcripts.SESSION_ID.fullmatch(str(resume)):
                raise HttpError(400, tr("Ungültige Session-ID", "Invalid session id"))
            if resume in self._rewinding:  # 423, not 409: the window offers "resume anyway" on a 409
                raise HttpError(423, tr("Die Dateien werden gerade zurückgesetzt; bitte gleich noch einmal.",
                                        "The files are being restored; please try again in a moment."))
            info = self._info(resume)
            worktree = self.worktrees.get(resume)
            if info is None and worktree and os.path.isdir(worktree["path"]):
                # Stopped before its first message, so nothing to resume: a new CLI under its id, in
                # its worktree, unless one of ours runs it already (two windows, a double click).
                for row in self.status()["terminals"]:
                    if row["session_id"] == resume and row["status"] != "exited":
                        return {"id": row["id"], "session_id": resume, "cwd": row["cwd"]}
                term = self.terminals.start(worktree["path"], session_id=resume)
                return {"id": term.id, "session_id": term.session_id, "cwd": term.cwd}
            info = info or self._require_session(resume)
            cwd = info["cwd"]
            if not cwd or not os.path.isdir(cwd):
                raise HttpError(400, tr("Arbeitsverzeichnis existiert nicht mehr: ",
                                        "Working directory no longer exists: ") + str(cwd))
            status = self.status()  # also updates which session each of our terminals runs now
            for row in status["terminals"]:
                # One of our terminals may run it under another id, after /resume or /clear in the CLI.
                if row["session_id"] == resume and row["status"] != "exited":
                    return {"id": row["id"], "session_id": resume, "cwd": row["cwd"]}
            if not body.get("force") and any(ext["session_id"] == resume for ext in status["external"]):
                raise HttpError(409, tr("Dieser Chat läuft bereits in einem anderen Terminal.",
                                        "This chat is already running in another terminal."))
            term = self.terminals.start(cwd, resume=resume)
        else:
            cwd = os.path.abspath(os.path.expanduser(str(body.get("cwd") or "~")))
            if not os.path.isdir(cwd):
                raise HttpError(400, tr("Verzeichnis existiert nicht: ", "Directory does not exist: ") + cwd)
            title = " ".join(str(body.get("title") or "").split())[:200]
            folder = body.get("folder")
            session_id = str(uuid.uuid4())
            if body.get("worktree"):
                try:
                    # Never a folder a chat worked in: resuming that chat would work in the new one's.
                    used = [info["cwd"] for info in self.index.scan()] + [t.cwd for t in self.terminals.all()]
                    cwd = self.worktrees.create(session_id, cwd, title, used)
                except WorktreeError as e:
                    raise HttpError(400, tr("Worktree ließ sich nicht anlegen: ", "Could not create the worktree: ") + str(e))
            try:
                term = self.terminals.start(cwd, name=title or None, session_id=session_id)
            except Exception:
                if body.get("worktree"):
                    try:
                        self.worktrees.remove(session_id)  # nothing happened in it yet
                    except WorktreeError:
                        pass
                raise
            if title:
                self.titles.set(term.session_id, title)
            if isinstance(folder, str) and folder:
                self.library.move(term.session_id, folder)  # a folder deleted meanwhile is skipped
            # Said back, so a window newer than this server notices a worktree it asked for in vain.
            return {"id": term.id, "session_id": term.session_id, "cwd": term.cwd, "worktree": bool(body.get("worktree"))}
        return {"id": term.id, "session_id": term.session_id, "cwd": term.cwd}

    # -- the chat's own worktree ------------------------------------------------------------

    def _worktree_key(self, session_id: str) -> str:
        """The worktree record a chat works in (see Worktrees.key_for)."""
        return self.worktrees.key_for(session_id) or session_id

    def _running_in(self, folder: str) -> bool:
        """Whether a CLI works in folder or below it (ours or another terminal's), whatever its
        session id: after /clear or /resume a chat's CLI goes on under another."""
        root = os.path.realpath(folder) + "/"
        status = self.status()
        cwds = ([t["cwd"] for t in status["terminals"] if t["status"] != "exited"]
                + [e.get("cwd") for e in status["external"]])
        for cwd in filter(None, cwds):
            real = os.path.realpath(cwd) + "/"
            if real.startswith(root):
                return True
        return False

    def _require_worktree(self, session_id: str) -> str:
        key = self._worktree_key(session_id)
        if self.worktrees.get(key) is None:
            raise HttpError(404, tr("Dieser Chat hat keinen eigenen Worktree.", "This chat has no worktree of its own."))
        return key

    def merge_worktree(self, session_id: str) -> dict:
        key = self._require_worktree(session_id)
        try:
            return self.worktrees.merge(key)
        except WorktreeError as e:
            raise HttpError(409, str(e))

    def remove_worktree(self, session_id: str) -> dict:
        """Delete the chat's worktree and branch; only while no CLI works in it, under whatever
        session id (after /clear the terminal's is another)."""
        key = self._require_worktree(session_id)
        entry = self.worktrees.get(key)
        if entry:
            if self._running(key) or self._running_in(entry["path"]):
                raise HttpError(409, tr("In diesem Worktree läuft noch eine Session. Bitte zuerst beenden.",
                                        "A session still runs in this worktree. Please stop it first."))
        try:
            self.worktrees.remove(key)
        except WorktreeError as e:
            raise HttpError(409, str(e))
        if self._info(key) is None:
            # A chat that said nothing was listed for its worktree only: with it, its name and place go.
            self.titles.set(key, None)
            self.library.forget(key)
            self.notes.forget(key)
        return {"ok": True}

    # -- back to a message: its files, or the conversation up to it -----------------------------

    def _running(self, session_id: str) -> bool:
        status = self.status()
        return (any(t["session_id"] == session_id and t["status"] != "exited" for t in status["terminals"])
                or any(e["session_id"] == session_id for e in status["external"]))

    @staticmethod
    def _message(body: dict, roles=("user", "assistant")):
        anchor, role = str(body.get("anchor") or ""), body.get("role")
        if not ANCHOR.fullmatch(anchor) or role not in roles:
            raise HttpError(400, tr("Ungültige Nachricht", "Invalid message"))
        return anchor.split("#")[0], role

    def _chat_folder(self, session_id: str):
        info = self._require_session(session_id)
        if not info["cwd"] or not os.path.isdir(info["cwd"]):
            raise HttpError(400, tr("Arbeitsverzeichnis existiert nicht mehr: ",
                                    "Working directory no longer exists: ") + str(info["cwd"]))
        return info

    def fork(self, session_id: str, body: dict) -> dict:
        """A new chat with the conversation up to a message, started in a terminal.

        At an answer the copy ends with that answer; at a prompt it ends just before it, so the
        prompt can be written anew (the window types it in again, unsent).
        """
        message, role = self._message(body)
        info = self._chat_folder(session_id)
        new_id = str(uuid.uuid4())
        try:
            path = transcripts.fork(info["path"], message, role == "user", new_id)
        except transcripts.NoParent:
            raise HttpError(404, tr("Was vor dieser Nachricht kam, steht nicht in ihrer Datei (der Chat wurde in einem "
                                    "anderen Ordner fortgesetzt); bitte von einer Antwort aus abzweigen.",
                                    "What came before this message is not in its file (the chat was resumed in another "
                                    "folder); please fork from an answer instead."))
        except LookupError:
            raise HttpError(404, tr("Nachricht nicht im Verlauf gefunden", "Message not found in the history"))
        except ValueError:
            raise HttpError(400, tr("Vor der ersten Nachricht gibt es nichts zu übernehmen: einfach einen neuen Chat starten.",
                                    "There is nothing before the first message: just start a new chat."))
        except OSError as e:
            raise HttpError(500, tr("Abzweigen fehlgeschlagen: ", "Forking failed: ") + str(e))
        prefix, title = tr("Abzweig: ", "Fork: "), self._title(session_id, info)
        title = (title if title.startswith(prefix) else prefix + title)[:200]  # a fork of a fork: once
        self.titles.set(new_id, title)
        transcripts.append_custom_title(path, new_id, title)
        folder = self.library.snapshot()["folder_of"].get(session_id)
        if folder:
            self.library.move(new_id, folder)
        self.worktrees.follow(session_id, new_id)  # it works in the same folder, so in its worktree
        self.index.scan()
        term = self.terminals.start(info["cwd"], resume=new_id)
        return {"id": term.id, "session_id": new_id, "cwd": term.cwd}

    def rewind_files(self, session_id: str, body: dict) -> dict:
        """Put the files Claude changed with its edit tools back as they were before a prompt.

        The CLI's own checkpoints do it (what /rewind restores from): claude --resume <chat>
        --rewind-files <prompt> changes the files and exits. Only while the chat is not running:
        the running CLI would not know its files went back.
        """
        message, _ = self._message(body, roles=("user",))
        info = self._chat_folder(session_id)
        with self._rewinding_lock:
            if session_id in self._rewinding:
                raise HttpError(423, tr("Die Dateien werden gerade schon zurückgesetzt.",
                                        "The files are being restored already."))
            # By folder too: after /clear the CLI works on there under another id.
            if self._running(session_id) or self._running_in(info["cwd"]):
                raise HttpError(409, tr("Diese Sitzung läuft noch. Bitte zuerst beenden.",
                                        "This session is still running. Please stop it first."))
            self._rewinding.add(session_id)
        try:
            return self._rewind(session_id, info, message)
        finally:
            with self._rewinding_lock:
                self._rewinding.discard(session_id)

    def _rewind(self, session_id: str, info, message: str) -> dict:
        # Checkpoints are on in the interactive CLI; a run like this one needs to ask for them.
        env = {**child_env(), "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING": "1"}
        try:
            proc = subprocess.Popen([self.terminals.claude, "--resume", session_id, "--rewind-files", message],
                                    cwd=info["cwd"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True)
        except OSError as e:
            raise HttpError(500, tr("Die CLI ließ sich nicht starten: ", "The CLI did not run: ") + str(e))
        try:
            stdout, stderr = proc.communicate(timeout=REWIND_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)  # with whatever it started
            except ProcessLookupError:
                pass
            proc.communicate()
            raise HttpError(504, tr(f"Die CLI hat nach {REWIND_TIMEOUT} s nicht geantwortet; abgebrochen.",
                                    f"The CLI did not answer within {REWIND_TIMEOUT} s; stopped."))
        said = transcripts.strip_ansi((stderr or stdout).decode("utf-8", "replace")).strip()
        if proc.returncode != 0:
            last = said.splitlines()[-1] if said else f"exit {proc.returncode}"
            if "unknown option" in said:  # --rewind-files is the CLI's own, not documented: it may go
                last += tr(" (diese CLI kennt das nicht: bitte die claude-CLI aktualisieren)",
                           " (this CLI does not know it: please update the claude CLI)")
            raise HttpError(409, tr("Die CLI hat die Dateien nicht zurückgesetzt: ", "The CLI did not restore the files: ")
                            + last)
        return {"ok": True}

    def create_folder(self, name) -> dict:
        return self.library.create_folder(_folder_name(name))

    def rename_folder(self, folder_id: str, name) -> dict:
        name = _folder_name(name)
        if not self.library.rename_folder(folder_id, name):
            raise HttpError(404, tr("Ordner nicht gefunden", "Folder not found"))
        return {"id": folder_id, "name": name}

    def delete_folder(self, folder_id: str) -> dict:
        if not self.library.delete_folder(folder_id):
            raise HttpError(404, tr("Ordner nicht gefunden", "Folder not found"))
        return {"ok": True}

    def move_session(self, session_id: str, folder_id) -> dict:
        if folder_id is not None and not isinstance(folder_id, str):
            raise HttpError(400, tr("Ungültiger Ordner", "Invalid folder"))
        if not self.library.move(session_id, folder_id):
            raise HttpError(404, tr("Ordner nicht gefunden", "Folder not found"))
        return {"ok": True}

    def archive_session(self, session_id: str, archived) -> dict:
        self.library.set_archived(session_id, bool(archived))
        return {"ok": True}

    def delete_session(self, session_id: str, keep_worktree: bool = False) -> dict:
        """Delete a chat for good. Its worktree passes on to a chat that went on from it or was
        forked from it; a worktree the chat holds alone goes first (the chat is the only way to it),
        or keep_worktree leaves folder and branch on disk, where only git lists them."""
        info = self._info(session_id)
        own = self.worktrees.get(session_id)
        if info is None and self.worktrees.key_for(session_id) is None:
            raise HttpError(404, tr("Chat nicht gefunden", "Chat not found"))
        if self._running(session_id):
            raise HttpError(409, tr("Diese Sitzung läuft noch. Bitte zuerst beenden.",
                                    "This session is still running. Please stop it first."))
        if own and not own.get("sessions") and os.path.isdir(own["path"]) and not keep_worktree:
            raise HttpError(409, tr("Dieser Chat hat noch seinen Worktree; ohne den Chat wäre er in CLIDA nicht mehr "
                                    "erreichbar.", "This chat still has its worktree; without the chat, CLIDA could no "
                                    "longer reach it."), code="worktree")
        if info is not None:
            try:
                transcripts.delete_session_files(session_id, self.index.paths(session_id))
            except (OSError, ValueError) as e:
                raise HttpError(500, tr("Löschen fehlgeschlagen: ", "Deleting failed: ") + str(e))
        if self.worktrees.let_go(session_id, listed=lambda sid: self.index.get(sid) is not None) == "own":
            self.worktrees.forget(session_id)  # folder and branch stay: asked for, or gone already
        self.library.forget(session_id)
        self.titles.set(session_id, None)
        shutil.rmtree(UPLOADS / session_id, ignore_errors=True)
        self.notes.forget(session_id)
        for term in self.terminals.all():
            if term.session_id == session_id and not term.alive:
                self.terminals.stop(term.id)
        self.index.scan()
        return {"ok": True}

    def save_upload(self, terminal_id: str, name, length: int, stream) -> dict:
        """Store a file dropped into a running session; the browser never reveals the original path."""
        term = self.terminals.get(terminal_id)
        if term is None or not term.alive:
            raise HttpError(404, tr("Diese Session läuft nicht.", "This session is not running."))
        if length < 0:
            raise HttpError(411, tr("Dateigröße fehlt", "File size missing"))
        if length > UPLOAD_LIMIT:
            raise HttpError(413, tr("Datei ist größer als 50 MB", "File is larger than 50 MB"))
        folder = term.uploads
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        first = target = folder / _upload_name(name)
        n = 2
        while target.exists():  # same name within the same second
            target = first.with_name(f"{first.stem}-{n}{first.suffix}")
            n += 1
        part = target.with_name(target.name + ".part")
        try:
            with open(part, "wb") as f:
                left = length
                while left:
                    chunk = stream.read(min(65536, left))
                    if not chunk:
                        raise HttpError(400, tr("Upload abgebrochen", "Upload aborted"))
                    f.write(chunk)
                    left -= len(chunk)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)
        return {"path": str(target)}

    def open_url(self, url) -> dict:
        if not browser.allowed(url):
            raise HttpError(400, tr("Nur http-, https- und mailto-Links lassen sich öffnen.",
                                    "Only http, https and mailto links can be opened."))
        if not browser.open_url(url):
            raise HttpError(500, tr("Der Standardbrowser ließ sich nicht starten.", "The default browser did not start."))
        return {"ok": True}

    def locate_folder(self, body: dict) -> dict:
        """The path of a folder dropped into a tab; the browser gives only its name and contents."""
        name, entries = body.get("name"), body.get("entries")
        if not isinstance(name, str) or name in ("", ".", "..") or "/" in name or "\0" in name or len(name) > 255:
            raise HttpError(400, tr("Ungültiger Ordnername", "Invalid folder name"))
        if not isinstance(entries, list) or len(entries) > 1000 or not all(isinstance(e, str) for e in entries):
            raise HttpError(400, tr("Ungültige Ordnerliste", "Invalid folder listing"))
        path = locate.find(name, entries)
        if path is None:
            windows = ("Explorer" if locate.on_wsl() else "Finder" if sys.platform == "darwin" else None)
            where = tr(f"den offenen {windows}-Fenstern sowie in ", f"the open {windows} windows and in ") if windows else ""
            raise HttpError(404, tr(f"Ordner „{name}“ nicht gefunden. CLIDA sucht in {where}Desktop, Downloads und "
                                    "Dokumente – den Pfad sonst bitte selbst einfügen.",
                                    f"Folder “{name}” not found. CLIDA looks in {where}Desktop, Downloads and Documents; "
                                    "otherwise paste its path yourself."))
        return {"path": path}

    # -- notes (private: never written to a terminal or a transcript) ------------------------

    def notes_of(self, session_id: str) -> dict:
        return self.notes.get(session_id)

    @staticmethod
    def _note_body(body) -> str:
        body = str(body or "").strip()
        if len(body) > BODY_MAX:
            raise HttpError(400, tr(f"Notiz ist länger als {BODY_MAX} Zeichen",
                                    f"The note is longer than {BODY_MAX} characters"))
        return body

    def set_session_note(self, session_id: str, body) -> dict:
        return {"session": self.notes.set_session(session_id, self._note_body(body))}

    def add_note(self, session_id: str, body: dict) -> dict:
        text = self._note_body(body.get("body"))
        anchor = str(body.get("anchor") or "")
        role = body.get("role")
        if not text:
            raise HttpError(400, tr("Notiz ist leer", "The note is empty"))
        if not ANCHOR.fullmatch(anchor) or role not in ("user", "assistant"):
            raise HttpError(400, tr("Ungültige Nachricht", "Invalid message"))
        preview = " ".join(str(body.get("preview") or "").split())[:PREVIEW_MAX]
        return self.notes.add(session_id, anchor, role, preview, text)

    def edit_note(self, session_id: str, note_id: str, body) -> dict:
        text = self._note_body(body)
        if not text:
            raise HttpError(400, tr("Notiz ist leer", "The note is empty"))
        note = self.notes.edit(session_id, note_id, text)
        if note is None:
            raise HttpError(404, tr("Notiz nicht gefunden", "Note not found"))
        return note

    def delete_note(self, session_id: str, note_id: str) -> dict:
        if not self.notes.remove(session_id, note_id):
            raise HttpError(404, tr("Notiz nicht gefunden", "Note not found"))
        return {"ok": True}

    def push_theme(self, mode) -> dict:
        """Tell every running CLI that the terminal went light or dark.

        The CLI asks for the terminal's background (OSC 11) when it starts. A theme switch in the
        window later reaches it as the color scheme report of DEC mode 2031, CSI ? 997 ; 1 n (dark)
        or ; 2 n (light), which it reads even without having asked; with its theme on "auto" it
        redraws at once.
        """
        if mode not in ("dark", "light"):
            raise HttpError(400, tr("Ungültiger Modus", "Invalid mode"))
        report = b"\x1b[?997;1n" if mode == "dark" else b"\x1b[?997;2n"
        terms = [term for term in self.terminals.all() if term.alive]
        for term in terms:
            term.write(report)
        return {"sent": len(terms)}

    def send_prompt(self, terminal_id: str, text, submit: bool = True) -> dict:
        """Type a prompt into a session and send it, e.g. the review comments of the changes view;
        without submit it is only typed in, for the user to change and send.

        As one bracketed paste, so its line breaks stay in the message instead of sending it early.
        Control characters go: an ESC in it could end the paste and type keys into the CLI.
        """
        term = self.terminals.get(terminal_id)
        if term is None or not term.alive:
            raise HttpError(404, tr("Diese Session läuft nicht.", "This session is not running."))
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(text or "")).strip()
        if not text:
            raise HttpError(400, tr("Nichts zu senden", "Nothing to send"))
        if len(text) > (PROMPT_MAX if submit else TYPED_MAX):
            raise HttpError(413, tr("Text ist zu lang", "The text is too long"))
        # Only into a CLI that says it is idle, checked now: typed into a permission prompt, the
        # Enter (or the text's own letters) would answer it. Without its own report, "idle" is just
        # quiet output, as a prompt is.
        entry = registry.running().get(term.pid)
        if entry is None or registry.cli_status(entry) != "idle":
            raise HttpError(409, tr("Die CLI ist gerade nicht bereit (sie arbeitet oder wartet auf eine Antwort). "
                                    "Die Kommentare bleiben erhalten.",
                                    "The CLI is not ready right now (it is working or waiting for an answer). "
                                    "The comments are kept."))
        if not submit:
            # Typed, not pasted: the CLI shows a paste of a few lines as "[Pasted text #1]", which
            # cannot be changed. A line break is Esc+Enter (a new line, not send), and the text goes
            # in small pieces, as a burst would be taken for a paste again.
            keys = ["\x1b\r" if ch == "\n" else "    " if ch == "\t" else ch for ch in text]
            for at in range(0, len(keys), 48):  # whole characters, and Esc+Enter as one
                term.write("".join(keys[at:at + 48]).encode("utf-8", "replace"))
                time.sleep(0.01)
            return {"ok": True}
        term.write(b"\x1b[200~" + text.encode() + b"\x1b[201~")
        time.sleep(0.2)  # the CLI takes the paste in first; an Enter in the same read could be part of it
        term.write(b"\r")
        return {"ok": True}

    def stop_terminal(self, terminal_id: str) -> dict:
        if not self.terminals.stop(terminal_id):
            raise HttpError(404, tr("Terminal nicht gefunden", "Terminal not found"))
        return {"ok": True}

    # -- keyboard shortcuts: CLIDA's own and the CLI's ------------------------------------------

    def get_keybindings(self) -> dict:
        return self.keybindings.snapshot()

    def update_keybindings(self, body: dict) -> dict:
        try:
            return self.keybindings.update(body)
        except KeysError as e:
            raise HttpError(409, str(e))
        except OSError as e:
            raise HttpError(500, tr("Speichern fehlgeschlagen: ", "Saving failed: ") + str(e))

    # -- settings ---------------------------------------------------------------------------

    def get_settings(self) -> dict:
        return {"settings": self.settings.snapshot()}

    def update_settings(self, body: dict) -> dict:
        try:
            return {"settings": self.settings.update(body)}
        except ValueError as e:
            raise HttpError(400, tr("Ungültige Einstellung: ", "Invalid setting: ") + str(e))
