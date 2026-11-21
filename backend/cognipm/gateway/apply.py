"""Turns staged drafts into real Jira issues - the one place that happens.

Shared by the gateway's commit_changes tool (for someone driving a run by hand)
and, from Phase 5, the API's approve route, so every write path runs exactly the
same logic, guardrail check included. Nothing here prints to stdout.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx
import psycopg

from cognipm.db.audit import log_audit
from cognipm.gateway.guardrails import run_guardrails
from cognipm.gateway.jira import JiraClient, describe_error, draft_to_adf

PROVENANCE_LABEL = (
    "cognipm-drafted"  # on every issue CogniPM creates, so teammates can tell it was AI-drafted
)
_DRAFT_ID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def draft_label(change_id: str) -> str:
    """The stamp that ties a Jira issue to the draft it came from."""
    return f"cognipm-draft-{change_id}"


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
    - Is safe to retry: every issue is stamped with its draft id (a label), and before creating, Jira is asked
      whether an issue with that stamp already exists, which is how a crash between "Jira created it" and "we
      recorded it" is recovered from instead of creating a second one. Every issue also gets the label
      `cognipm-drafted` and a comment saying who approved it.
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
    was_edited = change["edited_payload"] is not None

    existing = _already_created(jira, change["id"])
    if existing is not None:
        # An earlier attempt created it but never recorded that. Adopt it: a second issue would be a duplicate.
        _record_created(conn, change["id"], existing.key)
        log_audit(
            conn,
            run_id=run_id,
            actor=actor,
            mode=mode,
            action="create_issue",
            outcome="recovered",
            detail=f"{change['kind']} draft {change['id']} already existed as {existing.key}; not created again",
        )
        return _result(change, existing.key, jira, was_edited, recovered=True)

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

    labels = list(
        dict.fromkeys([*(payload.get("labels") or []), PROVENANCE_LABEL, draft_label(change["id"])])
    )
    created = jira.create_issue(
        issue_type,
        payload["summary"],
        description=draft_to_adf(payload.get("description", ""), payload.get("acceptance_criteria")),
        parent_key=parent_key,
        labels=labels,
    )
    _record_created(conn, change["id"], created.key)
    _comment_provenance(
        jira, conn, created.key, run_id=run_id, actor=actor, mode=mode, edited=was_edited, automatic=automatic
    )
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
    return _result(change, created.key, jira, was_edited, recovered=False)


def _result(change: dict, key: str, jira: JiraClient, was_edited: bool, *, recovered: bool) -> dict:
    return {
        "change_id": change["id"],
        "kind": change["kind"],
        "issue_key": key,
        "url": f"{jira.config.base_url}/browse/{key}",
        "was_edited": was_edited,
        "recovered": recovered,
    }


def _record_created(conn: psycopg.Connection, change_id: str, issue_key: str) -> None:
    conn.execute(
        "UPDATE staged_changes SET status = 'applied', created_issue_key = %s, applied_at = %s, error = NULL "
        "WHERE id = %s",
        (issue_key, datetime.now(UTC), change_id),
    )
    conn.commit()


def _already_created(jira: JiraClient, change_id: str):
    """The issue an earlier attempt created for this draft, found by its stamp, or None.

    ponytail: Jira's search index lags a moment behind writes, so a retry made within a second or two of
    a crash can miss the issue. A retry normally comes much later (a person clicks again); close the gap
    with a Jira issue property lookup if that ever matters."""
    if not _DRAFT_ID.fullmatch(change_id):
        return None
    stamp = draft_label(change_id)
    found = jira.search_issues(f'project = {jira.config.project_key} AND labels = "{stamp}"', max_results=1)
    return next((i for i in found if stamp in i.labels), None)


def _comment_provenance(
    jira: JiraClient,
    conn: psycopg.Connection,
    issue_key: str,
    *,
    run_id: str,
    actor: str,
    mode: str | None,
    edited: bool,
    automatic: bool,
) -> None:
    """Say in Jira itself that the AI drafted this and who let it through. Best effort: the issue already
    exists, so a failed comment is recorded, not raised."""
    how = f"Created automatically by {actor}" if automatic else f"Approved by {actor}"
    text = (
        f"Drafted by CogniPM at {mode} (run {run_id}). {how}"
        f"{', with edits to the draft' if edited else ''}. The original draft is kept in the CogniPM audit log."
    )
    try:
        jira.add_comment(issue_key, text)
    except Exception as exc:  # noqa: BLE001 - see docstring
        log_audit(
            conn,
            run_id=run_id,
            actor=actor,
            mode=mode,
            action="provenance_comment",
            outcome="failed",
            detail=f"{issue_key}: {exc}",
        )
