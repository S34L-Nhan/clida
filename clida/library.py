"""How the sidebar is organised: folders and the archive (~/.clida/library.json)."""

import json
import os
import secrets
import threading
import time

from . import STATE_DIR

LIBRARY_FILE = STATE_DIR / "library.json"


class Library:
    def __init__(self):
        self._lock = threading.Lock()
        try:
            data = json.loads(LIBRARY_FILE.read_text())
        except (OSError, ValueError):
            data = {}
        self._folders = data.get("folders", [])    # [{"id", "name", "sessions": [ids]}], in display order
        self._archived = data.get("archived", {})  # session id -> archived at (unix time)

    def _save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = LIBRARY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"folders": self._folders, "archived": self._archived}, ensure_ascii=False, indent=1))
        os.replace(tmp, LIBRARY_FILE)

    def _folder(self, folder_id):
        return next((f for f in self._folders if f["id"] == folder_id), None)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "folders": [{"id": f["id"], "name": f["name"]} for f in self._folders],
                "folder_of": {sid: f["id"] for f in self._folders for sid in f["sessions"]},
                "archived": set(self._archived),
            }

    def create_folder(self, name: str) -> dict:
        with self._lock:
            folder = {"id": "f" + secrets.token_hex(6), "name": name, "sessions": []}
            self._folders.append(folder)
            self._save()
            return {"id": folder["id"], "name": name}

    def rename_folder(self, folder_id: str, name: str) -> bool:
        with self._lock:
            folder = self._folder(folder_id)
            if folder is None:
                return False
            folder["name"] = name
            self._save()
            return True

    def delete_folder(self, folder_id: str) -> bool:
        """Remove the folder only; its chats go back to the main list."""
        with self._lock:
            folder = self._folder(folder_id)
            if folder is None:
                return False
            self._folders.remove(folder)
            self._save()
            return True

    def move(self, session_id: str, folder_id) -> bool:
        """Put a chat into a folder, or back into the main list when folder_id is None."""
        with self._lock:
            target = self._folder(folder_id) if folder_id else None
            if folder_id and target is None:
                return False
            for folder in self._folders:
                if session_id in folder["sessions"]:
                    folder["sessions"].remove(session_id)
            if target is not None:
                target["sessions"].append(session_id)
            self._save()
            return True

    def set_archived(self, session_id: str, archived: bool):
        with self._lock:
            if archived:
                self._archived[session_id] = time.time()
            else:
                self._archived.pop(session_id, None)
            self._save()

    def forget(self, session_id: str):
        with self._lock:
            for folder in self._folders:
                if session_id in folder["sessions"]:
                    folder["sessions"].remove(session_id)
            self._archived.pop(session_id, None)
            self._save()
