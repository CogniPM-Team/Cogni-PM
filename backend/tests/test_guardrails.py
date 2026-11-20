"""Guardrails refuse a write, name themselves in the refusal, and leave a record. They apply the same
at every mode, so each rule is tested against M1, M2 and M3. Refusal tests also assert that nothing
reached Jira's create endpoint."""

from __future__ import annotations

import pytest

from cognipm.gateway import guardrails
from cognipm.gateway.apply import ApplyFailed, apply_staged_changes
from cognipm.gateway.guardrails import GuardrailViolation, check_no_milestone_date_change, run_guardrails
from cognipm.gateway.jira import Issue
from cognipm.gateway.server import GatewayTools
from tests.helpers import creates, fake_jira

MODES = ["M1", "M2", "M3"]
REASONING = "Reasoning that is long enough."


def draft(kind="backlog_item", *, parent_change_id=None, action_class="structural", **payload) -> dict:
    base = {"summary": "Reset password", "description": "d"}
    if kind == "backlog_item":
        base |= {"issue_type": "Story", "acceptance_criteria": ["It works"]}
    return {
        "kind": kind,
        "payload": base | payload,
        "parent_change_id": parent_change_id,
        "action_class": action_class,
    }


def subtask(**payload) -> dict:
    return draft("subtask", **({"parent_key": "TEST-1"} | payload))


def make_run(conn, run_id="r1", mode="M2") -> str:
    conn.execute(
        "INSERT INTO runs (id, mode, task_type, agent, scope, status) VALUES (%s, %s, 'p1', 'a', 's', 'running')",
        (run_id, mode),
    )
    conn.commit()
    return run_id


def stage_row(
    conn, change_id, run_id="r1", *, summary="Existing draft", status="proposed", kind="backlog_item"
):
    conn.execute(
        "INSERT INTO staged_changes (id, run_id, kind, payload, sources, reasoning, status) "
        "VALUES (%s, %s, %s, %s::jsonb, '[\"q\"]', 'long enough reasoning here', %s)",
        (change_id, run_id, kind, f'{{"summary": "{summary}"}}', status),
    )
    conn.commit()


def check(conn, jira, the_draft, *, mode="M2", stage="propose", run_id=None, **kwargs) -> None:
    run_guardrails(
        the_draft, jira=jira, conn=conn, run_id=run_id, actor="agent:test", mode=mode, stage=stage, **kwargs
    )


def refused_by(conn) -> list[str]:
    rows = conn.execute("SELECT action FROM audit_log WHERE outcome = 'refused' ORDER BY id").fetchall()
    return [r["action"] for r in rows]


def assert_refused(conn, jira, seen, the_draft, name: str, match: str, **kwargs) -> None:
    with pytest.raises(GuardrailViolation, match=match) as refusal:
        check(conn, jira, the_draft, **kwargs)
    assert refusal.value.guardrail == name
    assert refused_by(conn)[-1] == f"guardrail:{name}"
    assert creates(seen) == []


# ---------- a good draft passes the whole chain ----------


@pytest.mark.parametrize("mode", MODES)
def test_a_well_formed_draft_passes_every_rule_at_every_mode(conn, mode):
    jira, _, _ = fake_jira()
    check(conn, jira, draft(), mode=mode)
    check(conn, jira, subtask(), mode=mode)
    assert refused_by(conn) == []


# ---------- one refusal test per guardrail ----------


@pytest.mark.parametrize("mode", MODES)
def test_required_fields_refuses_a_blank_title_and_a_story_without_acceptance_criteria(conn, mode):
    jira, seen, _ = fake_jira()

    assert_refused(conn, jira, seen, draft(summary="   "), "required_fields", "non-empty summary", mode=mode)
    assert_refused(
        conn,
        jira,
        seen,
        draft(acceptance_criteria=[" "]),
        "required_fields",
        "acceptance criterion",
        mode=mode,
    )
    check(conn, jira, draft(issue_type="Task", acceptance_criteria=[]), mode=mode)  # only stories need them


@pytest.mark.parametrize("mode", MODES)
def test_create_only_refuses_anything_that_acts_on_an_existing_issue(conn, mode):
    jira, seen, _ = fake_jira()

    assert_refused(conn, jira, seen, draft("transition_issue"), "create_only", "not a create", mode=mode)
    assert_refused(conn, jira, seen, draft(issue_key="TEST-1"), "create_only", "issue_key", mode=mode)
    assert_refused(conn, jira, seen, draft(status="Done"), "create_only", "status", mode=mode)


@pytest.mark.parametrize("mode", MODES)
def test_an_external_action_is_never_committed_automatically_but_a_person_may_approve_it(conn, mode):
    jira, seen, _ = fake_jira()
    external = draft(action_class="external")

    assert_refused(
        conn, jira, seen, external, "external_is_gated", "approved by a person", mode=mode, automatic=True
    )
    check(conn, jira, external, mode=mode, automatic=False)  # a human approving through the API
    check(conn, jira, draft(), mode=mode, automatic=True)  # an ordinary structural create is not external


@pytest.mark.parametrize("mode", MODES)
def test_max_items_per_run_stops_a_run_that_would_flood_the_backlog(conn, monkeypatch, mode):
    monkeypatch.setenv("COGNIPM_MAX_ITEMS_PER_RUN", "2")
    jira, seen, _ = fake_jira()
    run_id = make_run(conn)
    stage_row(conn, "c1", summary="One")
    stage_row(conn, "c2", summary="Two")
    stage_row(conn, "c3", summary="Rejected one", status="rejected")  # does not count

    assert_refused(
        conn, jira, seen, draft(summary="Three"), "max_items_per_run", "limit is 2", mode=mode, run_id=run_id
    )


def test_at_apply_time_the_cap_counts_what_was_actually_created(conn, monkeypatch):
    monkeypatch.setenv("COGNIPM_MAX_ITEMS_PER_RUN", "1")
    jira, seen, _ = fake_jira()
    run_id = make_run(conn)
    stage_row(conn, "c1", summary="Created already", status="applied")

    assert_refused(
        conn,
        jira,
        seen,
        draft(summary="Another"),
        "max_items_per_run",
        "limit is 1",
        stage="apply",
        run_id=run_id,
    )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("payload", [{"issue_type": "Epic"}, {"labels": ["milestone"]}])
def test_a_milestone_never_gets_a_due_date_from_an_agent(conn, mode, payload):
    jira, seen, _ = fake_jira()

    assert_refused(
        conn,
        jira,
        seen,
        draft(due_date="2026-12-01", **payload),
        "no_milestone_date_change",
        "milestone",
        mode=mode,
    )
    check(
        conn, jira, draft(due_date="2026-12-01"), mode=mode
    )  # a date on an ordinary story is not this rule's business


@pytest.mark.parametrize("mode", MODES)
def test_in_project_scope_refuses_anything_that_reaches_outside_the_project(conn, mode):
    jira, seen, _ = fake_jira()

    assert_refused(
        conn, jira, seen, subtask(parent_key="OTHER-1"), "in_project_scope", "outside project TEST", mode=mode
    )
    assert_refused(
        conn, jira, seen, draft(project="OTHER"), "in_project_scope", "only target project TEST", mode=mode
    )


@pytest.mark.parametrize("mode", MODES)
def test_valid_parent_refuses_orphans_missing_parents_and_parents_that_cannot_have_children(conn, mode):
    jira, seen, _ = fake_jira(
        existing={
            "TEST-1": {},
            "TEST-5": {"issuetype": {"name": "Subtask"}},
            "TEST-6": {"issuetype": {"name": "Epic"}},
        }
    )

    assert_refused(conn, jira, seen, draft("subtask"), "valid_parent", "needs a parent story", mode=mode)
    assert_refused(
        conn, jira, seen, subtask(parent_key="TEST-99"), "valid_parent", "could not be read", mode=mode
    )
    assert_refused(
        conn, jira, seen, subtask(parent_key="TEST-5"), "valid_parent", "itself a sub-task", mode=mode
    )
    assert_refused(conn, jira, seen, subtask(parent_key="TEST-6"), "valid_parent", "is an Epic", mode=mode)
    assert_refused(
        conn, jira, seen, draft(parent_key="TEST-1"), "valid_parent", "cannot have a parent", mode=mode
    )


def test_valid_parent_checks_a_parent_draft_belongs_to_this_run_and_is_not_rejected_or_a_subtask(conn):
    jira, seen, _ = fake_jira()
    run_id = make_run(conn)
    make_run(conn, "r2")
    stage_row(conn, "mine", summary="Mine")
    stage_row(conn, "theirs", "r2", summary="Theirs")
    stage_row(conn, "rejected", summary="Rejected", status="rejected")
    stage_row(conn, "child", summary="Child", kind="subtask")

    def under(parent):
        return draft("subtask", parent_change_id=parent)

    check(conn, jira, under("mine"), run_id=run_id)
    assert_refused(conn, jira, seen, under("theirs"), "valid_parent", "not part of this run", run_id=run_id)
    assert_refused(conn, jira, seen, under("rejected"), "valid_parent", "was rejected", run_id=run_id)
    assert_refused(
        conn,
        jira,
        seen,
        under("child"),
        "valid_parent",
        "cannot be the parent of another sub-task",
        run_id=run_id,
    )


@pytest.mark.parametrize("mode", MODES)
def test_no_duplicate_refuses_a_title_that_is_already_open_in_jira_ignoring_case_and_spacing(conn, mode):
    jira, seen, _ = fake_jira(open_issues={"TEST-7": "Reset  Password"})

    assert_refused(
        conn, jira, seen, draft(summary="reset password"), "no_duplicate", "TEST-7 is already open", mode=mode
    )
    check(conn, jira, draft(summary="Export invoices"), mode=mode)


def test_no_duplicate_refuses_a_second_draft_with_the_same_title_in_one_run_but_not_the_draft_itself(conn):
    jira, seen, _ = fake_jira()
    run_id = make_run(conn)
    stage_row(conn, "c1", summary="Reset password")

    assert_refused(conn, jira, seen, draft(), "no_duplicate", "already has the title", run_id=run_id)
    check(
        conn, jira, draft(), run_id=run_id, change_id="c1"
    )  # re-checking c1 at apply time must not trip on itself


@pytest.mark.parametrize("mode", MODES)
def test_a_field_jira_requires_but_a_draft_cannot_fill_is_refused_by_name(conn, mode):
    jira, seen, _ = fake_jira(required=[{"key": "customfield_10042", "name": "Team"}])

    assert_refused(conn, jira, seen, draft(), "jira_required_fields", "requires Team", mode=mode)
    assert_refused(conn, jira, seen, subtask(), "jira_required_fields", "requires Team", mode=mode)


def test_fields_a_draft_can_fill_are_not_mistaken_for_missing_ones(conn):
    jira, _, _ = fake_jira(
        required=[{"key": "labels", "name": "Labels"}, {"key": "parent", "name": "Parent"}]
    )

    check(conn, jira, draft())


# ---------- the chain is cheap-first and logs by name ----------


def test_a_local_refusal_never_costs_a_jira_request(conn):
    jira, seen, _ = fake_jira()

    with pytest.raises(GuardrailViolation):
        check(conn, jira, draft(summary=""))

    assert seen == []  # required_fields runs before anything that reads Jira


def refuse_everything(draft: dict, ctx) -> None:
    raise GuardrailViolation("test_rule", f"no {draft['kind']} drafts today")


def test_the_chain_logs_the_refusing_guardrail_by_name_and_stage(conn, monkeypatch):
    monkeypatch.setattr(guardrails, "GUARDRAILS", (refuse_everything,))
    jira, _, _ = fake_jira()

    with pytest.raises(GuardrailViolation, match="no backlog_item drafts today"):
        check(conn, jira, draft(), stage="apply")

    row = conn.execute("SELECT action, outcome, detail FROM audit_log").fetchone()
    assert row == {
        "action": "guardrail:test_rule",
        "outcome": "refused",
        "detail": "[apply] no backlog_item drafts today",
    }


# ---------- the same chain guards propose time and apply time ----------


def test_propose_refuses_a_duplicate_before_it_is_staged_and_the_agent_is_told_why(conn):
    jira, seen, _ = fake_jira(open_issues={"TEST-7": "Reset password"})
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")

    with pytest.raises(GuardrailViolation, match="TEST-7 is already open"):
        tools.propose_backlog_item(run_id, "Reset password", "d", ["c"], REASONING, "NA", ["quote"])

    assert conn.execute("SELECT COUNT(*) AS n FROM staged_changes").fetchone() == {"n": 0}
    assert refused_by(conn) == ["guardrail:no_duplicate"]
    assert creates(seen) == []


def test_a_stale_approval_cannot_get_around_a_rule_that_Jira_state_has_since_broken(conn):
    # Proposed while the title was free...
    jira, _, _ = fake_jira()
    tools = GatewayTools(jira, conn, "M2")
    run_id = tools.start_run("p1", "notes")
    tools.propose_backlog_item(run_id, "Reset password", "d", ["c"], REASONING, "NA", ["quote"])
    # ...then somebody creates that issue by hand before the PM approves.
    later_jira, seen, created = fake_jira(open_issues={"TEST-7": "Reset password"})

    with pytest.raises(ApplyFailed, match="TEST-7 is already open"):
        apply_staged_changes(later_jira, conn, run_id, actor="human:reviewer", mode="M2")

    assert creates(seen) == [] and created == []
    assert conn.execute("SELECT status FROM staged_changes").fetchone() == {"status": "failed"}
    assert "guardrail:no_duplicate" in refused_by(conn)


def test_an_external_draft_is_refused_by_commit_changes_but_not_by_a_human_approval(conn):
    jira, _, created = fake_jira()
    tools = GatewayTools(jira, conn, "M3")
    run_id = tools.start_run("p1", "notes")
    change_id = tools.propose_backlog_item(
        run_id, "Notify the client", "d", ["c"], REASONING, "NA", ["quote"]
    )
    conn.execute("UPDATE staged_changes SET action_class = 'external' WHERE id = %s", (change_id,))
    conn.commit()

    with pytest.raises(ApplyFailed, match="approved by a person"):
        apply_staged_changes(jira, conn, run_id, actor="agent:test", mode="M3", automatic=True)
    assert created == []

    result = apply_staged_changes(jira, conn, run_id, actor="human:reviewer", mode="M3", automatic=False)
    assert len(result) == 1 and len(created) == 1


# ---------- the milestone rule for a write that changes an existing issue's date ----------


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


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("target", [issue(issue_type="Epic"), issue(labels=["milestone"])])
def test_a_milestones_existing_due_date_is_protected_at_every_mode(conn, mode, target):
    with pytest.raises(GuardrailViolation) as refusal:
        check_no_milestone_date_change(conn, target, run_id=None, actor="agent:test", mode=mode)

    assert refusal.value.guardrail == "no_milestone_date_change"
    row = conn.execute("SELECT mode, outcome, action FROM audit_log").fetchone()
    assert row == {"mode": mode, "outcome": "refused", "action": "guardrail:no_milestone_date_change"}


def test_an_ordinary_issue_may_have_its_date_checked_without_a_refusal(conn):
    check_no_milestone_date_change(conn, issue(), run_id=None, actor="agent:test", mode="M2")

    assert conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone() == {"n": 0}
