"""Builds/rebuilds the embedded SQLite database from schema.sql + seed_data.sql.

This is the "insert script" that loads the sample dataset. Run it directly
whenever you want a known-clean dataset:

    python -m db.init_db

Re-running it is safe — schema.sql drops and recreates every table before
seeding, so you always end up with the same 12 sample orders.

`db.connection.ensure_initialized()` also calls `build_database()`
automatically the first time the app runs against a missing database file,
so forgetting this step doesn't hard-crash the app — but this script is the
primary, explicit way to (re)seed.
"""
from pathlib import Path

from config import DB_PATH
from db.connection import get_admin_connection

_DB_DIR = Path(__file__).parent
_SCHEMA_PATH = _DB_DIR / "schema.sql"
_SEED_DATA_PATH = _DB_DIR / "seed_data.sql"


def build_database() -> None:
    schema_sql = _SCHEMA_PATH.read_text()
    seed_sql = _SEED_DATA_PATH.read_text()

    conn = get_admin_connection()
    try:
        conn.executescript(schema_sql)
        conn.executescript(seed_sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    build_database()
    print(f"Database built and seeded at {Path(DB_PATH).resolve()}")
