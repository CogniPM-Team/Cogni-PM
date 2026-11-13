"""commit_changes fails with a missing, unknown, expired, consumed or mismatched-run token -
and never creates anything in Jira when it does."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from cognipm.gateway.server import GatewayTools, issue_approval_token
from tests.helpers import fake_jira, posts

REASONING = "Reasoning that is long enough."


@pytest.fixture
def env(conn):
    jira, seen, created = fake_jira()
    tools = GatewayTools(jira=jira, conn=conn, mode="M3", agent="test")
    run_id = tools.start_run("p1", "notes")
    tools.propose_backlog_item(run_id, "A story", "text", ["criterion"], REASONING, "NA", ["quote"])
    tools.finish_run(run_id)
    return tools, run_id, seen, created, conn


def token_for(conn, run_id, *, expires_in=timedelta(minutes=10), consumed=False) -> str:
    token = str(uuid.uuid4())
    now = datetime.now(UTC)
    conn.execute(
        "INSERT INTO approval_tokens (token, run_id, issued_at, expires_at, consumed_at) VALUES (%s, %s, %s, %s, %s)",
        (token, run_id, now, now + expires_in, now if consumed else None),
    )
    conn.commit()
    return token


def refusal_logged(conn, reason: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM audit_log WHERE action = 'commit_changes' AND outcome = 'refused' AND detail = %s",
        (reason,),
    ).fetchone()
    return row is not None


@pytest.mark.parametrize("token", ["", "not-a-real-token"])
def test_refuses_a_missing_or_unknown_token(env, token):
    tools, run_id, seen, _, conn = env

    with pytest.raises(ValueError, match="missing or unknown"):
        tools.commit_changes(run_id, token)

    assert posts(seen) == []
    assert refusal_logged(conn, "approval_token is missing or unknown")


def test_refuses_a_token_that_belongs_to_another_run(env):
    tools, run_id, seen, _, conn = env
    other = tools.start_run("p1", "other")
    token = token_for(conn, other)

    with pytest.raises(ValueError, match="different run"):
        tools.commit_changes(run_id, token)

    assert posts(seen) == []


def test_refuses_an_expired_token(env):
    tools, run_id, seen, _, conn = env
    token = token_for(conn, run_id, expires_in=timedelta(minutes=-1))

    with pytest.raises(ValueError, match="expired"):
        tools.commit_changes(run_id, token)

    assert posts(seen) == []


def test_refuses_a_consumed_token(env):
    tools, run_id, seen, _, conn = env
    token = token_for(conn, run_id, consumed=True)

    with pytest.raises(ValueError, match="already been consumed"):
        tools.commit_changes(run_id, token)

    assert posts(seen) == []


def test_a_valid_token_creates_the_issues_once_and_is_then_spent(env):
    tools, run_id, seen, created, conn = env
    token = issue_approval_token(conn, run_id)

    result = tools.commit_changes(run_id, token)

    assert result == {"run_id": run_id, "created_issue_keys": ["TEST-100"]}
    assert created[0]["summary"] == "A story"
    assert conn.execute("SELECT status FROM runs WHERE id = %s", (run_id,)).fetchone() == {
        "status": "applied"
    }
    with pytest.raises(ValueError, match="already been consumed"):
        tools.commit_changes(run_id, token)
    assert len(posts(seen)) == 1  # the replay created nothing


def test_a_failed_commit_marks_the_run_failed_and_keeps_the_token_for_a_retry(conn):
    jira, _, created = fake_jira(fail_on_summary="A story")
    tools = GatewayTools(jira=jira, conn=conn, mode="M3")
    run_id = tools.start_run("p1", "notes")
    tools.propose_backlog_item(run_id, "A story", "text", ["c"], REASONING, "NA", ["quote"])
    tools.finish_run(run_id)
    token = issue_approval_token(conn, run_id)

    with pytest.raises(Exception, match="stopped at draft"):
        tools.commit_changes(run_id, token)

    assert created == []
    assert conn.execute("SELECT status FROM runs WHERE id = %s", (run_id,)).fetchone() == {"status": "failed"}
    assert conn.execute("SELECT consumed_at FROM approval_tokens").fetchone() == {"consumed_at": None}
