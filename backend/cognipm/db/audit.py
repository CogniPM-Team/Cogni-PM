"""Writes to audit_log. The table is append-only: a database trigger rejects
any UPDATE, DELETE or TRUNCATE (see migrations/0001_init.sql), so this holds
even for code that forgets the rule.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb


def log_audit(
    conn: psycopg.Connection,
    *,
    run_id: str | None,
    actor: str,
    mode: str | None,
    action: str,
    outcome: str,
    detail: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Append one row and commit. `before`/`after` record an edit or change as a diff."""
    conn.execute(
        "INSERT INTO audit_log (run_id, actor, mode, action, outcome, detail, before, after) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            run_id,
            actor,
            mode,
            action,
            outcome,
            detail,
            None if before is None else Jsonb(before),
            None if after is None else Jsonb(after),
        ),
    )
    conn.commit()
