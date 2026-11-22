"""apply.py is the one place a draft becomes a Jira issue. It creates parents first, uses the
PM's edits, and when Jira fails part-way it says exactly what was and was not created."""

from __future__ import annotations

import json

import pytest

from cognipm.gateway.apply import ApplyFailed, apply_staged_changes
from cognipm.gateway.server import GatewayTools
from tests.helpers import creates, fake_jira, posts

SOURCES = ["Quote from the input."]
REASONING = "Reasoning that is long enough."


def stage_story_with_subtask(conn, tools):
    """A P1 story and a P2 sub-task under it, in one run. The sub-task is made OLDER than its
    parent, so only an explicit parents-first ordering (not insertion order) can pass."""
    run_id = tools.start_run("p1", "notes")
    story = tools.propose_backlog_item(
        run_id, "The story", "Story text", ["Criterion"], REASONING, "NA", SOURCES, labels=["x"]
    )
    child = tools.propose_task_breakdown(
        run_id, "The sub-task", "Child text", REASONING, "NA", SOURCES, parent_change_id=story
    )
    conn.execute("UPDATE staged_changes SET created_at = now() - interval '1 hour' WHERE id = %s", (child,))
    conn.commit()
    return run_id, story, child


def apply(conn, jira, run_id, **kwargs):
    return apply_staged_changes(jira, conn, run_id, actor="human:reviewer", mode="M2", **kwargs)


def statuses(conn) -> dict[str, str]:
    return {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM staged_changes").fetchall()}


def test_a_story_is_created_before_the_subtask_that_hangs_under_it(conn):
    jira, seen, created = fake_jira()
    run_id, story, child = stage_story_with_subtask(conn, GatewayTools(jira, conn, "M2"))

    result = apply(conn, jira, run_id)

    assert [r["issue_key"] for r in result] == ["TEST-100", "TEST-101"]
    assert [r["change_id"] for r in result] == [story, child]
    story_fields, child_fields = created
    assert story_fields["issuetype"] == {"id": "10001"} and "parent" not in story_fields
    assert story_fields["labels"] == ["x", "cognipm-drafted", f"cognipm-draft-{story}"]
    assert child_fields["issuetype"] == {"id": "10003"}  # the sub-task type, found by its flag
    assert child_fields["parent"] == {"key": "TEST-100"}  # the key Jira gave the story a moment earlier
    rows = conn.execute(
        "SELECT id, status, created_issue_key FROM staged_changes ORDER BY created_issue_key"
    ).fetchall()
    assert [(r["status"], r["created_issue_key"]) for r in rows] == [
        ("applied", "TEST-100"),
        ("applied", "TEST-101"),
    ]


def test_the_pms_edited_version_is_what_reaches_jira_and_the_original_is_kept(conn):
    jira, _, created = fake_jira()
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")
    change = tools.propose_backlog_item(run_id, "Agent wording", "d", ["c"], REASONING, "NA", SOURCES)
    edited = {"issue_type": "Task", "summary": "PM wording", "description": "d", "acceptance_criteria": ["c"]}
    conn.execute("UPDATE staged_changes SET edited_payload = %s WHERE id = %s", (json.dumps(edited), change))
    conn.commit()

    result = apply(conn, jira, run_id)

    assert created[0]["summary"] == "PM wording" and created[0]["issuetype"] == {"id": "10002"}
    assert result[0]["was_edited"] is True
    assert (
        conn.execute("SELECT payload FROM staged_changes").fetchone()["payload"]["summary"] == "Agent wording"
    )


def test_only_the_approved_drafts_are_created(conn):
    jira, _, created = fake_jira()
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")
    keep = tools.propose_backlog_item(run_id, "Keep", "d", ["c"], REASONING, "NA", SOURCES)
    tools.propose_backlog_item(run_id, "Unticked", "d", ["c"], REASONING, "NA", SOURCES)

    apply(conn, jira, run_id, change_ids=[keep])

    assert [c["summary"] for c in created] == ["Keep"]
    assert sorted(statuses(conn).values()) == ["applied", "proposed"]


def test_a_subtask_whose_parent_draft_was_left_out_writes_nothing(conn):
    jira, seen, _ = fake_jira()
    run_id, story, child = stage_story_with_subtask(conn, GatewayTools(jira, conn, "M2"))

    with pytest.raises(ValueError, match="needs its parent draft"):
        apply(conn, jira, run_id, change_ids=[child])

    assert posts(seen) == []
    assert set(statuses(conn).values()) == {"proposed"}


def test_a_jira_failure_halfway_reports_exactly_what_was_and_was_not_created(conn):
    jira, _, created = fake_jira(fail_on_summary="The sub-task")
    run_id, story, child = stage_story_with_subtask(conn, GatewayTools(jira, conn, "M2"))

    with pytest.raises(ApplyFailed) as failure:
        apply(conn, jira, run_id)

    assert [c["issue_key"] for c in failure.value.created] == ["TEST-100"]
    assert failure.value.not_created == [child]
    assert "summary: refused by the fake" in failure.value.reason
    assert statuses(conn) == {story: "applied", child: "failed"}
    assert conn.execute("SELECT error FROM staged_changes WHERE id = %s", (child,)).fetchone()["error"]
    assert len(created) == 1  # the story really exists; no silent half-batch
    outcomes = [
        r["outcome"] for r in conn.execute("SELECT outcome FROM audit_log WHERE action = 'create_issue'")
    ]
    assert outcomes == ["created", "failed"]


def test_a_retry_creates_only_what_is_left(conn):
    jira, _, _ = fake_jira(fail_on_summary="The sub-task")
    run_id, story, child = stage_story_with_subtask(conn, GatewayTools(jira, conn, "M2"))
    with pytest.raises(ApplyFailed):
        apply(conn, jira, run_id)

    healthy_jira, _, created = fake_jira(first_number=200)
    result = apply(conn, healthy_jira, run_id)

    assert [r["change_id"] for r in result] == [child]
    assert created[0]["parent"] == {"key": "TEST-100"}  # still hangs under the story made the first time
    assert set(statuses(conn).values()) == {"applied"}


# ---------- safe to retry, and honest about where an issue came from ----------


def test_every_created_issue_says_it_was_drafted_by_cognipm_and_who_approved_it(conn):
    jira, _, created = fake_jira()
    tools = GatewayTools(jira, conn, "M2", agent="orchestrator:test")
    run_id = tools.start_run("p1", "notes")
    change = tools.propose_backlog_item(run_id, "A story", "d", ["c"], REASONING, "NA", SOURCES)
    conn.execute(
        'UPDATE staged_changes SET edited_payload = payload || \'{"summary": "A better story"}\' WHERE id = %s',
        (change,),
    )
    conn.commit()

    apply(conn, jira, run_id)

    assert {"cognipm-drafted", f"cognipm-draft-{change}"} <= set(created[0]["labels"])
    ((key, text),) = jira.comments
    assert key == "TEST-100"
    assert "Drafted by CogniPM at M2" in text and run_id in text
    assert "Approved by human:reviewer, with edits to the draft" in text


def test_a_failed_provenance_comment_does_not_undo_a_create(conn):
    jira, _, created = fake_jira()
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")
    tools.propose_backlog_item(run_id, "A story", "d", ["c"], REASONING, "NA", SOURCES)
    jira.add_comment = lambda key, text: (_ for _ in ()).throw(RuntimeError("comments are down"))

    result = apply(conn, jira, run_id)

    assert [r["issue_key"] for r in result] == ["TEST-100"] and len(created) == 1
    row = conn.execute("SELECT outcome, detail FROM audit_log WHERE action = 'provenance_comment'").fetchone()
    assert row["outcome"] == "failed" and "comments are down" in row["detail"]


def test_a_draft_that_was_created_before_a_crash_is_adopted_not_created_a_second_time(conn):
    jira, _, _ = fake_jira()
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")
    change = tools.propose_backlog_item(run_id, "A story", "d", ["c"], REASONING, "NA", SOURCES)
    # The first attempt made TEST-55 in Jira, then died before recording it. The retry finds its stamp.
    retry_jira, seen, created = fake_jira(stamped={change: "TEST-55"})

    result = apply(conn, retry_jira, run_id)

    assert result[0]["issue_key"] == "TEST-55" and result[0]["recovered"] is True
    assert creates(seen) == [] and created == []  # no second issue
    row = conn.execute("SELECT status, created_issue_key FROM staged_changes").fetchone()
    assert row == {"status": "applied", "created_issue_key": "TEST-55"}
    assert conn.execute("SELECT outcome FROM audit_log WHERE action = 'create_issue'").fetchone() == {
        "outcome": "recovered"
    }
