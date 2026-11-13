"""Schema-level guarantees: migrations are idempotent, constraints hold, and audit_log is
append-only because the database says so, not because code is careful."""

from __future__ import annotations

import psycopg
import pytest

from cognipm.db.audit import log_audit
from cognipm.db.migrate import apply_migrations


def _run(conn, run_id="r1", mode="M2"):
    conn.execute(
        "INSERT INTO runs (id, mode, task_type, agent, scope, status) VALUES (%s, %s, 'p1', 'a', 's', 'running')",
        (run_id, mode),
    )


def _draft(conn, *, kind="backlog_item", status="proposed", sources='["quote"]'):
    conn.execute(
        "INSERT INTO staged_changes (id, run_id, kind, payload, sources, reasoning, status) "
        "VALUES ('c1', 'r1', %s, '{}', %s, 'long enough reasoning here', %s)",
        (kind, sources, status),
    )


def test_migrations_are_idempotent(conn):
    assert apply_migrations(conn) == []


@pytest.mark.parametrize("mode", ["L2", "M4", "M1"])  # M1 is a real mode but never starts a run
def test_runs_reject_an_unknown_mode(conn, mode):
    with pytest.raises(psycopg.errors.CheckViolation):
        _run(conn, mode=mode)


def test_a_draft_must_cite_at_least_one_source(conn):
    _run(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _draft(conn, sources="[]")


@pytest.mark.parametrize("field,value", [("kind", "epic"), ("status", "approved")])
def test_a_draft_rejects_an_unknown_kind_and_status(conn, field, value):
    _run(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _draft(conn, **{field: value})


def test_audit_log_keeps_a_before_and_after_diff(conn):
    log_audit(
        conn,
        run_id=None,
        actor="human:reviewer",
        mode="M2",
        action="edit",
        outcome="ok",
        before={"summary": "old"},
        after={"summary": "new"},
    )

    row = conn.execute("SELECT before, after FROM audit_log").fetchone()
    assert row == {"before": {"summary": "old"}, "after": {"summary": "new"}}


def test_audit_log_rejects_update(conn):
    log_audit(conn, run_id=None, actor="gateway", mode=None, action="x", outcome="ok")

    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("UPDATE audit_log SET outcome = 'tampered'")


def test_audit_log_rejects_delete_and_truncate(conn):
    log_audit(conn, run_id=None, actor="gateway", mode=None, action="x", outcome="ok")

    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("DELETE FROM audit_log")
    conn.rollback()
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("TRUNCATE audit_log")
    conn.rollback()

    assert conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone() == {"n": 1}
