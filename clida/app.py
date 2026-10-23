"""What the UI can ask for: sessions, titles, live status and terminals."""

import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import STATE_DIR, browser, locate, registry, storage, transcripts
from .library import Library
from .notes import BODY_MAX, PREVIEW_MAX, Notes
from .settings import Settings, tr
from .terminals import UPLOADS, Terminals

UPLOAD_LIMIT = 50 * 1024 * 1024
WINDOW_TTL = 90  # seconds a window counts as open after its last request; a hidden one polls once a minute

TITLES_FILE = STATE_DIR / "titles.json"


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


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
    try:
        # Without optional locks: git status may otherwise take index.lock to refresh the index,
        # and a git commit Claude runs in the same repo at that moment would fail.
        out = subprocess.run(["git", "--no-optional-locks", "-C", cwd, "status", "--porcelain=v1", "--branch"],
                             capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = out.stdout.splitlines()
    if out.returncode or not lines or not lines[0].startswith("## "):
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
        # New on every start: an open window that sees it change reloads, with the new code.
        self.boot = secrets.token_hex(6)
        self._windows = {}  # window id -> time of its last request (monotonic)
        self._windows_lock = threading.Lock()

    def _require_session(self, session_id: str) -> dict:
        info = self.index.get(session_id)
        if info is None:
            self.index.scan()
            info = self.index.get(session_id)
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
                term.session_id = entry["sessionId"]
            ours[term.pid] = term
            terminals.append({
                "id": term.id, "session_id": term.session_id, "cwd": term.cwd,
                "status": term.status(entry), "exit_code": term.exit_code, "started": term.started,
            })
        live_ids = {t["session_id"] for t in terminals if t["status"] != "exited"}
        external = []
        for pid, entry in running.items():
            sid = entry.get("sessionId")
            if pid in ours or not sid or sid in live_ids:
                continue
            external.append({"session_id": sid, "pid": pid, "status": registry.cli_status(entry),
                             "kind": entry.get("kind"), "cwd": entry.get("cwd")})
        return {"terminals": terminals, "external": external, "boot": self.boot, "windows": self.windows_open()}

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
        out = []
        for info in infos:
            out.append({
                "id": info["id"], "title": self._title(info["id"], info), "cwd": info["cwd"],
                "cwd_label": _home_label(info["cwd"]) or info["project"], "mtime": info["mtime"],
                "first_prompt": info["first_prompt"], "last_prompt": info["last_prompt"],
                "folder": library["folder_of"].get(info["id"]), "archived": info["id"] in library["archived"],
                "note": notes.get(info["id"]), "usage": usage["chats"].get(info["id"]),
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
                })
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return {"sessions": out, "folders": library["folders"], "home": str(Path.home()),
                "cost_today": usage["today"], **self.status()}

    def messages(self, session_id: str) -> dict:
        info = self.index.get(session_id)
        if info is None:
            self.index.scan()
            info = self.index.get(session_id)
        if info is None:
            if any(t.session_id == session_id for t in self.terminals.all()):
                return {"items": [], "truncated": False}
            raise HttpError(404, tr("Chat nicht gefunden", "Chat not found"))
        return transcripts.render(info["path"])

    def changes(self, session_id: str, brief: bool = False) -> dict:
        """The files the chat changed with its edit tools, each as before the chat against now,
        and the git branch of its folder.

        brief leaves the diffs and steps out: the header and the switch only need the counts.
        """
        info = self.index.get(session_id)
        if info is None:
            self.index.scan()
            info = self.index.get(session_id)
        cwd = info["cwd"] if info else next((t.cwd for t in self.terminals.all() if t.session_id == session_id), None)
        if info is None and cwd is None:
            raise HttpError(404, tr("Chat nicht gefunden", "Chat not found"))
        files = self.changes_cache.get(session_id, self.index.paths(session_id)) if info else []
        out = []
        for changed in files:
            label = (os.path.relpath(changed["path"], cwd)
                     if cwd and changed["path"].startswith(cwd.rstrip("/") + "/") else _home_label(changed["path"]))
            out.append({**changed, "label": label, **({"net": None, "steps": []} if brief else {})})
        git = _git_state(cwd) if cwd and os.path.isdir(cwd) else None
        return {"files": out, "git": git}

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
        for info in sorted(self.index.scan(), key=lambda i: i["mtime"], reverse=True):
            cwd = info["cwd"]
            if cwd and cwd not in seen and os.path.isdir(cwd):
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
            info = self._require_session(resume)
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
            term = self.terminals.start(cwd, name=title or None)
            if title:
                self.titles.set(term.session_id, title)
            if isinstance(folder, str) and folder:
                self.library.move(term.session_id, folder)  # a folder deleted meanwhile is skipped
        return {"id": term.id, "session_id": term.session_id, "cwd": term.cwd}

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

    def delete_session(self, session_id: str) -> dict:
        self._require_session(session_id)
        status = self.status()
        running = [t for t in status["terminals"] if t["session_id"] == session_id and t["status"] != "exited"]
        if running or any(e["session_id"] == session_id for e in status["external"]):
            raise HttpError(409, tr("Diese Sitzung läuft noch. Bitte zuerst beenden.",
                                    "This session is still running. Please stop it first."))
        try:
            transcripts.delete_session_files(session_id, self.index.paths(session_id))
        except (OSError, ValueError) as e:
            raise HttpError(500, tr("Löschen fehlgeschlagen: ", "Deleting failed: ") + str(e))
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
        if not re.fullmatch(r"[0-9a-f-]{36}#\d{1,4}", anchor) or role not in ("user", "assistant"):
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

    def stop_terminal(self, terminal_id: str) -> dict:
        if not self.terminals.stop(terminal_id):
            raise HttpError(404, tr("Terminal nicht gefunden", "Terminal not found"))
        return {"ok": True}

    # -- settings ---------------------------------------------------------------------------

    def get_settings(self) -> dict:
        return {"settings": self.settings.snapshot()}

    def update_settings(self, body: dict) -> dict:
        try:
            return {"settings": self.settings.update(body)}
        except ValueError as e:
            raise HttpError(400, tr("Ungültige Einstellung: ", "Invalid setting: ") + str(e))
