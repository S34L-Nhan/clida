"""Index and render Claude Code transcripts (~/.claude/projects/<project>/<session>.jsonl).

Transcripts are append-only JSONL files that can grow to tens of megabytes, so the
index remembers how far it has read each file and only parses what was appended.
"""

import datetime
import difflib
import glob
import json
import os
import re
import shutil
import threading
import time
import traceback

from pathlib import Path

from . import CLAUDE_HOME, STATE_DIR
from .lru import Lru
from .settings import tr

PROJECTS = CLAUDE_HOME / "projects"
INDEX_FILE = STATE_DIR / "index.json"
INDEX_VERSION = 3
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
            # A second transcript of a chat starts with the total carried over from the first, so
            # its first figure may count again here; capped at the chat's cost, it cannot grow past it.
            cost_today = sum(min(sum(info["cost_days"].get(today, 0) for info in infos), usage_of(infos)["cost"])
                             for infos in by_id.values())
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
    # also split by local day. cost_last, last_msg and last_day carry over between incremental reads.
    return {"tokens": dict.fromkeys(USAGE_KEYS, 0), "cost": 0.0, "cost_days": {},
            "cost_last": 0.0, "last_msg": None, "last_day": None}


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
    # cost-state: the chat's running total, written now and then. A resumed chat carries it on
    # (checked with claude --resume: same total, same startTime), so only the growth counts.
    total = entry.get("totalCostUSD")
    if not isinstance(total, (int, float)):
        return
    delta = total - info["cost_last"] if total >= info["cost_last"] else total  # lower: a total that started over
    info["cost_last"] = total
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
    # Every transcript of a chat holds the running total so far, so the highest one is the chat's.
    return {"tokens": tokens, "cost": round(max(info["cost"] for info in infos), 4)}


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


FILE_HISTORY = CLAUDE_HOME / "file-history"
STEP_LINE_LIMIT = 400  # per tool call
NET_LINE_LIMIT = 3000  # per file
LATER_NO_TTL = 5  # seconds a "no later backups" answer is kept
NET_SIZE_LIMIT = 512 * 1024  # larger files get no diff: difflib grows fast with size
_EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
_SNAPSHOT = b'{"type":"file-history-snapshot"'


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


def changes(path: str) -> dict:
    """The files a transcript changed with its edit tools, each with the steps that changed it.

    Only tool calls that succeeded count. "backup" is the file's name in the CLI's file history
    (~/.claude/file-history/<session>/<backup>@v<n>, what /rewind restores from), if it kept one.
    """
    files, calls, tracked, cwd = {}, {}, {}, None
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(_SNAPSHOT):
                # Before each turn the CLI records every file its tools touched so far: the backup's
                # name, or none while the file does not exist.
                entry = _loads(line) or {}
                snapshot = entry.get("snapshot") if isinstance(entry.get("snapshot"), dict) else {}
                backups = snapshot.get("trackedFileBackups")
                for key, backup in (backups.items() if isinstance(backups, dict) else ()):
                    name = _str((backup or {}).get("backupFileName")) if isinstance(backup, dict) else None
                    if name and "@" in name:
                        tracked[key] = name.split("@")[0]
                continue
            if line.startswith(_SKIP_PREFIXES) or line.startswith(_META_PREFIXES):
                continue
            entry = _loads(line)
            if entry is None or entry.get("isSidechain") or entry.get("type") not in ("user", "assistant"):
                continue
            cwd = cwd or _str(entry.get("cwd"))
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
                    changed = files.setdefault(target, {"path": target, "edits": 0, "created": False, "steps": []})
                    # The tool result says whether Write made the file or replaced one.
                    result = entry.get("toolUseResult") if isinstance(entry.get("toolUseResult"), dict) else {}
                    replaced = name == "Write" and result.get("type") == "update"
                    if not changed["edits"]:
                        # Newer CLIs say "create"; older transcripts say nothing, and a first Write then
                        # most likely made the file (a backup, if any, still wins: see _compare).
                        changed["created"] = name == "Write" and result.get("type") in ("create", None)
                    changed["edits"] += 1
                    for hunk in hunks:
                        cut = len(hunk) - STEP_LINE_LIMIT
                        if cut > 0:
                            hunk = hunk[:STEP_LINE_LIMIT] + ["… " + tr(f"({cut} Zeilen gekürzt)", f"({cut} lines cut)")]
                        changed["steps"].append({"tool": name, "ts": ts, "lines": hunk, "replaced": replaced})
    for changed in files.values():
        target = changed["path"]
        keys = [target] + ([os.path.relpath(target, cwd)] if cwd else [])
        changed["backup"] = next((tracked[k] for k in keys if k in tracked), None)
    return {"files": files}


def classify(data: bytes):
    """(text, note) of a file's content: note says why it gets no diff (large, binary)."""
    if len(data) > NET_SIZE_LIMIT:
        return None, "large"
    if b"\0" in data[:8192]:
        return None, "binary"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "binary"


def read_text(path):
    """(text, note) of a file on disk; (None, None) if it does not exist."""
    try:
        if os.path.getsize(path) > NET_SIZE_LIMIT:
            return None, "large"
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError:
        return None, "unreadable"
    return classify(data)


def net_diff(before: str, after: str) -> dict:
    """A unified diff with line numbers: rows of [kind, old line, new line, text], kind @ + - or space."""
    rows, added, removed = [], 0, 0
    old_no = new_no = 0
    # [2:]: without the --- and +++ file header
    for line in list(difflib.unified_diff(before.splitlines(), after.splitlines(), n=3, lineterm=""))[2:]:
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            old_no, new_no = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            rows.append(["@", None, None, line])
        elif line.startswith("+"):
            rows.append(["+", None, new_no, line[1:]])
            new_no += 1
            added += 1
        elif line.startswith("-"):
            rows.append(["-", old_no, None, line[1:]])
            old_no += 1
            removed += 1
        else:
            rows.append([" ", old_no, new_no, line[1:]])
            old_no += 1
            new_no += 1
    cut = len(rows) - NET_LINE_LIMIT
    if cut > 0:
        rows = rows[:NET_LINE_LIMIT] + [["@", None, None, tr(f"… ({cut} Zeilen gekürzt)", f"… ({cut} lines cut)")]]
    return {"rows": rows, "added": added, "removed": removed}


class ChangesCache:
    """What a chat changed, like a merge request: each file as it was before the chat against now.

    Transcripts are parsed once per size and mtime; a file's diff is kept until it changes on disk.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._parsed = {}  # transcript path -> (size, mtime, changes())
        self._nets = {}  # file path -> (key, result)
        self._laters = Lru(2000)  # (backup folder, backup) -> True once later backups were seen
        self._no_laters = Lru(2000)  # the same slot -> False, for LATER_NO_TTL

    def _parse(self, path: str) -> dict:
        try:
            st = os.stat(path)
        except OSError:
            return {"files": {}}
        with self._lock:
            hit = self._parsed.get(path)
        if hit and hit[:2] == (st.st_size, st.st_mtime):
            return hit[2]
        parsed = changes(path)
        with self._lock:
            self._parsed[path] = (st.st_size, st.st_mtime, parsed)
        return parsed

    def get(self, session_id: str, paths: list) -> list:
        """The files of a chat over all its transcripts (resuming from another folder can leave two)."""
        merged = {}
        for path in sorted(paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0):
            for changed in self._parse(path)["files"].values():
                into = merged.get(changed["path"])
                if into is None:
                    merged[changed["path"]] = {**changed, "steps": list(changed["steps"])}
                    continue
                into["edits"] += changed["edits"]
                into["steps"] += changed["steps"]
                into["backup"] = into["backup"] or changed["backup"]
        return [self._net(session_id, changed) for changed in sorted(merged.values(), key=lambda c: c["path"])]

    def _net(self, session_id: str, changed: dict) -> dict:
        path = changed["path"]
        try:
            st = os.stat(path)
            now = (st.st_size, st.st_mtime)
        except OSError:
            now = None
        first = FILE_HISTORY / session_id / f"{changed['backup']}@v1" if changed["backup"] else None
        # Which backups exist decides the result too, and the CLI cleans its file history up.
        key = (now, str(first), changed["created"], first is not None and first.exists(), self._later(first, changed))
        with self._lock:
            hit = self._nets.get(path)
        if hit and hit[0] == key:
            return {**changed, **hit[1]}
        result = self._compare(changed, first, now, later=key[-1])
        with self._lock:
            self._nets[path] = (key, result)
        return {**changed, **result}

    def _later(self, first, changed) -> bool:
        """Whether the file has backups after @v1 but not @v1: the chat created it.

        A yes holds while the session's backup folder is there (the CLI's cleanup takes the whole
        folder); a no for a few seconds only, since a backup may appear within the same second,
        which coarse folder times (/mnt on WSL) cannot tell.
        """
        if first is None or first.exists():
            return False
        if not first.parent.is_dir():
            return False
        slot = (str(first.parent), changed["backup"])
        if self._laters.get(slot, True):
            return True
        window = int(time.monotonic() // LATER_NO_TTL)
        if self._no_laters.get(slot, window) is False:
            return False
        found = bool(glob.glob(os.path.join(glob.escape(str(first.parent)), glob.escape(changed["backup"]) + "@v*")))
        if found:
            self._laters.put(slot, True, True)
        else:
            self._no_laters.put(slot, window, False)
        return found

    @staticmethod
    def _compare(changed: dict, first, now, later: bool) -> dict:
        # Before: the first backup is the file as it was before the chat's first edit. A tracked file
        # without one did not exist yet, nor did one that Write created. Else it is not known.
        # A file the chat created has later backups (@v2 …) but no @v1; once the CLI has cleaned
        # its file history up, there are none at all, and the state before is not known. (Where git
        # knows better, app.py takes git's.)
        if first is not None and first.exists():
            before, before_note = read_text(first)
            known = True  # a binary or large before is known too, it just gets no diff
        elif later or (changed["created"] and not changed["backup"]):
            before, before_note, known = None, None, True
        else:
            before, before_note, known = None, None, False
        after, after_note = read_text(changed["path"]) if now is not None else (None, None)
        exists = now is not None
        note = before_note or after_note
        if not exists:
            status = "deleted" if (before is not None or not known or before_note) else "gone"
        elif known and before is None and not before_note:
            status = "added"
        else:
            status = "modified"
        out = {"status": status, "note": note, "known": known, "net": None, "added": None, "removed": None}
        if note or not known:
            return out
        diff = net_diff(before or "", after or "")
        if exists and before is not None and not diff["rows"]:
            out["status"] = "unchanged"  # edited, and back to how it was
        out.update(net=diff["rows"], added=diff["added"], removed=diff["removed"])
        return out
