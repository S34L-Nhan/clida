"""Index and render Claude Code transcripts (~/.claude/projects/<project>/<session>.jsonl).

Transcripts are append-only JSONL files that can grow to tens of megabytes, so the
index remembers how far it has read each file and only parses what was appended.
"""

import datetime
import difflib
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
INDEX_VERSION = 2
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

_COST_STATE = b'{"type":"cost-state"'
_ASSISTANT = b'"type":"assistant"'
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")

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

    def usage(self) -> dict:
        """Usage per chat id, and the cost of today (local time) over all chats."""
        today = datetime.date.today().isoformat()
        with self._lock:
            by_id = {}
            for info in self._files.values():
                by_id.setdefault(info["id"], []).append(info)
            cost_today = sum(info["cost_days"].get(today, 0) for info in self._files.values())
        return {"chats": {sid: usage_of(infos) for sid, infos in by_id.items()}, "today": round(cost_today, 4)}

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
                "summary": None, "last_prompt": None, **_empty_usage(),
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
            is_usage = line.startswith(_COST_STATE) or (_ASSISTANT in line and not line.startswith(_SKIP_PREFIXES))
            need_head = info["first_prompt"] is None or info["cwd"] is None
            if not is_meta and not is_usage and (not need_head or line.startswith(_SKIP_PREFIXES)):
                continue
            entry = _loads(line)
            if entry is None:
                continue
            kind = entry.get("type")
            if kind in ("assistant", "cost-state"):
                try:
                    _count_usage(info, entry)
                except (AttributeError, TypeError, ValueError):
                    pass  # written by another program: skip what does not have the expected shape
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


def _empty_usage() -> dict:
    # tokens: summed over the API messages of the chat; cost: the CLI's own figure (cost-state),
    # also split by local day. cost_run, last_msg and last_day carry over between incremental reads.
    return {"tokens": dict.fromkeys(USAGE_KEYS, 0), "cost": 0.0, "cost_days": {},
            "cost_run": None, "last_msg": None, "last_day": None}


def _local_day(timestamp) -> str:
    when = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return when.astimezone().date().isoformat()


def _count_usage(info: dict, entry: dict):
    if entry["type"] == "assistant":
        if entry.get("isSidechain"):
            return
        if _str(entry.get("timestamp")):
            info["last_day"] = _local_day(entry["timestamp"])
        message = entry.get("message") or {}
        usage = message.get("usage")
        # The CLI writes one entry per content block of a message, each with the message's usage.
        if not isinstance(usage, dict) or message.get("id") == info["last_msg"]:
            return
        info["last_msg"] = message.get("id")
        for key in USAGE_KEYS:
            value = usage.get(key)
            if isinstance(value, int):
                info["tokens"][key] += value
        return
    # cost-state: the running total of one CLI process, written now and then. A resumed chat gets a
    # new process (startTime) whose total either starts at 0 or carries on from the last one.
    total, start = entry.get("totalCostUSD"), entry.get("startTime")
    if not isinstance(total, (int, float)):
        return
    run = info["cost_run"]
    if run is None or (start != run[0] and total < run[1]):
        delta = total
    else:
        delta = max(total - run[1], 0)
    info["cost_run"] = [start, total]
    if delta:
        info["cost"] += delta
        day = info["last_day"] or "?"
        info["cost_days"][day] = info["cost_days"].get(day, 0) + delta


def usage_of(infos: list) -> dict:
    """Tokens and cost of one chat, over all its transcripts."""
    tokens = dict.fromkeys(USAGE_KEYS, 0)
    for info in infos:
        for key in USAGE_KEYS:
            tokens[key] += info["tokens"][key]
    return {"tokens": tokens, "cost": round(sum(info["cost"] for info in infos), 4)}


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


DIFF_LINE_LIMIT = 400  # per tool call
_EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")


def _diff_lines(old: str, new: str) -> list:
    """The changed lines of one edit, unified-diff style without the file header."""
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), n=2, lineterm=""))[2:]
    if not lines:
        return [" " + l for l in new.splitlines()]
    # The @@ line numbers count within the edited snippet, not the file, so they would mislead.
    return [l if not l.startswith("@@") else "⋯" for l in lines[1:]]


def _edit_hunks(name: str, inp: dict) -> list:
    if name == "Edit":
        return [_diff_lines(_str(inp.get("old_string")) or "", _str(inp.get("new_string")) or "")]
    if name == "MultiEdit":
        edits = inp.get("edits") if isinstance(inp.get("edits"), list) else []
        return [_diff_lines(_str(e.get("old_string")) or "", _str(e.get("new_string")) or "")
                for e in edits if isinstance(e, dict)]
    if name == "Write":
        return [["+" + l for l in (_str(inp.get("content")) or "").splitlines()]]
    return [["+" + l for l in (_str(inp.get("new_source")) or "").splitlines()]]  # NotebookEdit


def changes(path: str) -> list:
    """The files a chat changed with its edit tools, in the order first touched, each with its diffs.

    Only tool calls that succeeded count; the diffs are what the tools did, not the file's state now.
    """
    files, calls = {}, {}
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(_SKIP_PREFIXES) or line.startswith(_META_PREFIXES):
                continue
            entry = _loads(line)
            if entry is None or entry.get("isSidechain") or entry.get("type") not in ("user", "assistant"):
                continue
            content = (entry.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else ():
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("name") in _EDIT_TOOLS:
                    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                    target = _str(inp.get("file_path")) or _str(inp.get("notebook_path"))
                    if target:
                        calls[block.get("id")] = (target, block["name"], inp, _str(entry.get("timestamp")))
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                    target, name, inp, ts = calls.pop(block["tool_use_id"])
                    if block.get("is_error"):
                        continue
                    try:
                        hunks = _edit_hunks(name, inp)
                    except (AttributeError, TypeError):
                        continue
                    changed = files.setdefault(target, {"path": target, "edits": 0, "added": 0, "removed": 0,
                                                       "created": False, "hunks": []})
                    changed["edits"] += 1
                    changed["created"] = changed["created"] or (name == "Write" and not changed["hunks"])
                    for hunk in hunks:
                        changed["added"] += sum(1 for l in hunk if l.startswith("+"))
                        changed["removed"] += sum(1 for l in hunk if l.startswith("-"))
                        cut = len(hunk) - DIFF_LINE_LIMIT
                        if cut > 0:
                            hunk = hunk[:DIFF_LINE_LIMIT] + ["… " + tr(f"({cut} Zeilen gekürzt)", f"({cut} lines cut)")]
                        changed["hunks"].append({"tool": name, "ts": ts, "lines": hunk})
    return list(files.values())
