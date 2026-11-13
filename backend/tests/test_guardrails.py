"""Guardrails refuse a write, name themselves in the refusal, and leave a record. They apply
the same at every mode, so the tests run against M1, M2 and M3."""

from __future__ import annotations

import pytest

from cognipm.gateway import guardrails
from cognipm.gateway.apply import ApplyFailed, apply_staged_changes
from cognipm.gateway.guardrails import GuardrailViolation, check_no_milestone_date_change, run_guardrails
from cognipm.gateway.jira import Issue
from cognipm.gateway.server import GatewayTools
from tests.helpers import fake_jira, posts


def issue(*, issue_type="Story", labels=()) -> Issue:
    return Issue(
        key="TEST-7",
        summary="s",
        status="To Do",
        issue_type=issue_type,
        story_points=None,
        due_date="2026-12-01",
        labels=list(labels),
    )


@pytest.mark.parametrize("mode", ["M1", "M2", "M3"])
@pytest.mark.parametrize("target", [issue(issue_type="Epic"), issue(labels=["milestone"])])
def test_a_milestones_due_date_is_protected_at_every_mode(conn, mode, target):
    with pytest.raises(GuardrailViolation) as refusal:
        check_no_milestone_date_change(conn, target, run_id=None, actor="agent:test", mode=mode)

    assert refusal.value.guardrail == "no_milestone_date_change"
    row = conn.execute("SELECT mode, outcome, action FROM audit_log").fetchone()
    assert row == {"mode": mode, "outcome": "refused", "action": "guardrail:no_milestone_date_change"}


def test_an_ordinary_issue_may_have_its_date_checked_without_a_refusal(conn):
    check_no_milestone_date_change(conn, issue(), run_id=None, actor="agent:test", mode="M2")

    assert conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone() == {"n": 0}


def refuse_everything(draft: dict) -> None:
    raise GuardrailViolation("test_rule", f"no {draft['kind']} drafts today")


def test_the_chain_logs_the_refusing_guardrail_by_name(conn, monkeypatch):
    monkeypatch.setattr(guardrails, "GUARDRAILS", (refuse_everything,))

    with pytest.raises(GuardrailViolation, match="no backlog_item drafts today"):
        run_guardrails(
            conn, {"kind": "backlog_item", "payload": {}}, run_id=None, actor="human:reviewer", mode="M2"
        )

    row = conn.execute("SELECT action, outcome FROM audit_log").fetchone()
    assert row == {"action": "guardrail:test_rule", "outcome": "refused"}


def test_a_guardrail_refusal_at_apply_time_stops_the_write_and_marks_the_draft_failed(conn, monkeypatch):
    jira, seen, created = fake_jira()
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")
    tools.propose_backlog_item(
        run_id, "A story", "d", ["c"], "Reasoning that is long enough.", "NA", ["quote"]
    )
    monkeypatch.setattr(guardrails, "GUARDRAILS", (refuse_everything,))  # tightened after the proposal

    with pytest.raises(ApplyFailed, match="no backlog_item drafts today"):
        apply_staged_changes(jira, conn, run_id, actor="human:reviewer", mode="M2")

    assert posts(seen) == [] and created == []
    assert conn.execute("SELECT status FROM staged_changes").fetchone() == {"status": "failed"}
