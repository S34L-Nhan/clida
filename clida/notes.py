"""Private notes: one per session, and any number on single messages (~/.clida/notes.json).

Notes are for the user only. Nothing here is ever written to a terminal or a transcript, so
the CLI and the model never see them. A message note is anchored to the transcript entry's
uuid, which stays the same across reloads, resumes and compactions.
"""

import json
import os
import secrets
import threading
import time

from . import STATE_DIR

NOTES_FILE = STATE_DIR / "notes.json"
BODY_MAX = 2000
PREVIEW_MAX = 140


class Notes:
    def __init__(self):
        self._lock = threading.Lock()
        try:
            self._data = json.loads(NOTES_FILE.read_text())
        except (OSError, ValueError):
            self._data = {}  # session id -> {"session": {...} | None, "messages": [...]}

    def _save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = NOTES_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1))
        os.replace(tmp, NOTES_FILE)

    def _entry(self, session_id: str) -> dict:
        return self._data.setdefault(session_id, {"session": None, "messages": []})

    def _tidy(self, session_id: str):
        entry = self._data.get(session_id)
        if entry and not entry["session"] and not entry["messages"]:
            del self._data[session_id]

    def get(self, session_id: str) -> dict:
        with self._lock:
            entry = self._data.get(session_id) or {"session": None, "messages": []}
            return json.loads(json.dumps(entry))

    def session_previews(self) -> dict:
        """session id -> start of its session note, for the sidebar and the tab tooltips."""
        with self._lock:
            return {sid: e["session"]["body"][:300] for sid, e in self._data.items() if e.get("session")}

    def set_session(self, session_id: str, body: str):
        """Set the session note; an empty body removes it."""
        with self._lock:
            entry = self._entry(session_id)
            entry["session"] = {"body": body, "updated": time.time()} if body else None
            self._tidy(session_id)
            self._save()
            return entry["session"]

    def add(self, session_id: str, anchor: str, role: str, preview: str, body: str) -> dict:
        with self._lock:
            now = time.time()
            note = {"id": "n" + secrets.token_hex(6), "anchor": anchor, "role": role,
                    "preview": preview, "body": body, "created": now, "updated": now}
            self._entry(session_id)["messages"].append(note)
            self._save()
            return note

    def edit(self, session_id: str, note_id: str, body: str):
        with self._lock:
            for note in self._data.get(session_id, {}).get("messages", []):
                if note["id"] == note_id:
                    note["body"], note["updated"] = body, time.time()
                    self._save()
                    return note
            return None

    def remove(self, session_id: str, note_id: str) -> bool:
        with self._lock:
            entry = self._data.get(session_id)
            if not entry:
                return False
            kept = [n for n in entry["messages"] if n["id"] != note_id]
            if len(kept) == len(entry["messages"]):
                return False
            entry["messages"] = kept
            self._tidy(session_id)
            self._save()
            return True

    def forget(self, session_id: str):
        with self._lock:
            if self._data.pop(session_id, None) is not None:
                self._save()
