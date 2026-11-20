"""Server-side guardrails: validators every write path must pass through.

Guardrails sit above the autonomy modes - they apply identically at M1, M2 and M3. An agent never
negotiates with a guardrail: the call is refused and the refusal is logged. They are validator
functions called by every write path, never a prompt instruction. Nothing here prints to stdout.

The chain runs twice for each draft: when it is proposed (gateway) and again immediately before its
Jira write (apply.py), so an approval given earlier cannot get around a rule that Jira's state, or
the rules themselves, have since changed. The second run is why each rule reads Jira's current state
instead of trusting what was true at propose time.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx
import psycopg

from cognipm.config import max_items_per_run
from cognipm.db.audit import log_audit
from cognipm.gateway.jira import Issue, JiraClient, describe_error, validate_issue_key

MILESTONE_LABEL = "milestone"
MILESTONE_ISSUE_TYPE = "Epic"

CREATE_KINDS = ("backlog_item", "task", "subtask")
# A draft is a create. Any of these keys would mean it is trying to act on an issue that already exists.
UPDATE_KEYS = ("issue_key", "key", "transition", "status", "links", "delete")
# The fields a draft can fill in. Anything else Jira requires, we cannot supply.
FILLABLE_FIELDS = ("summary", "description", "issuetype", "project", "parent", "labels")


class GuardrailViolation(Exception):
    """A write was refused by a guardrail. Carries the guardrail's name so
    callers can return a structured error rather than a bare message."""

    def __init__(self, guardrail: str, message: str):
        self.guardrail = guardrail
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class DraftContext:
    """What a guardrail may look at besides the draft itself."""

    jira: JiraClient
    conn: psycopg.Connection
    run_id: str | None
    mode: str | None
    stage: Literal["propose", "apply"]
    automatic: bool = False  # True when no human is approving this write (M3's commit_changes)
    change_id: str | None = None  # the draft's own row, once it has one (so it is not counted against itself)


# A guardrail looks at one draft and raises GuardrailViolation to refuse it. A draft is
# {"kind", "payload", "parent_change_id", "action_class"}.
Guardrail = Callable[[dict, DraftContext], None]


# ---------- the rules, cheapest first: no Jira request until the local checks pass ----------


def required_fields(draft: dict, ctx: DraftContext) -> None:
    """A draft needs a title, and a story needs acceptance criteria to be reviewable."""
    payload = draft["payload"]
    if not str(payload.get("summary", "")).strip():
        raise GuardrailViolation("required_fields", "a draft needs a non-empty summary")
    if draft["kind"] == "backlog_item" and payload.get("issue_type", "Story") == "Story":
        if not [c for c in payload.get("acceptance_criteria", []) if str(c).strip()]:
            raise GuardrailViolation(
                "required_fields", f"story {payload['summary']!r} needs at least one acceptance criterion"
            )


def create_only(draft: dict, ctx: DraftContext) -> None:
    """M2 and M3 may create new issues; a draft may never update, transition, link or delete one."""
    if draft["kind"] not in CREATE_KINDS:
        raise GuardrailViolation(
            "create_only", f"{draft['kind']!r} is not a create; only {list(CREATE_KINDS)} are allowed"
        )
    acting_on_existing = [k for k in UPDATE_KEYS if k in draft["payload"]]
    if acting_on_existing:
        raise GuardrailViolation(
            "create_only", f"a draft may only create issues, but this one carries {acting_on_existing}"
        )


def external_is_gated(draft: dict, ctx: DraftContext) -> None:
    """`external` actions need a human in every mode, M3 included: this is the floor no automation lowers."""
    if draft.get("action_class") == "external" and ctx.automatic:
        raise GuardrailViolation(
            "external_is_gated",
            "an external action must be approved by a person; it cannot be committed automatically",
        )


def max_items_per_run_rule(draft: dict, ctx: DraftContext) -> None:
    """Cap how many issues one run may stage (at propose) or create (at apply)."""
    if ctx.run_id is None:
        return
    limit = max_items_per_run()
    if ctx.stage == "propose":
        count = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM staged_changes WHERE run_id = %s AND status <> 'rejected'",
            (ctx.run_id,),
        ).fetchone()["n"]
    else:
        count = ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM staged_changes WHERE run_id = %s AND status = 'applied'", (ctx.run_id,)
        ).fetchone()["n"]
    if count >= limit:
        raise GuardrailViolation(
            "max_items_per_run", f"this run already has {count} issues; the limit is {limit} per run"
        )


def is_milestone(issue: Issue) -> bool:
    """An Epic, or any issue labelled 'milestone'."""
    return issue.issue_type == MILESTONE_ISSUE_TYPE or MILESTONE_LABEL in issue.labels


def no_milestone_date_change(draft: dict, ctx: DraftContext) -> None:
    """No agent sets a due date on a milestone (an Epic, or an issue labelled 'milestone'). Drafts do not
    normally carry a date, so this mainly stops one that tries to. No bypass at any mode."""
    payload = draft["payload"]
    has_date = payload.get("due_date") or payload.get("duedate")
    milestone = payload.get("issue_type") == MILESTONE_ISSUE_TYPE or MILESTONE_LABEL in payload.get(
        "labels", []
    )
    if has_date and milestone:
        raise GuardrailViolation(
            "no_milestone_date_change",
            "a due date on a milestone (an Epic, or a 'milestone' label) is refused at every mode",
        )


def in_project_scope(draft: dict, ctx: DraftContext) -> None:
    """Every created issue targets the configured project, including the parent it hangs under."""
    project = ctx.jira.config.project_key
    payload = draft["payload"]
    for field in ("project", "project_key"):
        if field in payload and payload[field] != project:
            raise GuardrailViolation(
                "in_project_scope", f"a draft may only target project {project}, not {payload[field]!r}"
            )
    parent_key = payload.get("parent_key")
    if parent_key and validate_issue_key(parent_key).rsplit("-", 1)[0] != project:
        raise GuardrailViolation(
            "in_project_scope",
            f"parent {parent_key} is outside project {project}; sub-tasks must stay inside it",
        )


def valid_parent(draft: dict, ctx: DraftContext) -> None:
    """A sub-task needs a parent that exists and can have children; nothing else may have one."""
    payload = draft["payload"]
    if draft["kind"] != "subtask":
        if payload.get("parent_key") or draft.get("parent_change_id"):
            raise GuardrailViolation("valid_parent", f"a {draft['kind']} cannot have a parent")
        return

    if draft.get("parent_change_id") is not None:
        parent = ctx.conn.execute(
            "SELECT run_id, kind, status FROM staged_changes WHERE id = %s", (draft["parent_change_id"],)
        ).fetchone()
        if parent is None or parent["run_id"] != ctx.run_id:
            raise GuardrailViolation("valid_parent", "the parent draft is not part of this run")
        if parent["kind"] == "subtask":
            raise GuardrailViolation("valid_parent", "a sub-task cannot be the parent of another sub-task")
        if parent["status"] == "rejected":
            raise GuardrailViolation(
                "valid_parent", "the parent draft was rejected, so its sub-tasks cannot be created"
            )
        return

    parent_key = payload.get("parent_key")
    if not parent_key:
        raise GuardrailViolation("valid_parent", "a sub-task needs a parent story")
    try:
        parent = ctx.jira.get_issue(parent_key)
    except Exception as exc:  # noqa: BLE001 - a missing or unreadable parent is the refusal, whatever the cause
        reason = describe_error(exc) if isinstance(exc, httpx.HTTPStatusError) else str(exc)
        raise GuardrailViolation(
            "valid_parent", f"parent {parent_key} could not be read from Jira: {reason}"
        ) from exc
    subtask_names = {t.name for t in ctx.jira.list_issue_types() if t.subtask}
    if parent.issue_type in subtask_names:
        raise GuardrailViolation(
            "valid_parent", f"{parent_key} is itself a sub-task and cannot have children"
        )
    if parent.issue_type == MILESTONE_ISSUE_TYPE:
        raise GuardrailViolation(
            "valid_parent", f"{parent_key} is an Epic; a sub-task goes under a story or task"
        )


def _same_title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def no_duplicate(draft: dict, ctx: DraftContext) -> None:
    """Refuse a draft whose title matches an open issue in the project, or another draft in this run.

    ponytail: compares against the 100 most recently created open issues only, and exactly (ignoring
    case and spacing). Near-duplicates and older issues slip through; tune on real runs."""
    title = _same_title(draft["payload"].get("summary", ""))
    if not title:
        return
    if ctx.run_id is not None:
        sibling = ctx.conn.execute(
            "SELECT 1 FROM staged_changes WHERE run_id = %s AND status <> 'rejected' AND id IS DISTINCT FROM %s "
            "AND lower(regexp_replace(trim(COALESCE(edited_payload, payload)->>'summary'), '\\s+', ' ', 'g')) = %s",
            (ctx.run_id, ctx.change_id, title),
        ).fetchone()
        if sibling:
            raise GuardrailViolation(
                "no_duplicate", f"another draft in this run already has the title {title!r}"
            )
    open_issues = ctx.jira.search_issues(
        f"project = {ctx.jira.config.project_key} AND statusCategory != Done ORDER BY created DESC",
        max_results=100,
    )
    for issue in open_issues:
        if _same_title(issue.summary) == title:
            raise GuardrailViolation(
                "no_duplicate", f"{issue.key} is already open with the title {issue.summary!r}"
            )


def jira_required_fields(draft: dict, ctx: DraftContext) -> None:
    """Jira may require fields (often custom ones) that a draft cannot fill. Refuse now, with the field's
    name, instead of letting the create fail at approval time."""
    if draft["kind"] == "subtask":
        issue_type = next((t.name for t in ctx.jira.list_issue_types() if t.subtask), None)
        if issue_type is None:
            raise GuardrailViolation(
                "jira_required_fields", f"project {ctx.jira.config.project_key} has no sub-task issue type"
            )
    else:
        issue_type = draft["payload"].get("issue_type", "Story")
    missing = [f["name"] for f in ctx.jira.required_fields(issue_type) if f["key"] not in FILLABLE_FIELDS]
    if missing:
        raise GuardrailViolation(
            "jira_required_fields",
            f"Jira requires {', '.join(missing)} to create a {issue_type} in {ctx.jira.config.project_key}, "
            "and a draft cannot fill that in; add a default for it in Jira or create these by hand",
        )


GUARDRAILS: tuple[Guardrail, ...] = (
    required_fields,
    create_only,
    external_is_gated,
    max_items_per_run_rule,
    no_milestone_date_change,
    in_project_scope,
    valid_parent,
    no_duplicate,
    jira_required_fields,
)


def run_guardrails(
    draft: dict,
    *,
    jira: JiraClient,
    conn: psycopg.Connection,
    run_id: str | None,
    actor: str,
    mode: str | None,
    stage: Literal["propose", "apply"],
    automatic: bool = False,
    change_id: str | None = None,
) -> None:
    """Run the whole chain. The first refusal is logged (with the guardrail's name) and re-raised, so the
    refusal is on record even though the caller never gets to continue."""
    ctx = DraftContext(
        jira=jira, conn=conn, run_id=run_id, mode=mode, stage=stage, automatic=automatic, change_id=change_id
    )
    for guardrail in GUARDRAILS:
        try:
            guardrail(draft, ctx)
        except GuardrailViolation as violation:
            log_audit(
                conn,
                run_id=run_id,
                actor=actor,
                mode=mode,
                action=f"guardrail:{violation.guardrail}",
                outcome="refused",
                detail=f"[{stage}] {violation.message}",
            )
            raise


def check_no_milestone_date_change(
    conn: psycopg.Connection,
    issue: Issue,
    *,
    run_id: str | None,
    actor: str,
    mode: str | None,
) -> None:
    """The milestone rule for a write path that changes an EXISTING issue's due date (none exists yet:
    M3 automations may add one in Phase 8). Call it with the issue as Jira has it now, first."""
    if not is_milestone(issue):
        return

    log_audit(
        conn,
        run_id=run_id,
        actor=actor,
        mode=mode,
        action="guardrail:no_milestone_date_change",
        outcome="refused",
        detail=(
            f"refused due-date change on {issue.key}: "
            f"issue_type={issue.issue_type!r}, labels={issue.labels!r}"
        ),
    )
    raise GuardrailViolation(
        guardrail="no_milestone_date_change",
        message=(
            f"{issue.key} is a milestone (issue_type={issue.issue_type}, "
            f"labels={issue.labels}); due-date changes are refused at every mode."
        ),
    )
