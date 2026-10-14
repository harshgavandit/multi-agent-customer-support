"""Concept: read-only data access for mocked tools.

The mocked tools (tools/mock_tools.py) are the only callers of
`get_read_only_connection()`. That connection is opened via SQLite's URI
`mode=ro`, which makes write-safety a real, DB-enforced guarantee rather
than a coding convention: any INSERT/UPDATE/DELETE attempted through it
raises `sqlite3.OperationalError: attempt to write a readonly database`.

SQLite has no user/role system, so unlike Postgres there's no per-table
GRANT to lean on — a read-only *connection* is the strongest access
control an embedded, single-file database can offer, and it's enough for
this POC. See README for the full explanation.

The read-write connection (`get_admin_connection`) is used exclusively by
db/init_db.py to build/seed the database — nothing at runtime (tools,
agents, graphs) ever imports it.
"""
import sqlite3
from pathlib import Path

from config import DB_PATH


def get_read_only_connection() -> sqlite3.Connection:
    ensure_initialized()
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_admin_connection() -> sqlite3.Connection:
    """Read-write connection — only db/init_db.py should use this."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_initialized() -> None:
    """Bootstrap the database on first use so a student who skips the
    manual `python -m db.init_db` step doesn't just hit a crash. The
    explicit script is still the documented, primary way to (re)seed."""
    if not Path(DB_PATH).exists():
        from db.init_db import build_database

        build_database()
