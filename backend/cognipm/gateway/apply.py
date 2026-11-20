"""Turns staged drafts into real Jira issues - the one place that happens.

Shared by the gateway's commit_changes tool (for someone driving a run by hand)
and, from Phase 5, the API's approve route, so every write path runs exactly the
same logic, guardrail check included. Nothing here prints to stdout.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import psycopg

from cognipm.db.audit import log_audit
from cognipm.gateway.guardrails import run_guardrails
from cognipm.gateway.jira import JiraClient, describe_error, draft_to_adf


class ApplyFailed(RuntimeError):
    """A create was refused or failed part-way through a batch. Jira cannot roll back,
    so this says exactly what happened: which drafts became issues and which did not."""

    def __init__(self, change_id: str, reason: str, created: list[dict], not_created: list[str]):
        self.change_id = change_id
        self.reason = reason
        self.created = created
        self.not_created = not_created
        keys = [c["issue_key"] for c in created] or "none"
        super().__init__(
            f"stopped at draft {change_id}: {reason}. Created: {keys}. Not created: {not_created}"
        )


def apply_staged_changes(
    jira: JiraClient,
    conn: psycopg.Connection,
    run_id: str,
    *,
    actor: str,
    mode: str | None,
    change_ids: list[str] | None = None,
    automatic: bool = False,
) -> list[dict]:
    """Create a Jira issue for each not-yet-applied draft of `run_id` (or only `change_ids`).

    - Uses `edited_payload` when a human set one, `payload` otherwise (`payload` always
      stays what the agent proposed, so this is where "what actually happened" is decided).
    - Runs the guardrail chain on each draft immediately before its write. `automatic` says no human is
      approving this call (M3's commit_changes), which is what lets `external` actions be refused.
    - Creates parents before children, and records `created_issue_key` as it goes.
    - Refuses before writing anything if a draft's parent draft is neither in this batch
      nor already created (for example because the PM unticked it).
    - On the first failure marks that draft `failed`, stops, and raises ApplyFailed.
      Drafts already created stay created. A retry picks up `proposed` and `failed` drafts.

    Does not touch runs or approval_tokens: callers own what "done" means.
    Returns one dict per created issue: change_id, kind, issue_key, url, was_edited.
    """
    rows = conn.execute(
        "SELECT id, kind, payload, edited_payload, parent_change_id, action_class FROM staged_changes "
        "WHERE run_id = %s AND status IN ('proposed', 'failed') "
        "AND (%s::text[] IS NULL OR id = ANY(%s::text[])) ORDER BY created_at, id",
        (run_id, change_ids, change_ids),
    ).fetchall()
    batch = {r["id"]: r for r in rows}
    _require_parents_available(conn, batch)
    ordered = sorted(rows, key=lambda r: r["parent_change_id"] is not None)  # stable: parents first

    created: list[dict] = []
    for position, change in enumerate(ordered):
        pending = [c["id"] for c in ordered[position:]]
        try:
            issue = _create_one(
                jira, conn, change, run_id=run_id, actor=actor, mode=mode, automatic=automatic
            )
        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised as ApplyFailed with the full picture
            reason = describe_error(exc) if isinstance(exc, httpx.HTTPStatusError) else str(exc)
            conn.rollback()
            conn.execute(
                "UPDATE staged_changes SET status = 'failed', error = %s WHERE id = %s",
                (reason, change["id"]),
            )
            conn.commit()
            log_audit(
                conn,
                run_id=run_id,
                actor=actor,
                mode=mode,
                action="create_issue",
                outcome="failed",
                detail=f"{change['kind']} draft {change['id']}: {reason}",
            )
            raise ApplyFailed(change["id"], reason, created, pending) from exc
        created.append(issue)
    return created


def _require_parents_available(conn: psycopg.Connection, batch: dict[str, dict]) -> None:
    for change in batch.values():
        parent_id = change["parent_change_id"]
        if parent_id is None or parent_id in batch:
            continue
        parent = conn.execute(
            "SELECT status, created_issue_key FROM staged_changes WHERE id = %s", (parent_id,)
        ).fetchone()
        if parent is None or parent["created_issue_key"] is None:
            raise ValueError(
                f"draft {change['id']} needs its parent draft {parent_id}, which is not part of this batch "
                f"and has not been created in Jira; nothing was written"
            )


def _create_one(
    jira: JiraClient,
    conn: psycopg.Connection,
    change: dict,
    *,
    run_id: str,
    actor: str,
    mode: str | None,
    automatic: bool,
) -> dict:
    payload = change["edited_payload"] if change["edited_payload"] is not None else change["payload"]
    run_guardrails(
        {
            "kind": change["kind"],
            "payload": payload,
            "parent_change_id": change["parent_change_id"],
            "action_class": change["action_class"],
        },
        jira=jira,
        conn=conn,
        run_id=run_id,
        actor=actor,
        mode=mode,
        stage="apply",
        automatic=automatic,
        change_id=change["id"],
    )

    if change["kind"] == "subtask":
        # The sub-task type's name varies per site, so find it by its flag, not by name.
        issue_type = next((t.name for t in jira.list_issue_types() if t.subtask), None)
        if issue_type is None:
            raise ValueError("this Jira project has no sub-task issue type")
    else:
        issue_type = payload.get("issue_type", "Story")

    parent_key = payload.get("parent_key")
    if change["parent_change_id"] is not None:
        parent = conn.execute(
            "SELECT created_issue_key FROM staged_changes WHERE id = %s", (change["parent_change_id"],)
        ).fetchone()
        parent_key = parent["created_issue_key"]

    created = jira.create_issue(
        issue_type,
        payload["summary"],
        description=draft_to_adf(payload.get("description", ""), payload.get("acceptance_criteria")),
        parent_key=parent_key,
        labels=payload.get("labels"),
    )
    conn.execute(
        "UPDATE staged_changes SET status = 'applied', created_issue_key = %s, applied_at = %s, error = NULL "
        "WHERE id = %s",
        (created.key, datetime.now(UTC), change["id"]),
    )
    conn.commit()
    log_audit(
        conn,
        run_id=run_id,
        actor=actor,
        mode=mode,
        action="create_issue",
        outcome="created",
        detail=f"{change['kind']} draft {change['id']} -> {created.key}",
        after={"issue_key": created.key, "summary": payload["summary"]},
    )
    return {
        "change_id": change["id"],
        "kind": change["kind"],
        "issue_key": created.key,
        "url": created.url,
        "was_edited": change["edited_payload"] is not None,
    }
