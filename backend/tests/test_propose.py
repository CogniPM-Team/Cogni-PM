"""propose_* only ever stages a draft: it never reaches Jira, and it refuses a draft that
cannot be traced to the input, explained, or attached to a real run."""

from __future__ import annotations

import pytest

from cognipm.gateway.server import GatewayTools
from tests.helpers import creates, fake_jira

REASONING = "The notes ask for this explicitly, twice."
SOURCES = ["Users must be able to reset their password by email."]


@pytest.fixture
def env(conn):
    jira, seen, _ = fake_jira()
    tools = GatewayTools(jira=jira, conn=conn, mode="M2", agent="test")
    return tools, seen, conn


def backlog_item(tools, run_id, **overrides):
    args = {
        "summary": "Reset password by email",
        "description": "As a user I can reset my password.",
        "acceptance_criteria": ["Email arrives within a minute", "Link expires after 1 hour"],
        "reasoning": REASONING,
        "assumptions": "NA",
        "sources": SOURCES,
    } | overrides
    return tools.propose_backlog_item(run_id, **args)


def subtask(tools, run_id, **overrides):
    args = {
        "summary": "Send the reset email",
        "description": "Add the mail template.",
        "reasoning": REASONING,
        "assumptions": "NA",
        "sources": SOURCES,
        "parent_key": "TEST-1",
    } | overrides
    return tools.propose_task_breakdown(run_id, **args)


def staged_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM staged_changes").fetchone()["n"]


def test_a_backlog_draft_is_staged_with_its_sources_and_never_touches_jira(env):
    tools, seen, conn = env
    run_id = tools.start_run("p1", "meeting notes 12 Nov")

    change_id = backlog_item(tools, run_id, labels=["auth"])

    row = conn.execute("SELECT * FROM staged_changes WHERE id = %s", (change_id,)).fetchone()
    assert row["kind"] == "backlog_item" and row["status"] == "proposed"
    assert row["payload"]["summary"] == "Reset password by email"
    assert row["payload"]["acceptance_criteria"] == [
        "Email arrives within a minute",
        "Link expires after 1 hour",
    ]
    assert row["payload"]["labels"] == ["auth"]
    assert row["sources"] == SOURCES
    assert row["action_class"] == "structural"
    assert row["created_issue_key"] is None
    assert creates(seen) == []  # it read Jira to check the rules, but created nothing
    audit = conn.execute(
        "SELECT actor, mode, outcome FROM audit_log WHERE action = 'propose_backlog_item'"
    ).fetchone()
    assert audit == {"actor": "agent:test", "mode": "M2", "outcome": "staged"}


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"reasoning": "too short"}, "reasoning"),
        ({"assumptions": "  "}, "assumptions"),
        ({"sources": []}, "sources"),
        ({"sources": ["", "   "]}, "sources"),
        ({"summary": "  "}, "summary"),
        ({"summary": "x" * 256}, "summary"),
        ({"issue_type": "Epic"}, "issue_type"),
    ],
)
def test_a_draft_that_breaks_a_rule_is_refused_and_nothing_is_staged(env, overrides, message):
    tools, seen, conn = env
    run_id = tools.start_run("p1", "notes")

    with pytest.raises(ValueError, match=message):
        backlog_item(tools, run_id, **overrides)

    assert staged_count(conn) == 0
    assert seen == []


def test_a_draft_needs_a_real_open_run(env):
    tools, _, conn = env

    with pytest.raises(ValueError, match="unknown run_id"):
        backlog_item(tools, "no-such-run")

    run_id = tools.start_run("p1", "notes")
    tools.finish_run(run_id)
    with pytest.raises(ValueError, match="not running"):
        backlog_item(tools, run_id)
    assert staged_count(conn) == 0


def test_start_run_refuses_an_unknown_task_type(env):
    tools, _, conn = env

    with pytest.raises(ValueError, match="task_type"):
        tools.start_run("reestimate", "project = TEST")

    assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"] == 0


def test_a_subtask_can_hang_under_an_existing_story_or_a_draft_in_the_same_run(env):
    tools, seen, conn = env
    run_id = tools.start_run("p2", "TEST-1")
    parent_draft = backlog_item(tools, run_id)

    under_key = subtask(tools, run_id)
    under_draft = subtask(
        tools, run_id, summary="Expire the link", parent_key=None, parent_change_id=parent_draft
    )

    rows = {r["id"]: r for r in conn.execute("SELECT * FROM staged_changes").fetchall()}
    assert rows[under_key]["kind"] == "subtask" and rows[under_key]["payload"]["parent_key"] == "TEST-1"
    assert rows[under_draft]["parent_change_id"] == parent_draft
    assert creates(seen) == []


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"parent_key": "TEST-1) OR project = SECRET"}, "not a valid Jira issue key"),
        ({"parent_key": None}, "exactly one parent"),
        ({"parent_change_id": "some-draft"}, "exactly one parent"),
    ],
)
def test_a_subtask_with_a_bad_parent_is_refused(env, overrides, error):
    tools, seen, conn = env
    run_id = tools.start_run("p2", "TEST-1")

    with pytest.raises(ValueError, match=error):
        subtask(tools, run_id, **overrides)

    assert staged_count(conn) == 0 and seen == []


def test_a_subtask_cannot_hang_under_another_run_or_under_a_subtask(env):
    tools, _, conn = env
    other_run = tools.start_run("p1", "other")
    foreign_draft = backlog_item(tools, other_run)
    run_id = tools.start_run("p2", "TEST-1")
    child = subtask(tools, run_id)

    with pytest.raises(ValueError, match="is not a draft in run"):
        subtask(tools, run_id, parent_key=None, parent_change_id=foreign_draft)
    with pytest.raises(ValueError, match="cannot be the parent of another sub-task"):
        subtask(tools, run_id, parent_key=None, parent_change_id=child)

    assert staged_count(conn) == 2  # the foreign draft and the one valid sub-task


def test_finish_run_summarises_the_drafts_and_closes_the_run_to_new_ones(env):
    tools, _, conn = env
    run_id = tools.start_run("p1", "notes")
    backlog_item(tools, run_id)

    summary = tools.finish_run(run_id)

    assert summary["status"] == "awaiting_review"
    assert [s["summary"] for s in summary["staged_changes"]] == ["Reset password by email"]
    assert conn.execute("SELECT status FROM runs WHERE id = %s", (run_id,)).fetchone() == {
        "status": "awaiting_review"
    }
