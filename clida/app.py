"""What the UI can ask for: sessions, titles, live status and terminals."""

import json
import os
import threading
from pathlib import Path

from . import STATE_DIR, registry, transcripts
from .library import Library
from .terminals import Terminals

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
        try:
            self._titles = json.loads(TITLES_FILE.read_text())
        except (OSError, ValueError):
            self._titles = {}

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
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = TITLES_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._titles, ensure_ascii=False, indent=1))
            os.replace(tmp, TITLES_FILE)


def _home_label(path):
    if not path:
        return None
    home = str(Path.home())
    if path == home:
        return "~"
    return "~" + path[len(home):] if path.startswith(home + "/") else path


def _clean_name(value, limit: int, what: str) -> str:
    name = " ".join(str(value or "").split())[:limit]
    if not name:
        raise HttpError(400, f"{what} darf nicht leer sein")
    return name


def _first_line(text: str, limit: int = 80) -> str:
    line = text.strip().splitlines()[0] if text and text.strip() else ""
    return line if len(line) <= limit else line[:limit - 1] + "…"


class Desk:
    def __init__(self, claude: str):
        self.index = transcripts.Index()
        self.titles = Titles()
        self.library = Library()
        self.terminals = Terminals(claude)

    def _require_session(self, session_id: str) -> dict:
        info = self.index.get(session_id)
        if info is None:
            self.index.scan()
            info = self.index.get(session_id)
        if info is None:
            raise HttpError(404, "Chat nicht gefunden")
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
        return "Neuer Chat"

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
        return {"terminals": terminals, "external": external}

    def sessions(self) -> dict:
        infos = self.index.scan()
        library = self.library.snapshot()
        out = []
        for info in infos:
            out.append({
                "id": info["id"], "title": self._title(info["id"], info), "cwd": info["cwd"],
                "cwd_label": _home_label(info["cwd"]) or info["project"], "mtime": info["mtime"],
                "first_prompt": info["first_prompt"], "last_prompt": info["last_prompt"],
                "folder": library["folder_of"].get(info["id"]), "archived": info["id"] in library["archived"],
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
                })
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return {"sessions": out, "folders": library["folders"], "home": str(Path.home()), **self.status()}

    def messages(self, session_id: str) -> dict:
        info = self.index.get(session_id)
        if info is None:
            self.index.scan()
            info = self.index.get(session_id)
        if info is None:
            if any(t.session_id == session_id for t in self.terminals.all()):
                return {"items": [], "truncated": False}
            raise HttpError(404, "Chat nicht gefunden")
        return transcripts.render(info["path"])

    def rename(self, session_id: str, title) -> dict:
        title = _clean_name(title, 200, "Titel")
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
                raise HttpError(400, "Ungültige Session-ID")
            info = self._require_session(resume)
            cwd = info["cwd"]
            if not cwd or not os.path.isdir(cwd):
                raise HttpError(400, f"Arbeitsverzeichnis existiert nicht mehr: {cwd}")
            status = self.status()  # also updates which session each of our terminals runs now
            for row in status["terminals"]:
                # One of our terminals may run it under another id, after /resume or /clear in the CLI.
                if row["session_id"] == resume and row["status"] != "exited":
                    return {"id": row["id"], "session_id": resume, "cwd": row["cwd"]}
            if not body.get("force") and any(ext["session_id"] == resume for ext in status["external"]):
                raise HttpError(409, "Dieser Chat läuft bereits in einem anderen Terminal.")
            term = self.terminals.start(cwd, resume=resume)
        else:
            cwd = os.path.abspath(os.path.expanduser(str(body.get("cwd") or "~")))
            if not os.path.isdir(cwd):
                raise HttpError(400, f"Verzeichnis existiert nicht: {cwd}")
            title = " ".join(str(body.get("title") or "").split())[:200]
            term = self.terminals.start(cwd, name=title or None)
            if title:
                self.titles.set(term.session_id, title)
        return {"id": term.id, "session_id": term.session_id, "cwd": term.cwd}

    def create_folder(self, name) -> dict:
        return self.library.create_folder(_clean_name(name, 80, "Ordnername"))

    def rename_folder(self, folder_id: str, name) -> dict:
        name = _clean_name(name, 80, "Ordnername")
        if not self.library.rename_folder(folder_id, name):
            raise HttpError(404, "Ordner nicht gefunden")
        return {"id": folder_id, "name": name}

    def delete_folder(self, folder_id: str) -> dict:
        if not self.library.delete_folder(folder_id):
            raise HttpError(404, "Ordner nicht gefunden")
        return {"ok": True}

    def move_session(self, session_id: str, folder_id) -> dict:
        if folder_id is not None and not isinstance(folder_id, str):
            raise HttpError(400, "Ungültiger Ordner")
        if not self.library.move(session_id, folder_id):
            raise HttpError(404, "Ordner nicht gefunden")
        return {"ok": True}

    def archive_session(self, session_id: str, archived) -> dict:
        self.library.set_archived(session_id, bool(archived))
        return {"ok": True}

    def delete_session(self, session_id: str) -> dict:
        self._require_session(session_id)
        status = self.status()
        running = [t for t in status["terminals"] if t["session_id"] == session_id and t["status"] != "exited"]
        if running or any(e["session_id"] == session_id for e in status["external"]):
            raise HttpError(409, "Diese Sitzung läuft noch. Bitte zuerst beenden.")
        try:
            transcripts.delete_session_files(session_id, self.index.paths(session_id))
        except (OSError, ValueError) as e:
            raise HttpError(500, f"Löschen fehlgeschlagen: {e}")
        self.library.forget(session_id)
        self.titles.set(session_id, None)
        term = self.terminals.get(session_id)
        if term is not None and not term.alive:
            self.terminals.stop(session_id)
        self.index.scan()
        return {"ok": True}

    def stop_terminal(self, terminal_id: str) -> dict:
        if not self.terminals.stop(terminal_id):
            raise HttpError(404, "Terminal nicht gefunden")
        return {"ok": True}
