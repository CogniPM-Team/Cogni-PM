"""The Library: every issue CogniPM created in Jira, and what became of it there."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from cognipm.api.deps import get_conn, get_jira
from cognipm.api.schemas import ArtifactList, ArtifactOut
from cognipm.db.connection import Connection
from cognipm.gateway.apply import PROVENANCE_LABEL
from cognipm.gateway.jira import Issue, JiraClient

router = APIRouter(tags=["library"])

MAX_ITEMS = 500
JIRA_PAGE = 200  # how many labelled issues one Jira search returns; more than this and the rest are "unknown"

# Our own record of what was created. The approver comes from the audit row written when the issue was made
# (its detail names the draft), so it stays right even if the reviewer changes later.
CREATED = """
SELECT s.id, s.run_id, s.kind, s.created_issue_key, s.applied_at,
       COALESCE(s.edited_payload, s.payload) AS effective,
       (SELECT a.actor FROM audit_log a
         WHERE a.action = 'create_issue' AND a.detail LIKE '%%' || s.id || '%%'
         ORDER BY a.id LIMIT 1) AS approved_by
FROM staged_changes s
WHERE s.status = 'applied' AND s.created_issue_key IS NOT NULL
ORDER BY s.applied_at DESC NULLS LAST
LIMIT %s
"""


def _jira_view(jira: JiraClient) -> tuple[dict[str, Issue] | None, bool]:
    """What Jira says about everything we labelled: ({key: issue}, complete). None when Jira cannot be reached.
    One search for the whole library, not one per issue."""
    jql = f'project = {jira.config.project_key} AND labels = "{PROVENANCE_LABEL}" ORDER BY created DESC'
    try:
        found = jira.search_issues(jql, max_results=JIRA_PAGE)
    except (
        httpx.HTTPError
    ):  # a refused login, a 5xx or no network: the list still loads, without live statuses
        return None, False
    return {i.key: i for i in found}, len(found) < JIRA_PAGE


@router.get("/artifacts", response_model=ArtifactList)
def list_artifacts(
    conn: Connection = Depends(get_conn), jira: JiraClient = Depends(get_jira)
) -> ArtifactList:
    """The issues CogniPM created, newest first, each with its current status in Jira. Reads Jira; changes nothing.

    An issue Jira does not list is `missing` (deleted, or its label removed) only when the search was complete;
    otherwise, and whenever Jira cannot be reached, its state is `unknown`."""
    rows = conn.execute(CREATED, (MAX_ITEMS,)).fetchall()
    live, complete = _jira_view(jira)
    names = {
        f"human:{u['id']}": u["display_name"]
        for u in conn.execute("SELECT id, display_name FROM users").fetchall()
    }
    base = jira.config.base_url
    items = []
    for r in rows:
        key = r["created_issue_key"]
        issue = live.get(key) if live is not None else None
        state = "found" if issue else ("missing" if live is not None and complete else "unknown")
        items.append(
            ArtifactOut(
                issue_key=key,
                url=f"{base}/browse/{key}",
                title=r["effective"].get("summary", ""),
                issue_type=issue.issue_type
                if issue
                else ("Sub-task" if r["kind"] == "subtask" else r["effective"].get("issue_type", "Story")),
                run_id=r["run_id"],
                approved_by=r["approved_by"],
                approved_by_name=names.get(r["approved_by"]),
                created_at=r["applied_at"],
                jira_state=state,
                jira_status=issue.status if issue else None,
            )
        )
    return ArtifactList(items=items, jira_reachable=live is not None)
