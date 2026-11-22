"""Postgres connections. Rows come back as dicts, so queries should name their
columns (`SELECT COUNT(*) AS n ...`) rather than rely on tuple position.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import DictRow, dict_row

from cognipm.config import database_url
from cognipm.db.migrate import apply_migrations

Connection = psycopg.Connection[DictRow]


def connect(url: str | None = None) -> Connection:
    """Open a connection without touching the schema."""
    return psycopg.connect(url or database_url(), row_factory=dict_row)


def get_connection(url: str | None = None) -> Connection:
    """Open a connection, applying any pending migrations first."""
    conn = connect(url)
    apply_migrations(conn)
    return conn
