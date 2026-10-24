"""Full-text search over what was said in every chat (~/.clida/search.db, a cache).

The prompts and Claude's answers, as the history view shows them, go into an SQLite FTS5 table
with the trigram tokenizer: any part of a word matches, as in the sidebar's title search, so
"verbindung" finds "Datenbankverbindung". Like the chat index, each transcript is read only as
far as it grew since the last time. Without FTS5 trigrams (SQLite before 3.34) a plain table and
LIKE do the same, more slowly.
"""

import os
import re
import sqlite3
import threading
import traceback

from . import STATE_DIR
from .transcripts import _META_PREFIXES, _SKIP_PREFIXES, PROJECTS, SESSION_ID, _loads, _render_entry

DB_FILE = STATE_DIR / "search.db"
SCHEMA_VERSION = 1
MIN_TERM = 3  # trigrams: shorter words cannot be looked up
MAX_TERMS = 8
MAX_CHATS = 300
SNIPPET_BEFORE, SNIPPET_AFTER = 50, 110  # characters around the first match
_MESSAGE = (b'"type":"user"', b'"type":"assistant"')


def _snippet(text: str, terms: list) -> dict:
    """The text around the first match, with where each term stands in it: [[from, to], ...]."""
    first = min((m.start() for term in terms for m in [re.search(re.escape(term), text, re.I)] if m), default=0)
    start, end = max(0, first - SNIPPET_BEFORE), min(len(text), first + SNIPPET_AFTER)
    if start:  # not in the middle of a word
        space = text.find(" ", start, first)
        start = space + 1 if space >= 0 else start
    shown = ("…" if start else "") + " ".join(text[start:end].split()) + ("…" if end < len(text) else "")
    marks = sorted((m.start(), m.end()) for term in terms for m in re.finditer(re.escape(term), shown, re.I))
    merged = []
    for a, b in marks:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return {"text": shown, "marks": merged}


class Search:
    def __init__(self):
        self._lock = threading.Lock()
        self._db = None
        self._fts = False

    # -- the database -----------------------------------------------------------------------

    def _open(self):
        if self._db is not None:
            return self._db
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            db = self._connect()
        except sqlite3.DatabaseError:  # damaged: it is only a cache, so start over
            traceback.print_exc()
            for suffix in ("", "-wal", "-shm", "-journal"):
                try:
                    os.unlink(f"{DB_FILE}{suffix}")
                except OSError:
                    pass
            db = self._connect()
        self._db = db
        return db

    def _connect(self):
        db = sqlite3.connect(str(DB_FILE), check_same_thread=False)  # used under self._lock only
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            db.executescript("DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS msgs;")
            db.execute("CREATE TABLE files (path TEXT PRIMARY KEY, session_id TEXT, offset INTEGER, size INTEGER, mtime REAL)")
            try:
                db.execute("CREATE VIRTUAL TABLE msgs USING fts5(text, session_id UNINDEXED, uid UNINDEXED, "
                           "role UNINDEXED, ts UNINDEXED, path UNINDEXED, tokenize='trigram')")
            except sqlite3.OperationalError:  # no FTS5, or no trigram tokenizer
                db.execute("CREATE TABLE msgs (text TEXT, session_id TEXT, uid TEXT, role TEXT, ts TEXT, path TEXT)")
                db.execute("CREATE INDEX msgs_path ON msgs (path)")
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            db.commit()
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = 'msgs'").fetchone()[0]
        self._fts = "fts5" in sql.lower()
        return db

    # -- reading the transcripts --------------------------------------------------------------

    def refresh(self):
        """Take in what the transcripts gained since the last time, and drop what is gone."""
        with self._lock:
            self._refresh()

    def _refresh(self):
        db = self._open()
        known = {path: (offset, size, mtime) for path, offset, size, mtime
                 in db.execute("SELECT path, offset, size, mtime FROM files")}
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
                    self._read(db, key, path.stem, st, known.get(key))
                except Exception:  # one odd file must not stop the search
                    traceback.print_exc()
        for key in set(known) - seen:
            db.execute("DELETE FROM msgs WHERE path = ?", (key,))
            db.execute("DELETE FROM files WHERE path = ?", (key,))
        db.commit()

    def _read(self, db, key, session_id, st, known):
        offset = 0
        if known:
            old_offset, size, mtime = known
            if (size, mtime) == (st.st_size, st.st_mtime):
                return
            # Grown: read on from where it was. Shorter, or rewritten at the same size: from the start.
            if st.st_size > size and st.st_size >= old_offset:
                offset = old_offset
            else:
                db.execute("DELETE FROM msgs WHERE path = ?", (key,))
        try:
            with open(key, "rb") as f:
                f.seek(offset)
                data = f.read()
        except OSError:
            return
        end = data.rfind(b"\n") + 1  # only complete lines; the writer may be mid-line
        rows = []
        for line in data[:end].split(b"\n"):
            if (not line or line.startswith(_SKIP_PREFIXES) or line.startswith(_META_PREFIXES)
                    or not any(kind in line for kind in _MESSAGE)):
                continue
            entry = _loads(line)
            if entry is None or entry.get("isSidechain"):
                continue
            items = []
            try:
                _render_entry(entry, items, {})
            except (AttributeError, TypeError, ValueError):
                continue  # written by another program: skip what does not have the expected shape
            rows += [(item["text"], session_id, item["uid"], item["k"], item.get("ts"), key)
                     for item in items if item["k"] in ("user", "assistant") and item.get("uid")]
        if rows:
            db.executemany("INSERT INTO msgs (text, session_id, uid, role, ts, path) VALUES (?, ?, ?, ?, ?, ?)", rows)
        db.execute("INSERT OR REPLACE INTO files (path, session_id, offset, size, mtime) VALUES (?, ?, ?, ?, ?)",
                   (key, session_id, offset + end, st.st_size, st.st_mtime))
        db.commit()  # file by file: a first build of many chats keeps what it has done

    # -- searching ----------------------------------------------------------------------------

    def find(self, query: str) -> dict:
        """session id -> its best matching message: uid, role, ts, snippet, and how many match.

        Every word of three or more characters must occur in the message, in any case.
        """
        terms = [w for w in dict.fromkeys(str(query or "").lower().split()) if len(w) >= MIN_TERM][:MAX_TERMS]
        if not terms:
            return {}
        with self._lock:
            self._refresh()
            db = self._db
            if self._fts:
                where, args, order = "msgs MATCH ?", [" AND ".join('"' + w.replace('"', '""') + '"' for w in terms)], "rank"
            else:
                like = [w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for w in terms]
                where, args, order = " AND ".join(["text LIKE ? ESCAPE '\\'"] * len(terms)), [f"%{w}%" for w in like], "ts DESC"
            rows = db.execute(f"""
                SELECT session_id, uid, role, ts, text, n FROM (
                    SELECT session_id, uid, role, ts, text,
                           row_number() OVER (PARTITION BY session_id ORDER BY {order}) AS r,
                           count(*) OVER (PARTITION BY session_id) AS n
                    FROM msgs WHERE {where})
                WHERE r = 1 LIMIT ?""", (*args, MAX_CHATS)).fetchall()
        return {sid: {"uid": uid, "role": role, "ts": ts, "count": n, **_snippet(text, terms)}
                for sid, uid, role, ts, text, n in rows}
