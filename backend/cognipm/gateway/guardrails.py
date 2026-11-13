"""Server-side guardrails: validators every write path must pass through.

Guardrails sit above the autonomy modes - they apply identically at M1, M2 and
M3. An agent never negotiates with a guardrail: the call is refused and the
refusal is logged. They are validator functions called by every write path,
never a prompt instruction. Nothing here prints to stdout.

Phase 2 ships the chain empty, plus the milestone rule ported unchanged.
Phase 4 adds the create-time rules to GUARDRAILS without restructuring
apply.py or the gateway.
"""

from __future__ import annotations

from collections.abc import Callable

import psycopg

from cognipm.db.audit import log_audit
from cognipm.gateway.jira import Issue

MILESTONE_LABEL = "milestone"
MILESTONE_ISSUE_TYPE = "Epic"


class GuardrailViolation(Exception):
    """A write was refused by a guardrail. Carries the guardrail's name so
    callers can return a structured error rather than a bare message."""

    def __init__(self, guardrail: str, message: str):
        self.guardrail = guardrail
        self.message = message
        super().__init__(message)


# A guardrail looks at one draft ({"kind", "payload", ...}) and raises
# GuardrailViolation to refuse it.
Guardrail = Callable[[dict], None]
GUARDRAILS: tuple[Guardrail, ...] = ()


def run_guardrails(
    conn: psycopg.Connection, draft: dict, *, run_id: str | None, actor: str, mode: str | None
) -> None:
    """Run the whole chain. The first refusal is logged (with the guardrail's name) and re-raised,
    so the refusal is on record even though the caller never gets to continue."""
    for guardrail in GUARDRAILS:
        try:
            guardrail(draft)
        except GuardrailViolation as violation:
            log_audit(
                conn,
                run_id=run_id,
                actor=actor,
                mode=mode,
                action=f"guardrail:{violation.guardrail}",
                outcome="refused",
                detail=violation.message,
            )
            raise


def is_milestone(issue: Issue) -> bool:
    """An Epic, or any issue labelled 'milestone'."""
    return issue.issue_type == MILESTONE_ISSUE_TYPE or MILESTONE_LABEL in issue.labels


def check_no_milestone_date_change(
    conn: psycopg.Connection,
    issue: Issue,
    *,
    run_id: str | None,
    actor: str,
    mode: str | None,
) -> None:
    """GUARDRAIL: no_milestone_date_change. No bypass at any mode, M3 included.

    Not in GUARDRAILS yet: P1/P2 only create issues and set no dates, so there is
    nothing for it to look at until a tool can change a due date. Any write path that
    does must call this first. On refusal the audit row is written before raising.
    """
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
