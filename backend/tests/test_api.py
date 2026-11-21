"""The control-plane API, end to end through the real app: real routes, real database, the real gateway
tool registration (in-process), a fake Jira and a scripted model. The refusal cases matter most: approving
twice, editing what is already created, approving a sub-task without its parent, and what happens when
Jira fails halfway."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from cognipm.api import launcher
from cognipm.api.deps import conn_factory, get_conn, get_jira, get_run_options
from cognipm.api.main import app
from cognipm.gateway.jira import text_to_adf
from cognipm.gateway.server import build_server
from tests.fake_gemini import FakeGemini, backlog_item, call_reply, drafts_reply, subtask, text_chat_reply
from tests.helpers import creates, fake_jira

NOTES = (
    "Meeting 12 Nov. Customers keep asking to reset their password by email.\n"
    "Admins need an audit trail of every login. Nothing else came up."
)
RESET = "Customers keep asking to reset their password by email."
AUDIT = "Admins need an audit trail of every login."
STORY = "Users can reset their password. They request a link by email and it expires after one hour."


class _Shared:
    """The test connection, which request code may 'close' without actually closing it."""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def build_api(conn, *, jira_options=None):
    """The app wired to the test database, a fake Jira and a scripted model. Returns a namespace the tests drive."""
    shared = _Shared(conn)
    jira, seen, created = fake_jira(
        existing={"TEST-1": {"summary": "Reset password", "description": text_to_adf(STORY)}},
        **(jira_options or {}),
    )
    gemini = FakeGemini([])
    api = SimpleNamespace(conn=conn, jira=jira, seen=seen, created=created, gemini=gemini)
    options = {
        "task": {
            "gemini": gemini,
            "mcp_server": build_server("M2", jira=jira, conn=shared, agent="orchestrator:test"),
        },
        "chat": {"gemini": gemini, "mcp_server": build_server("M1", jira=jira, conn=shared)},
    }
    app.dependency_overrides[get_conn] = lambda: shared
    app.dependency_overrides[conn_factory] = lambda: lambda: shared
    app.dependency_overrides[get_jira] = lambda: api.jira
    app.dependency_overrides[get_run_options] = lambda: options
    return api


@pytest.fixture
def api(conn):
    api = build_api(conn)
    with TestClient(app) as client:
        api.client = client
        yield api
    app.dependency_overrides.clear()


def wait_until_settled(client, run_id, timeout=20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["run"]["status"] != "running":
            return detail
        time.sleep(0.05)
    raise AssertionError("the run never settled")


def start_p1(api, replies=None, **body) -> dict:
    api.gemini.models.replies.extend(
        replies or [drafts_reply([backlog_item("Password reset", RESET), backlog_item("Login audit", AUDIT)])]
    )
    response = api.client.post("/api/runs", json={"task": "p1", "input_text": NOTES} | body)
    assert response.status_code == 202, response.text
    return wait_until_settled(api.client, response.json()["run_id"])


def draft_ids(detail) -> list[str]:
    return [d["id"] for d in detail["drafts"]]


# ---------- starting and reviewing a run ----------


def test_modes_come_from_the_gateways_own_tool_table(api):
    modes = {m["id"]: m for m in api.client.get("/api/modes").json()}

    assert [modes[m]["name"] for m in ("M1", "M2", "M3")] == ["Co-Pilot", "Super-Pilot", "Auto-Pilot"]
    assert modes["M1"]["tools"] == ["search_issues", "get_issue"]
    assert (modes["M1"]["can_stage_drafts"], modes["M2"]["can_stage_drafts"]) == (False, True)
    assert (modes["M2"]["can_commit"], modes["M3"]["can_commit"]) == (False, True)
    assert "Search Jira issues by JQL" in modes["M1"]["tool_help"]["search_issues"]


def test_a_run_started_through_the_api_ends_up_awaiting_review_with_cited_drafts_and_nothing_in_jira(api):
    detail = start_p1(api)

    assert detail["run"]["status"] == "awaiting_review" and detail["run"]["mode"] == "M2"
    assert detail["can_decide"] and detail["editable"]
    assert "Nothing has been created in Jira yet" in detail["status_note"]
    first = detail["drafts"][0]
    assert first["status"] == "proposed" and first["effective"]["summary"] == "Password reset"
    span = first["sources"][0]
    assert NOTES[span["start"] : span["end"]] == RESET  # the review screen can highlight the quote in place
    assert detail["input_text"] == NOTES
    assert [s["phase"] for s in detail["steps"]][0] == "analysing"
    assert creates(api.seen) == []


def test_the_run_list_puts_runs_waiting_for_a_decision_first(api):
    done = start_p1(api)
    api.client.post(f"/api/runs/{done['run']['id']}/reject", json={"comment": "no"})
    waiting = start_p1(api, [drafts_reply([backlog_item("Login audit", AUDIT)])])

    listing = api.client.get("/api/runs").json()

    assert [r["id"] for r in listing["waiting"]] == [waiting["run"]["id"]]
    assert [r["id"] for r in listing["past"]] == [done["run"]["id"]]
    assert listing["awaiting_review_count"] == 1 and listing["waiting"][0]["draft_count"] == 1


def test_a_p2_run_shows_the_story_it_was_asked_to_break_down(api):
    quote = "They request a link by email and it expires after one hour."
    api.gemini.models.replies.append(drafts_reply([subtask("Send the email", quote)]))

    response = api.client.post("/api/runs", json={"task": "p2", "story_key": "TEST-1"})
    detail = wait_until_settled(api.client, response.json()["run_id"])

    assert detail["parent_story"]["key"] == "TEST-1" and detail["story_key"] == "TEST-1"
    assert (
        detail["drafts"][0]["kind"] == "subtask"
        and detail["drafts"][0]["effective"]["parent_key"] == "TEST-1"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"task": "p1"},
        {"task": "p1", "input_text": "   "},
        {"task": "p2"},
        {"task": "p2", "story_key": "TEST-1) OR project = X"},
        {"task": "p3", "input_text": "x"},
    ],
)
def test_a_run_that_cannot_make_sense_is_refused_before_anything_starts(api, conn, body):
    response = api.client.post("/api/runs", json=body)

    assert response.status_code == 422
    assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone() == {"n": 0}


def test_a_story_with_nothing_to_break_down_is_reported_not_swallowed(conn):
    api = build_api(conn)
    api.jira, _, _ = fake_jira(existing={"TEST-1": {"summary": "Empty story"}})
    api.gemini.models.replies.clear()
    options = app.dependency_overrides[get_run_options]()
    options["task"]["mcp_server"] = build_server("M2", jira=api.jira, conn=_Shared(conn))
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"task": "p2", "story_key": "TEST-1"})
        run_id = response.json()["run_id"]
        detail = wait_until_settled(client, run_id)
    app.dependency_overrides.clear()

    assert detail["run"]["status"] == "failed" and "no description" in detail["run"]["comment"]
    assert detail["can_decide"] is False


def test_a_model_with_no_credit_fails_the_run_with_a_readable_reason(api):
    def out_of_credit(contents):
        raise genai_errors.ClientError(402, {"error": {"message": "credits depleted"}})

    detail = start_p1(api, [out_of_credit])

    assert detail["run"]["status"] == "failed" and "402" in detail["run"]["comment"]
    assert detail["drafts"] == []


def test_the_event_stream_replays_every_step_and_then_ends(api):
    detail = start_p1(api)

    response = api.client.get(f"/api/runs/{detail['run']['id']}/events")

    events = [e for e in response.text.split("\n\n") if e]
    steps = [json.loads(e.split("data: ")[1]) for e in events if "event: step" in e]
    assert [s["phase"] for s in steps][0] == "analysing" and steps[-1]["tool"] == "finish_run"
    assert events[-1].startswith("event: end") and '"awaiting_review"' in events[-1]
    last_id = [e for e in events if "event: step" in e][-1].split("\n")[0].removeprefix("id: ")
    resumed = api.client.get(f"/api/runs/{detail['run']['id']}/events", headers={"Last-Event-ID": last_id})
    assert "event: step" not in resumed.text  # reconnecting does not repeat what was already seen


def test_an_unknown_run_is_a_404(api):
    assert api.client.get("/api/runs/nope").status_code == 404
    assert api.client.get("/api/runs/nope/events").status_code == 404
    assert api.client.post("/api/runs/nope/approve").status_code == 404


# ---------- editing a draft ----------


def test_editing_a_draft_keeps_the_agents_version_and_records_what_changed(api):
    detail = start_p1(api)
    change_id = draft_ids(detail)[0]

    response = api.client.patch(
        f"/api/changes/{change_id}",
        json={"summary": "Reset password by email", "acceptance_criteria": ["Link works", " "]},
    )

    assert response.status_code == 200
    draft = response.json()
    assert draft["payload"]["summary"] == "Password reset"  # what the agent proposed is untouched
    assert draft["effective"]["summary"] == "Reset password by email"
    assert draft["effective"]["acceptance_criteria"] == ["Link works"]  # blanks dropped
    audit = api.conn.execute(
        "SELECT before, after, actor FROM audit_log WHERE action = 'edit_draft'"
    ).fetchone()
    assert audit["actor"] == "human:reviewer"
    assert (
        audit["before"]["summary"] == "Password reset"
        and audit["after"]["summary"] == "Reset password by email"
    )


def test_editing_a_draft_back_to_what_the_agent_wrote_counts_as_not_edited(api):
    detail = start_p1(api)
    change_id = draft_ids(detail)[0]
    api.client.patch(f"/api/changes/{change_id}", json={"summary": "Something else"})

    response = api.client.patch(f"/api/changes/{change_id}", json={"summary": "Password reset"})

    assert response.json()["edited_payload"] is None


@pytest.mark.parametrize(
    "body,status",
    [({}, 422), ({"summary": ""}, 422), ({"issue_type": "Epic"}, 422), ({"summary": "x" * 256}, 422)],
)
def test_a_nonsense_edit_is_refused(api, body, status):
    change_id = draft_ids(start_p1(api))[0]

    assert api.client.patch(f"/api/changes/{change_id}", json=body).status_code == status


def test_a_subtask_has_no_issue_type_to_edit(api):
    api.gemini.models.replies.append(drafts_reply([subtask("Send the email", "it expires after one hour.")]))
    run_id = api.client.post("/api/runs", json={"task": "p2", "story_key": "TEST-1"}).json()["run_id"]
    change_id = draft_ids(wait_until_settled(api.client, run_id))[0]

    assert api.client.patch(f"/api/changes/{change_id}", json={"issue_type": "Task"}).status_code == 422


def test_a_draft_that_is_already_created_or_dropped_cannot_be_edited(api):
    detail = start_p1(api)
    first, second = draft_ids(detail)
    api.client.post(f"/api/runs/{detail['run']['id']}/approve", json={"change_ids": [first]})

    assert api.client.patch(f"/api/changes/{first}", json={"summary": "Too late"}).status_code == 409
    assert (
        api.client.patch(f"/api/changes/{second}", json={"summary": "Too late"}).status_code == 409
    )  # dropped
    assert api.client.patch("/api/changes/nope", json={"summary": "x"}).status_code == 404


# ---------- approving ----------


def test_approving_creates_the_issues_in_jira_and_closes_the_run(api):
    detail = start_p1(api)
    run_id = detail["run"]["id"]
    api.client.patch(f"/api/changes/{draft_ids(detail)[0]}", json={"summary": "Reset password by email"})

    response = api.client.post(f"/api/runs/{run_id}/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "applied" and body["dropped"] == []
    assert [c["issue_key"] for c in body["created"]] == ["TEST-100", "TEST-101"]
    assert [f["summary"] for f in api.created] == [
        "Reset password by email",
        "Login audit",
    ]  # the PM's wording
    assert all("cognipm-drafted" in f["labels"] for f in api.created)
    after = api.client.get(f"/api/runs/{run_id}").json()
    assert after["run"]["status"] == "applied" and after["run"]["decided_at"] is not None
    assert after["seconds_to_decision"] is not None and after["can_decide"] is False
    assert [d["created_issue_key"] for d in after["drafts"]] == ["TEST-100", "TEST-101"]
    assert after["drafts"][0]["issue_url"].endswith("/browse/TEST-100")
    approval = api.conn.execute("SELECT actor, detail FROM audit_log WHERE action = 'approve'").fetchone()
    assert approval["actor"] == "human:reviewer" and "edited by the PM" in approval["detail"]
    assert api.conn.execute("SELECT consumed_at FROM approval_tokens").fetchone()["consumed_at"] is not None


def test_a_pm_can_approve_only_some_drafts_and_the_rest_are_dropped_not_created(api):
    detail = start_p1(api)
    keep, leave_out = draft_ids(detail)

    body = api.client.post(f"/api/runs/{detail['run']['id']}/approve", json={"change_ids": [keep]}).json()

    assert len(body["created"]) == 1 and body["dropped"] == [leave_out]
    assert [f["summary"] for f in api.created] == ["Password reset"]
    statuses = {
        d["id"]: d["status"] for d in api.client.get(f"/api/runs/{detail['run']['id']}").json()["drafts"]
    }
    assert statuses == {keep: "applied", leave_out: "rejected"}


def test_approving_the_same_run_twice_creates_nothing_the_second_time(api):
    run_id = start_p1(api)["run"]["id"]
    assert api.client.post(f"/api/runs/{run_id}/approve").status_code == 200

    second = api.client.post(f"/api/runs/{run_id}/approve")

    assert second.status_code == 409 and "applied" in second.json()["detail"]
    assert len(creates(api.seen)) == 2  # still just the two from the first approval


@pytest.mark.parametrize("body,status", [({"change_ids": []}, 400), ({"change_ids": ["nope"]}, 422)])
def test_approving_nothing_or_something_that_is_not_a_pending_draft_is_refused(api, body, status):
    run_id = start_p1(api)["run"]["id"]

    assert api.client.post(f"/api/runs/{run_id}/approve", json=body).status_code == status
    assert creates(api.seen) == []


def test_a_subtask_cannot_be_approved_without_its_parent_and_nothing_is_dropped_or_written(api):
    api.gemini.models.replies.append(drafts_reply([backlog_item("Password reset", RESET)]))
    run_id = api.client.post("/api/runs", json={"task": "p1", "input_text": NOTES}).json()["run_id"]
    wait_until_settled(api.client, run_id)
    parent = api.conn.execute("SELECT id FROM staged_changes").fetchone()["id"]
    api.conn.execute(
        "INSERT INTO staged_changes (id, run_id, kind, payload, parent_change_id, sources, reasoning) "
        "VALUES ('child', %s, 'subtask', '{\"summary\": \"Child\"}', %s, '[\"q\"]', 'long enough reasoning')",
        (run_id, parent),
    )
    api.conn.commit()

    response = api.client.post(f"/api/runs/{run_id}/approve", json={"change_ids": ["child"]})

    assert response.status_code == 400 and "tick the parent" in response.json()["detail"]
    assert creates(api.seen) == []
    assert {r["status"] for r in api.conn.execute("SELECT status FROM staged_changes").fetchall()} == {
        "proposed"
    }


def test_when_jira_fails_halfway_the_response_says_exactly_what_was_and_was_not_created(conn):
    api = build_api(conn, jira_options={"fail_on_summary": "Login audit"})
    with TestClient(app) as client:
        api.client = client
        detail = start_p1(api)
        first, second = draft_ids(detail)

        response = client.post(f"/api/runs/{detail['run']['id']}/approve")

        assert response.status_code == 502
        problem = response.json()["detail"]
        assert [c["issue_key"] for c in problem["created"]] == ["TEST-100"] and problem["not_created"] == [
            second
        ]
        assert "Login audit" in problem["message"] or second in problem["message"]
        failed = client.get(f"/api/runs/{detail['run']['id']}").json()
        assert failed["run"]["status"] == "failed" and failed["can_decide"] is True
        assert "stopped before every draft was created" in failed["status_note"]

        # Jira is healthy again: approving once more creates only what is left, never the first one twice.
        api.jira, _, retry_created = fake_jira(first_number=200)
        retry = client.post(f"/api/runs/{detail['run']['id']}/approve")

        assert retry.status_code == 200
        assert [c["issue_key"] for c in retry.json()["created"]] == ["TEST-200"]
        assert [f["summary"] for f in retry_created] == ["Login audit"]
        assert client.get(f"/api/runs/{detail['run']['id']}").json()["run"]["status"] == "applied"
    app.dependency_overrides.clear()


# ---------- rejecting and rerunning ----------


def test_rejecting_creates_nothing_and_keeps_the_note_as_feedback(api):
    detail = start_p1(api)
    run_id = detail["run"]["id"]

    response = api.client.post(f"/api/runs/{run_id}/reject", json={"comment": "Too vague"})

    assert response.status_code == 200
    after = api.client.get(f"/api/runs/{run_id}").json()
    assert after["run"]["status"] == "rejected" and after["run"]["comment"] == "Too vague"
    assert {d["status"] for d in after["drafts"]} == {"rejected"}
    assert after["can_decide"] is False and creates(api.seen) == []
    assert api.client.post(f"/api/runs/{run_id}/reject").status_code == 409  # already decided
    assert api.client.post(f"/api/runs/{run_id}/approve").status_code == 409


def test_an_applied_run_cannot_be_rejected_or_rerun(api):
    run_id = start_p1(api)["run"]["id"]
    api.client.post(f"/api/runs/{run_id}/approve")

    assert api.client.post(f"/api/runs/{run_id}/reject").status_code == 409
    assert api.client.post(f"/api/runs/{run_id}/rerun", json={"note": "again"}).status_code == 409


def test_a_rerun_starts_again_from_the_same_input_with_the_pms_note_and_links_back(api):
    first = start_p1(api, instructions="Keep it short")
    first_id = first["run"]["id"]
    api.gemini.models.replies.append(drafts_reply([backlog_item("Reset by email", RESET)]))

    response = api.client.post(
        f"/api/runs/{first_id}/rerun", json={"note": "Do not split the audit trail out"}
    )

    assert response.status_code == 202 and response.json()["rerun_of"] == first_id
    second = wait_until_settled(api.client, response.json()["run_id"])
    assert second["run"]["rerun_of"] == first_id and second["run"]["status"] == "awaiting_review"
    assert second["input_text"] == NOTES  # the same input, not re-pasted
    prompt = api.gemini.prompts[-1]
    assert "Keep it short" in prompt and "Do not split the audit trail out" in prompt
    old = api.client.get(f"/api/runs/{first_id}").json()["run"]
    assert old["status"] == "rejected" and "Rerun requested" in old["comment"]
    assert creates(api.seen) == []


def test_a_rerun_that_cannot_start_leaves_the_original_run_alone(api):
    first_id = start_p1(api)["run"]["id"]
    api.gemini.models.replies.append(lambda contents: (_ for _ in ()).throw(RuntimeError("boom")))

    response = api.client.post(f"/api/runs/{first_id}/rerun", json={"note": "again"})

    # The new run did open (so it is reported), but it failed; the original is rejected only once the new one exists.
    assert response.status_code == 202
    assert wait_until_settled(api.client, response.json()["run_id"])["run"]["status"] == "failed"


# ---------- chat ----------


def test_a_chat_turn_is_remembered_and_the_next_turn_sees_it(api):
    api.gemini.models.replies.extend(
        [
            call_reply("search_issues", jql="project = TEST"),
            text_chat_reply("Two issues."),
            text_chat_reply("Yes."),
        ]
    )

    first = api.client.post("/api/chat", json={"message": "What is open?"}).json()
    second = api.client.post("/api/chat", json={"session_id": first["session_id"], "message": "Sure?"}).json()

    assert first["answer"] == "Two issues." and first["tool_calls"] == [
        "search_issues({'jql': 'project = TEST'})"
    ]
    assert second["session_id"] == first["session_id"] and second["answer"] == "Yes."
    messages = api.conn.execute("SELECT role, content FROM chat_messages ORDER BY id").fetchall()
    assert [m["role"] for m in messages] == ["user", "agent", "user", "agent"]
    replayed = [c.role for c in api.gemini.calls[-1]["contents"]]
    assert replayed == ["user", "model", "user"]  # the whole earlier exchange went back to the model
    offered = {d.name for d in api.gemini.calls[0]["config"].tools[0].function_declarations}
    assert offered == {"search_issues", "get_issue"}  # Co-Pilot is offered the read tools and nothing else
    audit = api.conn.execute(
        "SELECT mode, detail FROM audit_log WHERE action = 'chat_turn' ORDER BY id"
    ).fetchone()
    assert (
        audit["mode"] == "M1" and "What is open" not in audit["detail"]
    )  # the question stays out of the log


def test_a_chat_with_an_unknown_session_is_refused_and_a_broken_model_is_a_readable_502(api):
    assert api.client.post("/api/chat", json={"session_id": "nope", "message": "hi"}).status_code == 404

    api.gemini.models.replies.append(
        lambda contents: (_ for _ in ()).throw(RuntimeError("secret internal detail"))
    )
    response = api.client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 502 and "secret internal detail" not in response.text


# ---------- the activity log ----------


def test_the_audit_filters_show_what_each_one_promises(api):
    kept = start_p1(api)
    approved_run = kept["run"]["id"]
    api.client.post(f"/api/runs/{approved_run}/approve", json={"change_ids": [draft_ids(kept)[0]]})
    start_p1(api, [drafts_reply([backlog_item("Login audit", AUDIT)])])  # left awaiting review
    rejected = start_p1(api, [drafts_reply([backlog_item("Another", RESET)])])
    api.client.post(f"/api/runs/{rejected['run']['id']}/reject", json={"comment": "no"})
    api.gemini.models.replies.append(text_chat_reply("An answer."))
    api.client.post("/api/chat", json={"message": "hello"})

    def actions(name, **params):
        rows = api.client.get("/api/audit", params={"filter": name, **params}).json()["rows"]
        return {r["action"] for r in rows}

    assert actions("changed_jira") == {"create_issue"}
    assert actions("rejected") == {"reject", "drop_draft"}
    assert actions("advice_only") == {"chat_turn"}
    assert "start_run" in actions("needs_you") and "reject" not in actions("needs_you")
    assert {"approve", "chat_turn", "reject"} <= actions("all")
    assert actions("all", run_id=approved_run) >= {"approve", "create_issue"}
    assert "chat_turn" not in actions("all", run_id=approved_run)
    newest_first = [r["id"] for r in api.client.get("/api/audit").json()["rows"]]
    assert newest_first == sorted(newest_first, reverse=True)
    assert api.client.get("/api/audit", params={"filter": "everything"}).status_code == 422


# ---------- the server restarting ----------


def test_a_run_left_running_by_a_restart_is_marked_failed_not_left_running_forever(conn):
    conn.execute(
        "INSERT INTO runs (id, mode, task_type, agent, scope, status) VALUES ('a', 'M2', 'p1', 'x', 's', 'running'), "
        "('b', 'M2', 'p1', 'x', 's', 'awaiting_review')"
    )
    conn.commit()

    assert launcher.fail_orphaned_runs(conn) == 1

    rows = {r["id"]: r for r in conn.execute("SELECT id, status, comment FROM runs").fetchall()}
    assert rows["a"]["status"] == "failed" and "restarted" in rows["a"]["comment"]
    assert rows["b"]["status"] == "awaiting_review"  # a run waiting for a person is untouched
