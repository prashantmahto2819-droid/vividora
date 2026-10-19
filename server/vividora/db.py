"""SQLite storage. One file in the data folder, WAL mode, no server to run.

Every row's JSON columns are stored as text and decoded by `row()`.
Everything belongs to a workspace (one brand / channel) so Vividora can be
offered to other creators later without a rewrite.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings

JSON_COLS = {"settings", "meta", "transcript", "edl", "payload", "result", "detail", "kinds", "info", "secrets"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, settings TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'editor', active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, last_login_at TEXT);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  created_by TEXT, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'talking_head',
  language TEXT NOT NULL DEFAULT 'hi', status TEXT NOT NULL DEFAULT 'uploading', status_note TEXT,
  meta TEXT NOT NULL DEFAULT '{}', transcript TEXT, edl TEXT, settings TEXT NOT NULL DEFAULT '{}',
  approved_by TEXT, approved_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS projects_ws ON projects(workspace_id, updated_at);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, label TEXT, path TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0, mime TEXT,
  meta TEXT NOT NULL DEFAULT '{}', archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS assets_project ON assets(project_id, kind);
CREATE TABLE IF NOT EXISTS uploads (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT NOT NULL, size INTEGER NOT NULL, received INTEGER NOT NULL DEFAULT 0,
  path TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', payload TEXT NOT NULL DEFAULT '{}',
  result TEXT, error TEXT, progress INTEGER NOT NULL DEFAULT 0, message TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, worker TEXT, created_at TEXT NOT NULL,
  started_at TEXT, heartbeat_at TEXT, finished_at TEXT);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, kind, created_at);
CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id, created_at);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id TEXT NOT NULL, user_id TEXT, project_id TEXT,
  action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS activity_ws ON activity(workspace_id, created_at);
CREATE TABLE IF NOT EXISTS library (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0,
  mime TEXT, meta TEXT NOT NULL DEFAULT '{}', created_by TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS library_ws ON library(workspace_id, kind);
CREATE TABLE IF NOT EXISTS connections (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  platform TEXT NOT NULL, name TEXT NOT NULL, external_id TEXT, secrets TEXT NOT NULL DEFAULT '{}',
  meta TEXT NOT NULL DEFAULT '{}', created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS publications (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL, connection_id TEXT NOT NULL, platform TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', payload TEXT NOT NULL DEFAULT '{}', remote_id TEXT, url TEXT,
  error TEXT, created_by TEXT, created_at TEXT NOT NULL, finished_at TEXT);
CREATE INDEX IF NOT EXISTS publications_project ON publications(project_id, created_at);
CREATE TABLE IF NOT EXISTS trends (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL, url TEXT,
  score REAL NOT NULL DEFAULT 0, meta TEXT NOT NULL DEFAULT '{}', fetched_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS trends_ws ON trends(workspace_id, fetched_at);
CREATE TABLE IF NOT EXISTS ideas (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  title TEXT NOT NULL, hook TEXT, angle TEXT, outline TEXT, script TEXT, format TEXT NOT NULL DEFAULT 'short',
  status TEXT NOT NULL DEFAULT 'new', source TEXT, project_id TEXT, due_at TEXT, meta TEXT NOT NULL DEFAULT '{}',
  created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ideas_ws ON ideas(workspace_id, status, updated_at);
CREATE TABLE IF NOT EXISTS workers (
  name TEXT PRIMARY KEY, kinds TEXT NOT NULL DEFAULT '[]', info TEXT NOT NULL DEFAULT '{}',
  last_seen_at TEXT NOT NULL);
"""

_lock = threading.Lock()
_local = threading.local()


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    p = Path(settings.database_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = _connect()
    return c


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """A write transaction. BEGIN IMMEDIATE serialises writers across workers."""
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise


def row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS & d.keys():
        v = d[k]
        d[k] = json.loads(v) if isinstance(v, str) else v
    for k in ("active", "done", "archived"):
        if k in d:
            d[k] = bool(d[k])
    return d


def rows(cur) -> list[dict[str, Any]]:
    return [row(r) for r in cur.fetchall()]  # type: ignore[misc]


def enc(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return int(v)
    return v


def insert(c: sqlite3.Connection, table: str, data: dict[str, Any]) -> dict[str, Any]:
    cols = list(data)
    c.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [enc(data[k]) for k in cols],
    )
    return data


def update(c: sqlite3.Connection, table: str, id_: str, data: dict[str, Any], key: str = "id") -> int:
    if not data:
        return 0
    sets = ", ".join(f"{k} = ?" for k in data)
    cur = c.execute(f"UPDATE {table} SET {sets} WHERE {key} = ?", [*(enc(v) for v in data.values()), id_])
    return cur.rowcount


def get(table: str, id_: str, key: str = "id") -> dict[str, Any] | None:
    return row(conn().execute(f"SELECT * FROM {table} WHERE {key} = ?", (id_,)).fetchone())
