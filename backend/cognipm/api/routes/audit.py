"""The activity log: what happened, to what, and who let it."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

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


@router.get("/audit", response_model=AuditPage)
def audit_log(
    filter: Literal["all", "changed_jira", "needs_you", "rejected", "advice_only"] = "all",
    run_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> AuditPage:
    """Newest first. `changed_jira`: issues that were created. `needs_you`: activity on runs awaiting review.
    `rejected`: rejections, reruns, dropped drafts and anything a guardrail refused. `advice_only`: Co-Pilot chat."""
    where = FILTERS[filter]
    params: list[object] = []
    if run_id is not None:
        where = f"({where}) AND run_id = %s"
        params.append(run_id)
    rows = conn.execute(
        f"SELECT * FROM audit_log WHERE {where} ORDER BY id DESC LIMIT %s", (*params, limit)
    ).fetchall()
    return AuditPage(filter=filter, rows=[AuditRow(**r) for r in rows])
