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
SCHEMA_VERSION = 2
MIN_TERM = 3  # trigrams: shorter words cannot be looked up
MAX_TERMS = 8
MAX_CHATS = 300
SNIPPET_BEFORE, SNIPPET_AFTER = 50, 110  # characters around the first match
_MESSAGE = (b'"type":"user"', b'"type":"assistant"')


def _utf16(text: str, at: int) -> int:
    """A place in text as JavaScript counts it: in UTF-16 units, where an emoji takes two."""
    return at + sum(1 for ch in text[:at] if ord(ch) > 0xFFFF)


def _snippet(text: str, terms: list) -> dict:
    """The text around the first match, with where each term stands in it: [[from, to], ...] in
    UTF-16 units, as the window slices it."""
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
    return {"text": shown, "marks": [[_utf16(shown, a), _utf16(shown, b)] for a, b in merged]}


class Search:
    def __init__(self):
        self._lock = threading.Lock()
        self._db = None
        self._fts = False
        self._failed = {}  # transcript -> (size, mtime) it failed at: not read again until it changes

    # -- the database -----------------------------------------------------------------------

    def _open(self):
        if self._db is None:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                self._db = self._connect()
            except sqlite3.DatabaseError as e:
                if not _damaged(e):
                    raise
                self._reset()
        return self._db

    def _reset(self):
        """Start over from an empty index: it is only a cache, rebuilt from the transcripts."""
        traceback.print_exc()
        if self._db is not None:
            self._db.close()
            self._db = None
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                os.unlink(f"{DB_FILE}{suffix}")
            except OSError:
                pass
        self._db = self._connect()

    def _connect(self):
        db = sqlite3.connect(str(DB_FILE), check_same_thread=False)  # used under self._lock only
        # A cache, rebuilt if lost: no waiting for the disk on every transcript's commit (ten times
        # faster for a first build of thousands of chats).
        db.execute("PRAGMA synchronous = OFF")
        # SQLite's own lower() and LIKE fold ASCII only; the plain table's search needs Ä and ä alike.
        db.create_function("pylower", 1, lambda text: text.lower() if isinstance(text, str) else text,
                           deterministic=True)
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            db.executescript("DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS msgs; DROP TABLE IF EXISTS spans;")
            # tail: the bytes before offset, to tell a file that grew from one written anew and longer.
            db.execute("CREATE TABLE files (path TEXT PRIMARY KEY, offset INTEGER, size INTEGER, mtime REAL, tail BLOB)")
            # Which rows each transcript gave, by rowid: a delete by path alone would read the whole
            # table, where path is not indexed.
            db.execute("CREATE TABLE spans (path TEXT, first INTEGER, last INTEGER)")
            db.execute("CREATE INDEX spans_path ON spans (path)")
            try:
                db.execute("CREATE VIRTUAL TABLE msgs USING fts5(text, session_id UNINDEXED, uid UNINDEXED, "
                           "role UNINDEXED, ts UNINDEXED, path UNINDEXED, tokenize='trigram')")
            except sqlite3.OperationalError:  # no FTS5, or no trigram tokenizer
                db.execute("CREATE TABLE msgs (text TEXT, session_id TEXT, uid TEXT, role TEXT, ts TEXT, path TEXT)")
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            db.commit()
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = 'msgs'").fetchone()[0]
        self._fts = "fts5" in sql.lower()
        return db

    def _guarded(self, work):
        """work(), and once more on an index made anew if the file turns out damaged."""
        try:
            return work()
        except sqlite3.DatabaseError as e:
            if not _damaged(e):
                raise
            self._reset()
            return work()

    # -- reading the transcripts --------------------------------------------------------------

    def refresh(self):
        """Take in what the transcripts gained since the last time, and drop what is gone."""
        with self._lock:
            self._guarded(self._refresh)

    def _refresh(self):
        db = self._open()
        known = {path: (offset, size, mtime, tail) for path, offset, size, mtime, tail
                 in db.execute("SELECT path, offset, size, mtime, tail FROM files")}
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
                if self._failed.get(key) == (st.st_size, st.st_mtime):
                    continue
                try:
                    self._read(db, key, path.stem, st, known.get(key))
                except Exception as e:  # one odd file must not stop the search
                    if isinstance(e, sqlite3.DatabaseError) and _damaged(e):
                        raise
                    db.rollback()  # none of it half taken in
                    self._failed[key] = (st.st_size, st.st_mtime)  # again once it changes
                    traceback.print_exc()
        for key in set(known) - seen:
            self._drop(db, key)
            db.execute("DELETE FROM files WHERE path = ?", (key,))
        db.commit()

    @staticmethod
    def _drop(db, key):
        for first, last in db.execute("SELECT first, last FROM spans WHERE path = ?", (key,)).fetchall():
            db.execute("DELETE FROM msgs WHERE rowid BETWEEN ? AND ?", (first, last))
        db.execute("DELETE FROM spans WHERE path = ?", (key,))

    def _read(self, db, key, session_id, st, known):
        offset = 0
        try:
            f = open(key, "rb")
        except OSError:
            return
        with f:
            if known:
                old_offset, size, mtime, tail = known
                if (size, mtime) == (st.st_size, st.st_mtime):
                    return
                # Grown: read on from where it was, if the bytes before that place are still the
                # same. Shorter, or written anew: from the start.
                if st.st_size > size:
                    f.seek(old_offset - len(tail or b""))
                    if f.read(len(tail or b"")) == (tail or b""):
                        offset = old_offset
                if not offset:
                    self._drop(db, key)
            f.seek(offset)
            # Line by line, in batches: a transcript can be hundreds of MB.
            read, last, rows = 0, b"", []
            for line in f:
                if not line.endswith(b"\n"):
                    break  # only complete lines; the writer may be mid-line
                read += len(line)
                last = line[-64:] if len(line) >= 64 else (last + line)[-64:]
                rows += self._rows(line[:-1], session_id, key)
                if len(rows) >= 500:
                    self._insert(db, key, rows)
                    rows = []
            self._insert(db, key, rows)
        tail = last if read else (known[3] if known and offset else b"")
        db.execute("INSERT OR REPLACE INTO files (path, offset, size, mtime, tail) VALUES (?, ?, ?, ?, ?)",
                   (key, offset + read, st.st_size, st.st_mtime, tail))
        db.commit()  # file by file: a first build of many chats keeps what it has done

    @staticmethod
    def _rows(line: bytes, session_id: str, key: str) -> list:
        if (not line or line.startswith(_SKIP_PREFIXES) or line.startswith(_META_PREFIXES)
                or not any(kind in line for kind in _MESSAGE)):
            return []
        entry = _loads(line)
        if entry is None or entry.get("isSidechain"):
            return []
        items = []
        try:
            _render_entry(entry, items, {})
        except (AttributeError, TypeError, ValueError):
            return []  # written by another program: skip what does not have the expected shape
        # Written by another program: a lone surrogate (half an emoji) cannot be stored, a
        # timestamp may be anything.
        return [(item["text"].encode("utf-8", "replace").decode(), session_id, item["uid"], item["k"],
                 item.get("ts") if isinstance(item.get("ts"), str) else None, key)
                for item in items if item["k"] in ("user", "assistant") and item.get("uid")]

    @staticmethod
    def _insert(db, key, rows):
        if not rows:
            return
        first = (db.execute("SELECT max(rowid) FROM msgs").fetchone()[0] or 0) + 1
        db.executemany("INSERT INTO msgs (rowid, text, session_id, uid, role, ts, path) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       [(first + n, *row) for n, row in enumerate(rows)])
        db.execute("INSERT INTO spans (path, first, last) VALUES (?, ?, ?)", (key, first, first + len(rows) - 1))

    # -- searching ----------------------------------------------------------------------------

    def find(self, query: str, paths=None):
        """session id -> its best matching message: uid, role, ts, snippet, and how many match;
        None while the index is being built (the first time, that reads every transcript).

        Every word of three or more characters must occur in the message, in any case; shorter
        ones cannot be looked up. paths: only these transcripts (the ones the history shows).
        The chats with the newest matches first, at most MAX_CHATS of them.
        """
        query = str(query or "").replace("\0", "")  # SQLite ends a string there
        terms = [w for w in dict.fromkeys(query.lower().split()) if len(w) >= MIN_TERM][:MAX_TERMS]
        if not terms:
            return {}
        if not self._lock.acquire(timeout=0.5):
            return None  # a search waiting for the build would hold one of the window's connections
        try:
            rows = self._guarded(lambda: self._find(terms, paths))
        finally:
            self._lock.release()
        return {sid: {"uid": uid, "role": role, "ts": ts, "count": n, **_snippet(text, terms)}
                for sid, uid, role, ts, text, n in rows}

    def _find(self, terms, paths):
        self._refresh()
        db = self._db
        if self._fts:
            where, args, order = "msgs MATCH ?", [" AND ".join('"' + w.replace('"', '""') + '"' for w in terms)], "rank"
        else:
            like = [w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for w in terms]
            where = " AND ".join(["pylower(text) LIKE ? ESCAPE '\\'"] * len(terms))
            args, order = [f"%{w}%" for w in like], "ts DESC"
        if paths is not None:
            db.execute("CREATE TEMP TABLE IF NOT EXISTS shown (path TEXT PRIMARY KEY)")
            db.execute("DELETE FROM shown")
            db.executemany("INSERT OR IGNORE INTO shown (path) VALUES (?)", [(p,) for p in paths])
            where += " AND path IN (SELECT path FROM shown)"
        if sqlite3.sqlite_version_info < (3, 25):  # no window functions: grouped here
            found = db.execute(f"SELECT session_id, uid, role, ts, text FROM msgs WHERE {where} ORDER BY {order} "
                               "LIMIT 20000", args).fetchall()
            best, counts, newest = {}, {}, {}
            for row in found:
                best.setdefault(row[0], row)
                counts[row[0]] = counts.get(row[0], 0) + 1
                newest[row[0]] = max(newest.get(row[0]) or "", row[3] or "")
            order_by = sorted(best, key=lambda sid: newest[sid], reverse=True)[:MAX_CHATS]
            return [(*best[sid], counts[sid]) for sid in order_by]
        return db.execute(f"""
            SELECT session_id, uid, role, ts, text, n FROM (
                SELECT session_id, uid, role, ts, text,
                       row_number() OVER (PARTITION BY session_id ORDER BY {order}) AS r,
                       count(*) OVER (PARTITION BY session_id) AS n,
                       max(ts) OVER (PARTITION BY session_id) AS newest
                FROM msgs WHERE {where})
            WHERE r = 1 ORDER BY newest DESC LIMIT ?""", (*args, MAX_CHATS)).fetchall()


def _damaged(error) -> bool:
    """A file that is no index (or no longer one): not a passing trouble like a lock, nor a value
    that could not be stored."""
    if isinstance(error, (sqlite3.OperationalError, sqlite3.ProgrammingError, sqlite3.IntegrityError,
                          sqlite3.InterfaceError)):
        # Also an index made by a newer SQLite than this one: "no such tokenizer: trigram" on every
        # use (on macOS the shortcut may start another python3 than the terminal does).
        return any(sign in str(error) for sign in ("malformed", "not a database", "no such tokenizer", "no such module"))
    return isinstance(error, sqlite3.DatabaseError)
