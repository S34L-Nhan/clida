"""Keyboard shortcuts, for the settings page: CLIDA's own (~/.clida/keys.json) and the Claude
CLI's (~/.claude/keybindings.json, which every running CLI reads again when it changes).

A shortcut is written as the CLI writes it: modifiers (ctrl, alt, shift, cmd; mod for Cmd on a
Mac and Ctrl elsewhere, in CLIDA's defaults only), then the key, joined by "+"; a chord is
keystrokes separated by a space ("ctrl+x ctrl+e"). Of the CLI's actions, the ones that matter
while working in a chat are listed, with the defaults of CLI 2.1.310; the CLI's file may hold
others, which are kept as they are.
"""

import json
import os
import threading

from . import CLAUDE_HOME, STATE_DIR, storage
from .settings import tr

CLI_FILE = CLAUDE_HOME / "keybindings.json"
APP_FILE = STATE_DIR / "keys.json"

# (context, action, default keys). Contexts as the CLI names them; the window groups by them.
CLI_ACTIONS = [
    ("Global", "app:interrupt", ["ctrl+c"]),
    ("Global", "app:exit", ["ctrl+d"]),
    ("Global", "app:toggleTodos", ["ctrl+t"]),
    ("Global", "app:toggleTranscript", ["ctrl+o"]),
    ("Global", "app:toggleBrief", ["ctrl+shift+b"]),
    ("Global", "history:search", ["ctrl+r"]),
    ("Chat", "chat:submit", ["enter"]),
    ("Chat", "chat:newline", ["ctrl+j"]),
    ("Chat", "chat:cancel", ["escape"]),
    ("Chat", "chat:stash", ["ctrl+s"]),
    ("Chat", "chat:undo", ["ctrl+_", "ctrl+-", "ctrl+shift+-", "ctrl+shift+_"]),
    ("Chat", "chat:externalEditor", ["ctrl+x ctrl+e", "ctrl+g"]),
    ("Chat", "chat:imagePaste", ["alt+v", "ctrl+v"]),
    ("Chat", "chat:cycleMode", ["shift+tab"]),
    ("Chat", "chat:modelPicker", ["meta+p"]),
    ("Chat", "chat:thinkingToggle", ["meta+t"]),
    ("Chat", "chat:fastMode", ["meta+o"]),
    ("Chat", "chat:queueSubmit", ["ctrl+x enter"]),
    ("Chat", "chat:sendNow", ["ctrl+x ctrl+s", "ctrl+enter"]),
    ("Chat", "chat:killAgents", ["ctrl+x ctrl+k"]),
    ("Chat", "history:previous", ["up"]),
    ("Chat", "history:next", ["down"]),
    ("Autocomplete", "autocomplete:accept", ["tab"]),
    ("Autocomplete", "autocomplete:dismiss", ["escape"]),
    ("Transcript", "transcript:toggleShowAll", ["ctrl+e"]),
    ("Task", "task:background", ["ctrl+x ctrl+b", "ctrl+b"]),
]
_BY_ACTION = {action: (context, defaults) for context, action, defaults in CLI_ACTIONS}
LOCKED = {"app:interrupt", "app:exit"}  # the CLI does not let these be bound otherwise
# Keys the CLI refuses: the terminal sends the same as Enter, Tab, Escape, Backspace, or a signal.
CLI_RESERVED = {"ctrl+c", "ctrl+d", "ctrl+m", "ctrl+[", "ctrl+i", "ctrl+h", "ctrl+\\"}

APP_ACTIONS = ("newChat", "toggleSidebar", "searchChats", "nextTab", "prevTab", "fileSearch", "terminalNewline")

_MODIFIERS = ("ctrl", "alt", "shift", "meta", "cmd", "mod")
_NAMED = {"escape", "enter", "tab", "space", "backspace", "delete", "up", "down", "left", "right", "pageup",
          "pagedown", "home", "end", "insert", *(f"f{n}" for n in range(1, 13))}


def valid_key(text) -> bool:
    """A keystroke or chord in the notation above: up to three keystrokes, each with its key."""
    if not isinstance(text, str) or not 0 < len(text) <= 60:
        return False
    for stroke in text.split(" "):
        *mods, key = stroke.split("+")
        if any(m not in _MODIFIERS for m in mods) or len(set(mods)) != len(mods):
            return False
        if not (key in _NAMED or (len(key) == 1 and key.isprintable() and key != " ")):
            return False
    return 0 < len(text.split(" ")) <= 3


def same_key(text: str) -> str:
    """A form to compare by: in a terminal alt and meta are one key, and modifiers come in any order."""
    def stroke(part):
        *mods, key = part.split("+")
        return "+".join(sorted("alt" if m == "meta" else m for m in mods) + [key])
    return " ".join(stroke(part) for part in text.split(" "))


class KeysError(Exception):
    pass


class Keybindings:
    def __init__(self):
        self._lock = threading.Lock()

    # -- CLIDA's own -------------------------------------------------------------------------

    def _app(self) -> dict:
        data = storage.load(APP_FILE) or {}
        return {a: k for a, k in data.items() if a in APP_ACTIONS and valid_key(k)}

    # -- the CLI's ---------------------------------------------------------------------------

    @staticmethod
    def _cli_file():
        """The CLI's file as it is: (data, None), ({"bindings": []}, None) if there is none, or
        (None, why) if it cannot be read; then it is shown but never written over."""
        try:
            text = CLI_FILE.read_text()
        except FileNotFoundError:
            return {"bindings": []}, None
        except OSError as e:
            return None, str(e)
        try:
            data = json.loads(text)
        except ValueError as e:
            return None, tr(f"keine gültige JSON-Datei ({e})", f"not valid JSON ({e})")
        if not isinstance(data, dict) or not isinstance(data.get("bindings", []), list):
            return None, tr("unerwarteter Aufbau", "unexpected structure")
        return data, None

    @staticmethod
    def _blocks(data, context):
        return [b for b in data.get("bindings", []) if isinstance(b, dict) and b.get("context") == context
                and isinstance(b.get("bindings"), dict)]

    def _effective(self, data, context, action, defaults) -> list:
        """The keys an action has with the user's file: the defaults it does not unbind, and what
        it binds to the action in that context (later entries win, as in the CLI)."""
        keys = {same_key(k): k for k in defaults}  # by the key as the CLI sees it (alt+p is meta+p)
        for block in self._blocks(data, context) if data else ():
            for key, value in block["bindings"].items():
                if value == action:
                    keys[same_key(key)] = key
                else:
                    keys.pop(same_key(key), None)  # unbound (null) or given to another action
        return list(keys.values())

    def snapshot(self) -> dict:
        with self._lock:
            data, error = self._cli_file()
            cli = [{"context": context, "action": action, "defaults": defaults,
                    "keys": self._effective(data, context, action, defaults) if data else list(defaults),
                    "locked": action in LOCKED}
                   for context, action, defaults in CLI_ACTIONS]
            return {"app": self._app(), "cli": cli, "cli_error": error, "cli_file": str(CLI_FILE)}

    def update(self, body: dict) -> dict:
        """Store changes: {"app": {action: key or null (default)}, "cli": {action: [keys] or null
        (default)}}. The CLI's file keeps whatever else it holds."""
        app, cli = body.get("app") or {}, body.get("cli") or {}
        if not isinstance(app, dict) or not isinstance(cli, dict):
            raise KeysError(tr("Ungültige Anfrage", "Invalid request"))
        with self._lock:
            if app:
                stored = self._app()
                for action, key in app.items():
                    if action not in APP_ACTIONS or (key is not None and not valid_key(key)):
                        raise KeysError(tr(f"Ungültiges Tastenkürzel für {action}", f"Invalid shortcut for {action}"))
                    if key is None:
                        stored.pop(action, None)
                    else:
                        stored[action] = key
                storage.save(APP_FILE, stored)
            if cli:
                self._update_cli(cli)
        return self.snapshot()

    def _update_cli(self, changes: dict):
        data, error = self._cli_file()
        if data is None:
            raise KeysError(tr(f"{CLI_FILE} lässt sich nicht lesen ({error}); bitte reparieren oder löschen.",
                               f"{CLI_FILE} cannot be read ({error}); please fix or delete it."))
        for action, keys in changes.items():
            if action not in _BY_ACTION or action in LOCKED:
                raise KeysError(tr(f"{action} lässt sich hier nicht ändern", f"{action} cannot be changed here"))
            context, defaults = _BY_ACTION[action]
            keys = list(defaults) if keys is None else keys
            if not isinstance(keys, list) or not keys or not all(valid_key(k) for k in keys):
                raise KeysError(tr(f"Ungültiges Tastenkürzel für {action}", f"Invalid shortcut for {action}"))
            if sorted(map(same_key, keys)) == sorted(map(same_key, defaults)):
                keys = list(defaults)  # the defaults, as alt+p may stand for meta+p: no entry needed
            strokes = [part.split("+") for k in keys for part in k.split(" ")]
            if any(k in CLI_RESERVED for k in keys) or any("cmd" in s or "mod" in s for s in strokes):
                raise KeysError(tr(f"Diese Taste erreicht die CLI nicht: {', '.join(keys)}",
                                   f"This key does not reach the CLI: {', '.join(keys)}"))
            for key in keys:  # taken by an action not changed now, listed here or only in the file?
                for other_context, other, other_defaults in CLI_ACTIONS:
                    if other_context != context or other == action or other in changes:
                        continue
                    if same_key(key) in {same_key(k) for k in self._effective(data, context, other, other_defaults)}:
                        raise KeysError(tr(f"{key} gehört schon zu {other}", f"{key} already belongs to {other}"))
                for block in self._blocks(data, context):
                    for bound, other in block["bindings"].items():
                        if other not in (None, action) and other not in _BY_ACTION and same_key(bound) == same_key(key):
                            raise KeysError(tr(f"{key} gehört schon zu {other}", f"{key} already belongs to {other}"))
            changes[action] = keys
        # First what the changed actions had goes, then they get their keys: a swap of two keys
        # within one save is no clash.
        for action in changes:
            self._clear(data, *_BY_ACTION[action], action)
        for action, keys in changes.items():
            self._bind(data, *_BY_ACTION[action], action, keys)
        # An unbinding of a key that some action binds anew in the same context only gets in the way:
        # the CLI takes the later entry, and alt+p and meta+p are one key to it.
        for context in {c for c, _, _ in CLI_ACTIONS}:
            blocks = self._blocks(data, context)
            bound = {same_key(k) for b in blocks for k, v in b["bindings"].items() if v is not None}
            for block in blocks:
                for key in [k for k, v in block["bindings"].items() if v is None and same_key(k) in bound]:
                    del block["bindings"][key]
        # Then no key twice in a context, among the listed actions (the CLI would give it to one).
        owner = {}
        for context, action, defaults in CLI_ACTIONS:
            for key in self._effective(data, context, action, defaults):
                other = owner.setdefault((context, same_key(key)), action)
                if other != action:
                    raise KeysError(tr(f"{key} gehört schon zu {other}", f"{key} already belongs to {other}"))
        data.setdefault("$schema", "https://www.schemastore.org/claude-code-keybindings.json")
        data.setdefault("$docs", "https://code.claude.com/docs/en/keybindings")
        data["bindings"] = [b for b in data.get("bindings", []) if not isinstance(b, dict) or b.get("bindings")
                            or set(b) - {"context", "bindings"}]
        CLI_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CLI_FILE.with_name(CLI_FILE.name + ".clida-tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, CLI_FILE)  # whole or not at all: the running CLIs read it on every change

    def _clear(self, data, context, defaults, action):
        """The user's own entries for action go: what it binds, and the unbinding of its defaults."""
        for block in self._blocks(data, context):
            for key in [k for k, v in block["bindings"].items() if v == action or (v is None and k in defaults)]:
                del block["bindings"][key]

    def _bind(self, data, context, defaults, action, keys):
        """Then the file says action has exactly keys: a default not wanted is unbound, a new key bound."""
        blocks = self._blocks(data, context)
        if not blocks:
            block = {"context": context, "bindings": {}}
            data.setdefault("bindings", []).append(block)
        else:
            block = blocks[-1]
        for key in defaults:
            if key not in keys:
                block["bindings"][key] = None
        for key in keys:
            if key not in defaults:
                # Never by overwriting: a key that another action holds is that action's.
                for other_block in blocks:
                    for bound, other in other_block["bindings"].items():
                        if other not in (None, action) and same_key(bound) == same_key(key):
                            raise KeysError(tr(f"{key} gehört schon zu {other}", f"{key} already belongs to {other}"))
                block["bindings"][key] = action
