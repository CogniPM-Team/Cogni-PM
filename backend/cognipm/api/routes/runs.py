"""Runs and their drafts: start one, follow it, and make the human decisions on it.

Approving, rejecting and rerunning happen here, in the API process. The gateway has no tool for any of
them, which is the point: a person clicking Approve is what creates issues in Jira.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from cognipm.api import review
from cognipm.api.deps import conn_factory, get_conn, get_jira, get_run_options
from cognipm.api.launcher import StartFailed, start_task_run
from cognipm.api.schemas import (
    ApplyProblem,
    ApproveBody,
    ApproveResult,
    ChangeEdit,
    CreatedIssue,
    DraftOut,
    ParentStory,
    RejectBody,
    RejectResult,
    RerunBody,
    RerunResult,
    RunDetail,
    RunList,
    RunSummary,
    SourceSpan,
    StartedRun,
    StartRunBody,
    StepOut,
)
from cognipm.config import HUMAN_ACTOR
from cognipm.db.audit import log_audit
from cognipm.db.connection import Connection
from cognipm.gateway.apply import ApplyFailed, apply_staged_changes
from cognipm.gateway.jira import InvalidIssueKey, JiraClient, validate_issue_key
from cognipm.gateway.server import issue_approval_token

router = APIRouter(tags=["runs"])

POLL_SECONDS = 0.5  # how often the event stream looks for new steps
DECIDABLE = ("awaiting_review", "failed")  # a failed run can be approved again to create what is left
_RUN_COLUMNS = (
    "r.id, r.mode, r.task_type, r.status, r.scope, r.agent, r.created_at, r.ready_at, r.decided_at, r.comment, "
    "r.rerun_of, r.model, r.input_tokens, r.output_tokens, "
    "(SELECT COUNT(*) FROM staged_changes c WHERE c.run_id = r.id) AS draft_count"
)


# ---------- shared pieces ----------


def _get_run(conn: Connection, run_id: str) -> dict:
    run = conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,)).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@contextmanager
def _run_lock(conn: Connection, run_id: str):
    """Only one decision on a run at a time. Two clicks on Approve, or two browser tabs, would otherwise
    both pass the status check. A session lock survives the commits apply makes along the way."""
    conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (run_id,))
    conn.commit()
    try:
        yield
    finally:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (run_id,))
        conn.commit()


def _pending(conn: Connection, run_id: str) -> list[dict]:
    return conn.execute(
        "SELECT id, kind, payload, edited_payload, parent_change_id FROM staged_changes "
        "WHERE run_id = %s AND status IN ('proposed', 'failed') ORDER BY created_at, id",
        (run_id,),
    ).fetchall()


def _draft_out(row: dict, input_text: str | None, jira: JiraClient) -> DraftOut:
    effective = row["edited_payload"] if row["edited_payload"] is not None else row["payload"]
    spans = []
    for quote in row["sources"]:
        found = review.source_span(input_text, quote)
        spans.append(
            SourceSpan(quote=quote, start=found[0] if found else None, end=found[1] if found else None)
        )
    key = row["created_issue_key"]
    return DraftOut(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        payload=row["payload"],
        edited_payload=row["edited_payload"],
        effective=effective,
        parent_change_id=row["parent_change_id"],
        sources=spans,
        reasoning=row["reasoning"],
        assumptions=row["assumptions"],
        action_class=row["action_class"],
        created_issue_key=key,
        issue_url=f"{jira.config.base_url}/browse/{key}" if key else None,
        error=row["error"],
    )


def _parent_story(jira: JiraClient, key: str | None) -> ParentStory | None:
    """The story a P2 run was asked to break down. Best effort: the review still works if Jira is unreachable."""
    if not key:
        return None
    try:
        issue = jira.get_issue(key)
    except Exception:  # noqa: BLE001 - see docstring
        return None
    return ParentStory(
        key=issue.key, summary=issue.summary, status=issue.status, url=f"{jira.config.base_url}/browse/{key}"
    )


# ---------- starting and following a run ----------


@router.post("/runs", response_model=StartedRun, status_code=202)
async def start_run(
    body: StartRunBody,
    jira: JiraClient = Depends(get_jira),
    open_connection=Depends(conn_factory),
    options: dict = Depends(get_run_options),
) -> StartedRun:
    """Start a run in M2. Returns as soon as the run exists; follow it through /runs/{id}/events."""
    if body.task == "p1" and not (body.input_text or "").strip():
        raise HTTPException(
            status_code=422, detail="p1 needs input_text: the notes or requirements to draft from"
        )
    if body.task == "p2":
        try:
            validate_issue_key(body.story_key or "")
        except InvalidIssueKey as exc:
            raise HTTPException(
                status_code=422, detail="p2 needs story_key: the story to break down"
            ) from exc
    try:
        run_id = await start_task_run(
            open_connection=open_connection,
            options=options["task"],
            task=body.task,
            input_text=body.input_text or "",
            story_key=body.story_key,
            context_jql=f"project = {jira.config.project_key} ORDER BY created DESC"
            if body.task == "p1"
            else None,
            instructions=body.instructions,
        )
    except StartFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return StartedRun(run_id=run_id)


@router.get("/runs", response_model=RunList)
def list_runs(conn: Connection = Depends(get_conn)) -> RunList:
    """The decision inbox: runs waiting on a human first (oldest first, so nothing sits forgotten), then the rest."""
    rows = conn.execute(f"SELECT {_RUN_COLUMNS} FROM runs r ORDER BY r.created_at DESC").fetchall()
    summaries = [RunSummary(**r) for r in rows]
    waiting = sorted(
        (r for r in summaries if r.status == "awaiting_review"), key=lambda r: r.ready_at or r.created_at
    )
    return RunList(
        waiting=waiting,
        past=[r for r in summaries if r.status != "awaiting_review"],
        awaiting_review_count=len(waiting),
    )


@router.get("/runs/{run_id}", response_model=RunDetail)
def show_run(
    run_id: str, conn: Connection = Depends(get_conn), jira: JiraClient = Depends(get_jira)
) -> RunDetail:
    run = _get_run(conn, run_id)
    summary = RunSummary(
        **conn.execute(f"SELECT {_RUN_COLUMNS} FROM runs r WHERE r.id = %s", (run_id,)).fetchone()
    )
    rows = conn.execute(
        "SELECT * FROM staged_changes WHERE run_id = %s ORDER BY created_at, id", (run_id,)
    ).fetchall()
    steps = conn.execute("SELECT * FROM run_steps WHERE run_id = %s ORDER BY id", (run_id,)).fetchall()
    pending = [r for r in rows if r["status"] in ("proposed", "failed")]
    decided, ready = run["decided_at"], run["ready_at"]
    return RunDetail(
        run=summary,
        input_text=run["input_text"],
        instructions=run["instructions"],
        story_key=run["story_key"],
        parent_story=_parent_story(jira, run["story_key"]),
        drafts=[_draft_out(r, run["input_text"], jira) for r in rows],
        steps=[StepOut(**s) for s in steps],
        status_note=review.status_note(run["status"], pending=len(pending)),
        editable=run["status"] == "awaiting_review",
        can_decide=run["status"] in DECIDABLE and bool(pending),
        seconds_to_decision=(decided - ready).total_seconds() if decided and ready else None,
    )


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str, request: Request, open_connection=Depends(conn_factory), conn: Connection = Depends(get_conn)
) -> StreamingResponse:
    """Server-Sent Events: each step of the run as it is recorded, then an `end` event once it is no longer
    running. Reconnecting with Last-Event-ID resumes where the stream left off."""
    _get_run(conn, run_id)
    last = int(request.headers.get("last-event-id") or 0)

    async def stream() -> AsyncIterator[str]:
        events = open_connection()
        position = last
        try:
            while True:
                rows = events.execute(
                    "SELECT * FROM run_steps WHERE run_id = %s AND id > %s ORDER BY id", (run_id, position)
                ).fetchall()
                status = events.execute("SELECT status FROM runs WHERE id = %s", (run_id,)).fetchone()[
                    "status"
                ]
                events.commit()  # end the read transaction, or later polls would not see new rows
                for row in rows:
                    position = row["id"]
                    yield f"id: {position}\nevent: step\ndata: {StepOut(**row).model_dump_json()}\n\n"
                if status != "running" and not rows:
                    yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                    return
                await asyncio.sleep(POLL_SECONDS)
        finally:
            events.close()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------- the PM's decisions ----------


@router.patch("/changes/{change_id}", response_model=DraftOut)
def edit_draft(
    change_id: str,
    body: ChangeEdit,
    conn: Connection = Depends(get_conn),
    jira: JiraClient = Depends(get_jira),
) -> DraftOut:
    """Edit a draft before approving it. The agent's original stays in `payload`; the PM's version is
    `edited_payload`, and the audit log records exactly what changed."""
    change = conn.execute(
        "SELECT c.*, r.status AS run_status, r.mode AS run_mode, r.input_text FROM staged_changes c "
        "JOIN runs r ON r.id = c.run_id WHERE c.id = %s",
        (change_id,),
    ).fetchone()
    if change is None:
        raise HTTPException(status_code=404, detail="draft not found")
    if change["run_status"] != "awaiting_review" or change["status"] != "proposed":
        raise HTTPException(status_code=409, detail="this draft can no longer be edited")
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=422, detail="nothing to change")
    if change["kind"] == "subtask" and {"issue_type", "acceptance_criteria"} & fields.keys():
        raise HTTPException(
            status_code=422, detail="a sub-task has no issue type or acceptance criteria to edit"
        )
    for name in ("acceptance_criteria", "labels"):
        if name in fields:
            fields[name] = [item.strip() for item in fields[name] if item.strip()]

    current = change["edited_payload"] if change["edited_payload"] is not None else change["payload"]
    updated = {**current, **fields}
    stored = (
        None if updated == change["payload"] else updated
    )  # back to the agent's version means "not edited"
    conn.execute(
        "UPDATE staged_changes SET edited_payload = %s WHERE id = %s",
        (None if stored is None else json.dumps(stored), change_id),
    )
    conn.commit()
    log_audit(
        conn,
        run_id=change["run_id"],
        actor=HUMAN_ACTOR,
        mode=change["run_mode"],
        action="edit_draft",
        outcome="edited",
        detail=f"{change['kind']} {change_id}: changed {sorted(fields)}",
        before={k: current.get(k) for k in fields},
        after=fields,
    )
    row = conn.execute("SELECT * FROM staged_changes WHERE id = %s", (change_id,)).fetchone()
    return _draft_out(row, change["input_text"], jira)


@router.post("/runs/{run_id}/approve", response_model=ApproveResult, responses={502: {"model": ApplyProblem}})
def approve_run(
    run_id: str,
    body: ApproveBody | None = None,
    conn: Connection = Depends(get_conn),
    jira: JiraClient = Depends(get_jira),
) -> ApproveResult:
    """Create the ticked drafts in Jira. Drafts left out are dropped, not created. Safe to repeat: an
    already-approved run is refused, and a run that failed part-way creates only what is left."""
    with _run_lock(conn, run_id):
        run = _get_run(conn, run_id)
        if run["status"] not in DECIDABLE:
            raise HTTPException(
                status_code=409, detail=f"this run is {run['status']}; it cannot be approved again"
            )
        pending = _pending(conn, run_id)
        pending_ids = {p["id"] for p in pending}
        chosen = (
            list(pending_ids)
            if body is None or body.change_ids is None
            else list(dict.fromkeys(body.change_ids))
        )
        if unknown := set(chosen) - pending_ids:
            raise HTTPException(status_code=422, detail=f"not pending drafts of this run: {sorted(unknown)}")
        if not chosen:
            raise HTTPException(status_code=400, detail="choose at least one draft to create")
        _require_parents_chosen(conn, pending, set(chosen))

        dropped = sorted(pending_ids - set(chosen))
        for change_id in dropped:
            conn.execute("UPDATE staged_changes SET status = 'rejected' WHERE id = %s", (change_id,))
            conn.commit()
            log_audit(
                conn,
                run_id=run_id,
                actor=HUMAN_ACTOR,
                mode=run["mode"],
                action="drop_draft",
                outcome="dropped",
                detail=f"draft {change_id} left out at approval",
            )

        token = issue_approval_token(conn, run_id)
        try:
            created = apply_staged_changes(
                jira, conn, run_id, actor=HUMAN_ACTOR, mode=run["mode"], change_ids=chosen
            )
        except ApplyFailed as failure:
            conn.execute("UPDATE runs SET status = 'failed' WHERE id = %s", (run_id,))
            conn.commit()
            log_audit(
                conn,
                run_id=run_id,
                actor=HUMAN_ACTOR,
                mode=run["mode"],
                action="approve",
                outcome="failed",
                detail=str(failure),
            )
            raise HTTPException(
                status_code=502,
                detail=ApplyProblem(
                    message=str(failure),
                    created=[CreatedIssue(**c) for c in failure.created],
                    not_created=failure.not_created,
                ).model_dump(),
            ) from failure

        conn.execute(
            "UPDATE approval_tokens SET consumed_at = %s WHERE token = %s", (datetime.now(UTC), token)
        )
        conn.execute("UPDATE runs SET status = 'applied', decided_at = now() WHERE id = %s", (run_id,))
        conn.commit()
        edited = [c["issue_key"] for c in created if c["was_edited"]]
        detail = f"{len(created)} issue(s) created: {[c['issue_key'] for c in created]}"
        if edited:
            detail += f"; edited by the PM: {edited}"
        if dropped:
            detail += f"; {len(dropped)} draft(s) left out"
        log_audit(
            conn,
            run_id=run_id,
            actor=HUMAN_ACTOR,
            mode=run["mode"],
            action="approve",
            outcome="applied",
            detail=detail,
        )
        return ApproveResult(
            run_id=run_id,
            status="applied",
            created=[
                CreatedIssue(**{k: c[k] for k in ("change_id", "issue_key", "url", "recovered")})
                for c in created
            ],
            dropped=dropped,
        )


def _require_parents_chosen(conn: Connection, pending: list[dict], chosen: set[str]) -> None:
    """A sub-task cannot be created without its parent: refuse before anything is written or dropped."""
    for draft in pending:
        parent_id = draft["parent_change_id"]
        if draft["id"] not in chosen or parent_id is None or parent_id in chosen:
            continue
        parent = conn.execute(
            "SELECT created_issue_key FROM staged_changes WHERE id = %s", (parent_id,)
        ).fetchone()
        if parent is None or parent["created_issue_key"] is None:
            title = (draft["edited_payload"] or draft["payload"]).get("summary", draft["id"])
            raise HTTPException(
                status_code=400,
                detail=f"{title!r} is a sub-task of a draft you did not tick; tick the parent too, or untick this one",
            )


@router.post("/runs/{run_id}/reject", response_model=RejectResult)
def reject_run(
    run_id: str, body: RejectBody | None = None, conn: Connection = Depends(get_conn)
) -> RejectResult:
    """Send the run back. Nothing is created in Jira; the note is kept as feedback."""
    comment = body.comment if body else ""
    with _run_lock(conn, run_id):
        run = _get_run(conn, run_id)
        if run["status"] not in DECIDABLE:
            raise HTTPException(status_code=409, detail=f"this run is {run['status']}; it cannot be rejected")
        conn.execute(
            "UPDATE staged_changes SET status = 'rejected' WHERE run_id = %s AND status IN ('proposed', 'failed')",
            (run_id,),
        )
        conn.execute(
            "UPDATE runs SET status = 'rejected', comment = %s, decided_at = now() WHERE id = %s",
            (comment, run_id),
        )
        conn.commit()
        log_audit(
            conn,
            run_id=run_id,
            actor=HUMAN_ACTOR,
            mode=run["mode"],
            action="reject",
            outcome="rejected",
            detail=comment or None,
        )
    return RejectResult(run_id=run_id, status="rejected")


@router.post("/runs/{run_id}/rerun", response_model=RerunResult, status_code=202)
async def rerun(
    run_id: str,
    body: RerunBody,
    conn: Connection = Depends(get_conn),
    jira: JiraClient = Depends(get_jira),
    open_connection=Depends(conn_factory),
    options: dict = Depends(get_run_options),
) -> RerunResult:
    """Run the same task again with the PM's note as extra instruction. The old run is rejected and the new
    one records which run it replaces, so reruns chain."""
    old = _get_run(conn, run_id)
    if old["status"] not in DECIDABLE:
        raise HTTPException(status_code=409, detail=f"this run is {old['status']}; it cannot be rerun")
    if old["task_type"] == "p1" and not old["input_text"]:
        raise HTTPException(
            status_code=409, detail="the original input was not kept, so this run cannot be repeated"
        )

    earlier = f"{old['instructions']}\n\n" if old["instructions"] else ""
    try:
        new_id = await start_task_run(
            open_connection=open_connection,
            options=options["task"],
            task=old["task_type"],
            input_text=old["input_text"] or "",
            story_key=old["story_key"],
            context_jql=f"project = {jira.config.project_key} ORDER BY created DESC"
            if old["task_type"] == "p1"
            else None,
            instructions=f"{earlier}The PM rejected the previous attempt and said: {body.note}",
            rerun_of=run_id,
        )
    except StartFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with _run_lock(conn, run_id):
        conn.execute(
            "UPDATE staged_changes SET status = 'rejected' WHERE run_id = %s AND status IN ('proposed', 'failed')",
            (run_id,),
        )
        conn.execute(
            "UPDATE runs SET status = 'rejected', comment = %s, decided_at = now() WHERE id = %s",
            (f"Rerun requested: {body.note}", run_id),
        )
        conn.commit()
        log_audit(
            conn,
            run_id=run_id,
            actor=HUMAN_ACTOR,
            mode=old["mode"],
            action="rerun",
            outcome="rerun",
            detail=f"new run {new_id}: {body.note}",
        )
    return RerunResult(run_id=new_id, rerun_of=run_id)
