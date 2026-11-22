"""The activity log: what happened, to what, and who let it."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from cognipm.api.deps import get_conn
from cognipm.api.schemas import AuditPage, AuditRow
from cognipm.db.connection import Connection

router = APIRouter(tags=["audit"])

# Each filter is a fixed WHERE clause; nothing the caller sends is ever placed in SQL.
FILTERS = {
    "all": "TRUE",
    "changed_jira": "action = 'create_issue' AND outcome IN ('created', 'recovered')",
    "needs_you": "run_id IN (SELECT id FROM runs WHERE status = 'awaiting_review')",
    "rejected": "action IN ('reject', 'rerun', 'drop_draft') OR outcome = 'refused'",
    "advice_only": "mode = 'M1'",
}

Filter = Literal["all", "changed_jira", "needs_you", "rejected", "advice_only"]

# Each entry with the name of the person behind it. People are recorded by id, so a rename shows everywhere.
NAMED = "a.*, u.display_name AS actor_name FROM audit_log a LEFT JOIN users u ON a.actor = 'human:' || u.id"


def _like(text: str) -> str:
    """The text as a literal ILIKE pattern: a typed % or _ must match itself, not act as a wildcard."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _where(
    filter: Filter, run_id: str | None, since: datetime | None, until: datetime | None, q: str | None
) -> tuple[str, list[object]]:
    """The WHERE clause for the list and the export, so the two can never disagree about what matches."""
    clauses = [f"({FILTERS[filter]})"]
    params: list[object] = []
    if run_id is not None:
        clauses.append("run_id = %s")
        params.append(run_id)
    if since is not None:
        clauses.append("ts >= %s")
        params.append(since)
    if until is not None:
        clauses.append("ts < %s")
        params.append(until)
    if q and q.strip():
        # The note, who and what, and the before/after of an edit (which is where a draft's title appears).
        clauses.append(
            "concat_ws(' ', detail, actor, action, before::text, after::text) ILIKE %s ESCAPE '\\'"
        )
        params.append(_like(q.strip()))
    return " AND ".join(clauses), params


@router.get("/audit", response_model=AuditPage)
def audit_log(
    filter: Filter = "all",
    run_id: str | None = None,
    since: datetime | None = Query(
        default=None, alias="from", description="Only entries at or after this time"
    ),
    until: datetime | None = Query(default=None, alias="to", description="Only entries before this time"),
    q: str | None = Query(default=None, max_length=200, description="Only entries whose text contains this"),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> AuditPage:
    """Newest first. `changed_jira`: issues that were created. `needs_you`: activity on runs awaiting review.
    `rejected`: rejections, reruns, dropped drafts and anything a guardrail refused. `advice_only`: Co-Pilot chat."""
    where, params = _where(filter, run_id, since, until, q)
    rows = conn.execute(
        f"SELECT {NAMED} WHERE {where} ORDER BY a.id DESC LIMIT %s", (*params, limit)
    ).fetchall()
    return AuditPage(filter=filter, rows=[AuditRow(**r) for r in rows])


COLUMNS = ("time", "run", "actor", "mode", "action", "outcome", "detail", "before", "after", "actor_name")


def _cell(value: object) -> str:
    """One CSV cell. A cell a spreadsheet would read as a formula is defused with a leading apostrophe: the
    detail text can contain words an agent or a document supplied. (The csv module does the quoting.)"""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/audit/export.csv", response_class=Response)
def export_audit(
    filter: Filter = "all",
    run_id: str | None = None,
    since: datetime | None = Query(default=None, alias="from"),
    until: datetime | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, max_length=200),
    conn: Connection = Depends(get_conn),
) -> Response:
    """Every matching row as CSV, oldest first: no 500-row cap, unlike the list. Same filters as the list.

    ponytail: built in memory. Fine for a study-sized log; stream it if the log reaches millions of rows."""
    where, params = _where(filter, run_id, since, until, q)
    rows = conn.execute(f"SELECT {NAMED} WHERE {where} ORDER BY a.id", params).fetchall()
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow(
            _cell(v)
            for v in (
                r["ts"].isoformat(),
                r["run_id"],
                r["actor"],
                r["mode"],
                r["action"],
                r["outcome"],
                r["detail"],
                None if r["before"] is None else json.dumps(r["before"]),
                None if r["after"] is None else json.dumps(r["after"]),
                r["actor_name"],
            )
        )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cognipm-activity.csv"'},
    )
