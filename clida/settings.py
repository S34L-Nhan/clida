"""User settings (~/.clida/settings.json), and server texts in the chosen language.

SCHEMA holds every setting with its allowed values and default; nothing else gets stored. A new
setting is one entry here, one in SETTINGS in static/app.js (control and effect) and its texts
in static/i18n.js.
"""

import threading

from . import STATE_DIR, storage

SETTINGS_FILE = STATE_DIR / "settings.json"
SCHEMA = {
    "language": {"choices": ("de", "en"), "default": "de"},
}

_language = "de"  # what tr() answers in; read by every request thread


def tr(de: str, en: str) -> str:
    """A text for the UI (error messages, made-up titles) in the language set in the settings."""
    return en if _language == "en" else de


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        data = storage.load(SETTINGS_FILE) or {}
        self._values = {key: data[key] for key in SCHEMA if _valid(key, data.get(key))}  # only what was chosen
        self._apply()

    def _effective(self) -> dict:
        return {key: self._values.get(key, spec["default"]) for key, spec in SCHEMA.items()}

    def _apply(self):
        global _language
        _language = self._effective()["language"]

    def snapshot(self) -> dict:
        with self._lock:
            return self._effective()

    def update(self, changes: dict) -> dict:
        """Store the given settings; raises ValueError naming the first bad key, storing nothing."""
        for key, value in changes.items():
            if not _valid(key, value):
                raise ValueError(key)
        with self._lock:
            self._values.update(changes)
            self._apply()
            storage.save(SETTINGS_FILE, self._values)
            return self._effective()


def _valid(key, value) -> bool:
    return key in SCHEMA and value in SCHEMA[key]["choices"]
