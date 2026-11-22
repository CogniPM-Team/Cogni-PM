"""Applies every migrations/*.sql file once, in filename order, tracked in a
schema_migrations table. Safe to call on every startup and from several
processes at once: each migration runs inside a transaction holding an
advisory lock, so two processes can't apply the same file twice.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_ADVISORY_LOCK_ID = 727_274_001


def apply_migrations(conn: psycopg.Connection) -> list[str]:
    """Returns the filenames applied by this call (empty when already current).
    Tests build their schema through this same function, not a separate snapshot."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  filename TEXT PRIMARY KEY,"
        "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    conn.commit()

    applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_ADVISORY_LOCK_ID,))
            done = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE filename = %s", (path.name,)
            ).fetchone()
            if done:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied
