"""Index and render Claude Code transcripts (~/.claude/projects/<project>/<session>.jsonl).

Transcripts are append-only JSONL files that can grow to tens of megabytes, so the
index remembers how far it has read each file and only parses what was appended.
"""

import json
import os
import re
import shutil
import threading
import traceback

from pathlib import Path

from . import CLAUDE_HOME, STATE_DIR
from .settings import tr

PROJECTS = CLAUDE_HOME / "projects"
INDEX_FILE = STATE_DIR / "index.json"
INDEX_VERSION = 1
SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# Metadata entries are written with "type" as their first key.
_META_PREFIXES = (
    b'{"type":"ai-title"',
    b'{"type":"custom-title"',
    b'{"type":"summary"',
    b'{"type":"last-prompt"',
)
# Large bookkeeping entries that never hold conversation content.
_SKIP_PREFIXES = (
    b'{"type":"api-request',
    b'{"type":"file-history',
    b'{"type":"queue-operation"',
    b'{"type":"cost-state"',
)
_HIDDEN_TAGS = ("<local-command-caveat>", "<system-reminder>", "<task-notification>", "<command-message>")
# OSC sequences end with BEL or with ESC \ (hyperlinks); stopping at any ESC keeps the match short.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

TOOL_TEXT_LIMIT = 4000
MAX_ITEMS = 3000


def _str(value):
    """value if it is a string; transcripts are written by another program, so check every type."""
    return value if isinstance(value, str) else None


def _loads(line: bytes):
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    return entry if isinstance(entry, dict) else None


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = len(text) - limit
    return text[:limit] + "\n… " + tr(f"({cut} Zeichen gekürzt)", f"({cut} characters cut)")


def _tag(text: str, name: str):
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return m.group(1) if m else None


def _user_text(entry: dict):
    """The text a human typed in a user entry, or None for tool results, meta and commands."""
    if entry.get("isMeta") or entry.get("isSidechain") or entry.get("isCompactSummary"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        if any(b.get("type") == "tool_result" for b in blocks):
            return None
        content = "\n".join(_str(b.get("text")) or "" for b in blocks if b.get("type") == "text")
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text or text.startswith("<") or text.startswith("[Request interrupted"):
        return None
    return text


class Index:
    def __init__(self):
        self._lock = threading.Lock()
        self._files = {}  # path -> info dict
        self._by_id = {}
        self._dirty = False
        self._load()

    def _load(self):
        try:
            data = json.loads(INDEX_FILE.read_text())
        except (OSError, ValueError):
            return  # only a cache: the next scan rebuilds it
        if isinstance(data, dict) and data.get("version") == INDEX_VERSION and isinstance(data.get("files"), dict):
            self._files = data["files"]

    def _save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = INDEX_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": INDEX_VERSION, "files": self._files}))
        os.replace(tmp, INDEX_FILE)

    def scan(self) -> list:
        """Refresh from disk and return all sessions that contain a conversation."""
        with self._lock:
            seen = set()
            for project in PROJECTS.iterdir() if PROJECTS.is_dir() else ():
                if not project.is_dir():
                    continue
                for path in project.glob("*.jsonl"):
                    if not SESSION_ID.fullmatch(path.stem):
                        continue
                    key = str(path)
                    seen.add(key)
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    try:
                        self._refresh(key, path.stem, project.name, st)
                    except Exception:  # one odd file must not hide all other chats
                        traceback.print_exc()
            for key in set(self._files) - seen:
                del self._files[key]
                self._dirty = True
            if self._dirty:
                self._save()
                self._dirty = False
            by_id = {}
            for info in self._files.values():
                if info["first_prompt"] or info["custom_title"] or info["ai_title"]:
                    old = by_id.get(info["id"])
                    if old is None or old["mtime"] < info["mtime"]:
                        by_id[info["id"]] = info
            self._by_id = by_id
            return list(by_id.values())

    def get(self, session_id: str):
        with self._lock:
            return self._by_id.get(session_id)

    def paths(self, session_id: str) -> list:
        """Every transcript of this session; resuming from another folder can leave a second one."""
        with self._lock:
            return [info["path"] for info in self._files.values() if info["id"] == session_id]

    def _refresh(self, key, session_id, project, st):
        info = self._files.get(key)
        if info and info["size"] == st.st_size and info["mtime"] == st.st_mtime:
            return
        if not info or st.st_size < info["offset"] or (st.st_size == info["size"]):
            info = {
                "id": session_id, "path": key, "project": project, "offset": 0, "cwd": None,
                "first_prompt": None, "created": None, "ai_title": None, "custom_title": None,
                "summary": None, "last_prompt": None,
            }
        try:
            with open(key, "rb") as f:
                f.seek(info["offset"])
                data = f.read()
        except OSError:
            return  # cache untouched, so the next scan tries again
        info["size"], info["mtime"] = st.st_size, st.st_mtime
        end = data.rfind(b"\n") + 1  # only complete lines; the writer may be mid-line
        self._parse(info, data[:end])
        info["offset"] += end
        self._files[key] = info
        self._dirty = True

    @staticmethod
    def _parse(info, data: bytes):
        for line in data.split(b"\n"):
            if not line:
                continue
            is_meta = line.startswith(_META_PREFIXES)
            need_head = info["first_prompt"] is None or info["cwd"] is None
            if not is_meta and (not need_head or line.startswith(_SKIP_PREFIXES)):
                continue
            entry = _loads(line)
            if entry is None:
                continue
            kind = entry.get("type")
            if kind == "ai-title":
                info["ai_title"] = _str(entry.get("aiTitle")) or info["ai_title"]
            elif kind == "custom-title":
                info["custom_title"] = _str(entry.get("customTitle")) or None
            elif kind == "summary":
                info["summary"] = _str(entry.get("summary")) or info["summary"]
            elif kind == "last-prompt":
                info["last_prompt"] = (_str(entry.get("lastPrompt")) or "")[:300] or info["last_prompt"]
            if info["cwd"] is None and _str(entry.get("cwd")):
                info["cwd"] = entry["cwd"]
            if info["first_prompt"] is None and kind == "user":
                text = _user_text(entry)
                if text:
                    info["first_prompt"] = text[:300]
                    info["created"] = _str(entry.get("timestamp"))


def delete_session_files(session_id: str, paths: list):
    """Remove a chat for good: transcript, tool output, file backups and env snapshot."""
    if not SESSION_ID.fullmatch(session_id):
        raise ValueError(f"not a session id: {session_id}")
    projects = PROJECTS.resolve()
    targets = []
    for path in map(Path, paths):
        if path.name != session_id + ".jsonl" or path.resolve().parent.parent != projects:
            raise ValueError(f"refusing to delete {path}")
        targets += [path, path.with_suffix("")]
    targets += [CLAUDE_HOME / "file-history" / session_id, CLAUDE_HOME / "session-env" / session_id]
    for target in targets:
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)


def append_custom_title(path: str, session_id: str, title: str):
    """Record a title the way `/rename` does, so `claude --resume` shows it too."""
    line = json.dumps({"type": "custom-title", "customTitle": title, "sessionId": session_id},
                      ensure_ascii=False, separators=(",", ":"))
    with open(path, "ab") as f:
        f.write(line.encode() + b"\n")


def _tool_summary(name: str, inp: dict) -> str:
    for key in ("command", "file_path", "path", "pattern", "url", "query", "description", "skill", "prompt"):
        value = inp.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().splitlines()[0][:200]
    return ""


def _tool_input(name: str, inp: dict) -> str:
    if name == "Edit" and isinstance(inp.get("old_string"), str):
        old = "\n".join("- " + l for l in inp["old_string"].splitlines())
        new = "\n".join("+ " + l for l in (inp.get("new_string") or "").splitlines())
        return _clip(f"{inp.get('file_path', '')}\n{old}\n{new}", TOOL_TEXT_LIMIT)
    if name == "Bash" and isinstance(inp.get("command"), str):
        return _clip(inp["command"], TOOL_TEXT_LIMIT)
    return _clip(json.dumps(inp, ensure_ascii=False, indent=2), TOOL_TEXT_LIMIT)


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(_str(block.get("text")) or "")
                elif block.get("type") == "image":
                    parts.append(tr("[Bild]", "[Image]"))
        return "\n".join(parts)
    return ""


def _user_string_items(text: str):
    stripped = text.strip()
    command = _tag(stripped, "command-name")
    if command is not None:
        args = (_tag(stripped, "command-args") or "").strip()
        return [{"k": "command", "text": f"{command} {args}".strip()}]
    stdout = _tag(stripped, "local-command-stdout")
    if stdout is not None:
        out = _ANSI.sub("", stdout).strip()
        return [{"k": "output", "text": _clip(out, TOOL_TEXT_LIMIT)}] if out else []
    bash = _tag(stripped, "bash-input")
    if bash is not None:
        return [{"k": "command", "text": "! " + bash.strip()}]
    if stripped.startswith("<bash-stdout>") or stripped.startswith("<bash-stderr>"):
        out = "\n".join(filter(None, ((_tag(stripped, "bash-stdout") or "").strip(),
                                      (_tag(stripped, "bash-stderr") or "").strip())))
        return [{"k": "output", "text": _clip(_ANSI.sub("", out), TOOL_TEXT_LIMIT)}] if out else []
    if stripped.startswith(_HIDDEN_TAGS) or not stripped:
        return []
    if stripped.startswith("[Request interrupted"):
        return [{"k": "note", "text": tr("Unterbrochen", "Interrupted")}]
    return [{"k": "user", "text": stripped}]


def _uid(uuid, n: int):
    """A stable anchor for notes: the entry's uuid plus the item's place inside that entry."""
    return f"{uuid}#{n}" if uuid else None


def _render_entry(entry: dict, items: list, tools: dict):
    """Add the display items of one transcript entry; tool results go into their tool's item."""
    kind, ts = entry.get("type"), entry.get("timestamp")
    uuid = entry.get("uuid")
    if kind == "system" and entry.get("subtype") == "compact_boundary":
        items.append({"k": "divider", "text": tr("Kontext komprimiert", "Context compacted"), "ts": ts})
        return
    if kind not in ("user", "assistant"):
        return
    content = (entry.get("message") or {}).get("content")
    if kind == "user":
        if entry.get("isCompactSummary"):
            items.append({"k": "divider", "text": tr("Kontext komprimiert", "Context compacted"), "ts": ts})
            return
        if entry.get("isMeta"):
            return
        if isinstance(content, str):
            for n, item in enumerate(_user_string_items(content)):
                item["ts"], item["uid"] = ts, _uid(uuid, n)
                items.append(item)
            return
        texts = []
        for block in content if isinstance(content, list) else ():
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_result":
                tool = tools.get(block.get("tool_use_id"))
                if tool is not None:
                    tool["result"] = _clip(_ANSI.sub("", _result_text(block.get("content"))), TOOL_TEXT_LIMIT)
                    tool["error"] = bool(block.get("is_error"))
            elif btype == "text":
                texts.extend(i for i in _user_string_items(_str(block.get("text")) or "") if i["k"] == "user")
            elif btype == "image":
                texts.append({"k": "user", "text": tr("[Bild]", "[Image]")})
        for n, item in enumerate(texts):
            item["ts"], item["uid"] = ts, _uid(uuid, n)
            items.append(item)
        return
    for n, block in enumerate(content if isinstance(content, list) else ()):
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        text = _str(block.get("text")) or ""
        thinking = _str(block.get("thinking")) or ""
        if btype == "text" and text.strip():
            items.append({"k": "assistant", "text": text, "ts": ts, "uid": _uid(uuid, n)})
        elif btype == "thinking" and thinking.strip():
            items.append({"k": "thinking", "text": _clip(thinking, TOOL_TEXT_LIMIT), "ts": ts})
        elif btype == "tool_use":
            name = _str(block.get("name")) or "Tool"
            inp = block.get("input") if isinstance(block.get("input"), dict) else {}
            tool = {"k": "tool", "name": name, "summary": _tool_summary(name, inp),
                    "input": _tool_input(name, inp), "result": None, "error": False, "ts": ts}
            tools[block.get("id")] = tool
            items.append(tool)


def render(path: str) -> dict:
    """Turn a transcript into display items for the history view."""
    items, tools = [], {}
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(_SKIP_PREFIXES) or line.startswith(_META_PREFIXES):
                continue
            entry = _loads(line)
            if entry is None or entry.get("isSidechain"):
                continue
            try:
                _render_entry(entry, items, tools)
            except (AttributeError, TypeError, ValueError):
                continue  # written by another program: skip what does not have the expected shape
    truncated = len(items) > MAX_ITEMS
    return {"items": items[-MAX_ITEMS:], "truncated": truncated}
