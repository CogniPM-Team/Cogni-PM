"""Pause, resume, stop, cancel, and the agent asking a question. A person's request only sets a flag; the running task
acts on it between steps, so these tests drive a real run (scripted model, real gateway tools) and press the controls
while it is in flight. The refusals matter most: you cannot pause what is not running, stop what is over, or answer
a question nobody asked, and an ended run never writes to Jira."""

from __future__ import annotations

import asyncio
import json
import os
import time
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient

from cognipm.api.launcher import fail_orphaned_runs
from cognipm.api.main import app
from cognipm.orchestrator.control import RunEnded, checkpoint, settle
from tests.fake_gemini import backlog_item, drafts_reply
from tests.helpers import creates
from tests.test_api import AUDIT, NOTES, RESET, build_api
from tests.test_insights import add_run

DRAFTS = [backlog_item("Password reset", RESET), backlog_item("Login audit", AUDIT)]


@pytest.fixture
def api(conn):
    api = build_api(conn)
    with TestClient(app) as client:
        api.client = client
        yield api
    app.dependency_overrides.clear()


def press(control: str):
    """The PM pressing a button while the model is thinking: a reply that, before answering, asks for `control` on the
    newest run. (A separate connection, as the API's own request would be.)"""

    def reply(contents):
        with psycopg.connect(os.environ["DATABASE_URL"]) as other:
            other.execute(
                "UPDATE runs SET control = %s WHERE id = (SELECT id FROM runs ORDER BY created_at DESC LIMIT 1)",
                (control,),
            )
        return drafts_reply(DRAFTS)

    return reply


def asks(*questions: str):
    return SimpleNamespace(text=json.dumps({"items": [], "questions": list(questions)}), usage_metadata=None)


def start(api, replies, **body) -> str:
    api.gemini.models.replies.extend(replies)
    response = api.client.post("/api/runs", json={"task": "p1", "input_text": NOTES} | body)
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def detail(api, run_id) -> dict:
    return api.client.get(f"/api/runs/{run_id}").json()


def wait_for(api, run_id, *statuses, timeout=15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = detail(api, run_id)
        if d["run"]["status"] in statuses:
            return d
        time.sleep(0.05)
    raise AssertionError(f"the run never reached {statuses}; it is {detail(api, run_id)['run']['status']}")


def actions(api, run_id) -> list[str]:
    rows = api.client.get("/api/audit", params={"run_id": run_id}).json()["rows"]
    return [r["action"] for r in rows]


# ---------- pause and resume ----------


def test_a_run_paused_while_the_model_was_thinking_holds_before_its_next_step_and_carries_on_when_resumed(
    api,
):
    run_id = start(api, [press("pause")])

    paused = wait_for(api, run_id, "paused")

    assert paused["control"] == "pause" and paused["can_control"] and "Paused" in paused["status_note"]
    assert paused["drafts"] == []  # held before anything was checked or staged
    assert creates(api.seen) == []

    response = api.client.post(f"/api/runs/{run_id}/resume")
    assert response.status_code == 200 and response.json()["control"] is None

    done = wait_for(api, run_id, "awaiting_review")
    assert len(done["drafts"]) == 2 and done["control"] is None
    assert "resume_run" in actions(
        api, run_id
    )  # the pause was simulated in the model reply; the resume was a request
    assert creates(api.seen) == []  # still nothing in Jira: only an approval does that


def test_pausing_through_the_api_sets_the_request_and_records_who_asked(api):
    add_run(api.conn, "busy", "running", drafts=[])

    response = api.client.post("/api/runs/busy/pause")

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["control"]) == (
        "running",
        "pause",
    )  # asked, not yet done
    row = next(
        r
        for r in api.client.get("/api/audit", params={"run_id": "busy"}).json()["rows"]
        if r["action"] == "pause_run"
    )
    assert (row["actor"], row["outcome"]) == ("human:reviewer", "requested")


def test_a_pause_can_be_taken_back_before_it_has_taken_effect(api):
    run_id = start(api, [drafts_reply(DRAFTS)])
    api.conn.execute("UPDATE runs SET status = 'running', control = 'pause' WHERE id = %s", (run_id,))
    api.conn.commit()

    response = api.client.post(f"/api/runs/{run_id}/resume")

    assert response.status_code == 200 and response.json()["control"] is None


def test_only_a_running_run_can_be_paused_and_only_a_paused_one_resumed(api):
    run_id = start(api, [drafts_reply(DRAFTS)])
    wait_for(api, run_id, "awaiting_review")

    pause = api.client.post(f"/api/runs/{run_id}/pause")
    resume = api.client.post(f"/api/runs/{run_id}/resume")

    assert pause.status_code == 409 and "only a running run can be paused" in pause.json()["detail"]
    assert resume.status_code == 409 and "only a paused run can be resumed" in resume.json()["detail"]
    assert api.client.post("/api/runs/nope/pause").status_code == 404


def test_a_second_pause_is_refused_while_the_first_is_waiting_to_take_effect(api):
    add_run(api.conn, "busy", "running", drafts=[])
    api.conn.execute("UPDATE runs SET control = 'pause' WHERE id = 'busy'")
    api.conn.commit()

    response = api.client.post("/api/runs/busy/pause")

    assert response.status_code == 409 and "already waiting to take effect" in response.json()["detail"]


# ---------- stop and cancel ----------


def test_stopping_a_paused_run_ends_it_with_nothing_to_approve_and_nothing_in_jira(api):
    run_id = start(api, [press("pause")])
    wait_for(api, run_id, "paused")

    assert api.client.post(f"/api/runs/{run_id}/stop").status_code == 200

    stopped = wait_for(api, run_id, "stopped")
    assert stopped["drafts"] == [] and stopped["control"] is None and "Stopped" in stopped["status_note"]
    assert not stopped["can_decide"] and not stopped["can_control"]
    assert api.client.post(f"/api/runs/{run_id}/approve").status_code == 409
    assert creates(api.seen) == []
    assert "stop_run" in actions(api, run_id)


def test_cancelling_a_running_run_ends_it_at_the_next_step(api):
    run_id = start(api, [press("cancel")])

    cancelled = wait_for(api, run_id, "cancelled")

    assert cancelled["drafts"] == [] and "Cancelled" in cancelled["status_note"]
    assert creates(api.seen) == []


def test_cancelling_discards_what_was_staged_but_stopping_keeps_it(conn):
    add_run(conn, "cancelled-run", "running", drafts=["proposed", "proposed"])
    add_run(conn, "stopped-run", "running", drafts=["proposed"])

    settle(conn, "cancelled-run", "cancelled")
    settle(conn, "stopped-run", "stopped")

    rows = conn.execute("SELECT run_id, status FROM staged_changes ORDER BY run_id").fetchall()
    assert {(r["run_id"], r["status"]) for r in rows} == {
        ("cancelled-run", "rejected"),
        ("stopped-run", "proposed"),
    }
    assert (
        conn.execute("SELECT status FROM runs WHERE id = 'cancelled-run'").fetchone()["status"] == "cancelled"
    )


def test_a_run_that_is_over_cannot_be_stopped_or_cancelled_and_a_review_is_pointed_at_reject(api):
    run_id = start(api, [drafts_reply(DRAFTS)])
    wait_for(api, run_id, "awaiting_review")

    stop = api.client.post(f"/api/runs/{run_id}/stop")
    cancel = api.client.post(f"/api/runs/{run_id}/cancel")

    assert stop.status_code == 409 and "Reject it instead" in stop.json()["detail"]
    assert cancel.status_code == 409
    assert detail(api, run_id)["run"]["status"] == "awaiting_review"  # untouched


# ---------- the agent asks a question ----------


def test_a_run_too_vague_to_draft_from_asks_and_waits_without_drafting_or_failing(api):
    run_id = start(api, [asks("Which payment provider?", "Who can see refunds?")])

    waiting = wait_for(api, run_id, "waiting_for_information")

    assert waiting["question"] == "Which payment provider?\nWho can see refunds?"
    assert waiting["can_answer"] and waiting["drafts"] == []
    assert "needs an answer" in waiting["status_note"]
    assert "ask_clarification" in actions(api, run_id)
    assert (
        api.client.get("/api/runs").json()["waiting"][0]["id"] == run_id
    )  # it is in the PM's inbox: it needs them


def test_answering_carries_the_same_run_on_with_the_answer_and_it_does_not_ask_again(api):
    run_id = start(api, [asks("Which payment provider?")])
    wait_for(api, run_id, "waiting_for_information")
    api.gemini.models.replies.append(drafts_reply(DRAFTS))

    response = api.client.post(f"/api/runs/{run_id}/answer", json={"text": "  Stripe  "})

    assert response.status_code == 202
    done = wait_for(api, run_id, "awaiting_review")
    assert len(done["drafts"]) == 2 and done["question"] is None
    assert "The agent asked: Which payment provider?\nThe PM answered: Stripe" in done["instructions"]
    second_prompt = api.gemini.prompts[-1]
    assert "The PM answered: Stripe" in second_prompt and "Do not ask again" in second_prompt
    assert len(api.client.get("/api/runs").json()["waiting"]) == 1  # the same run, not a new one
    log = api.client.get("/api/audit", params={"run_id": run_id}).json()["rows"]
    answered = next(r for r in log if r["action"] == "answer_clarification")
    assert "Stripe" not in json.dumps(answered)  # how long, never what


def test_a_run_that_asks_again_after_being_answered_fails_instead_of_asking_forever(api):
    run_id = start(api, [asks("Which provider?")])
    wait_for(api, run_id, "waiting_for_information")
    api.gemini.models.replies.extend([asks("And which currency?")] * 2)

    api.client.post(f"/api/runs/{run_id}/answer", json={"text": "Stripe"})

    failed = wait_for(api, run_id, "failed")
    assert failed["drafts"] == [] and "nothing was staged" in failed["run"]["comment"]


def test_answering_needs_an_answer_and_a_question_to_answer(api):
    asked = start(api, [asks("Which provider?")])
    wait_for(api, asked, "waiting_for_information")
    finished = start(api, [drafts_reply(DRAFTS)])
    wait_for(api, finished, "awaiting_review")

    assert api.client.post(f"/api/runs/{asked}/answer", json={"text": "   "}).status_code == 422
    assert api.client.post(f"/api/runs/{asked}/answer", json={}).status_code == 422
    not_waiting = api.client.post(f"/api/runs/{finished}/answer", json={"text": "Stripe"})
    assert not_waiting.status_code == 409 and "not waiting for an answer" in not_waiting.json()["detail"]
    assert (
        detail(api, asked)["run"]["status"] == "waiting_for_information"
    )  # a refused answer changed nothing


def test_a_run_waiting_for_an_answer_can_be_stopped_or_cancelled_at_once(api):
    first = start(api, [asks("Which provider?")])
    wait_for(api, first, "waiting_for_information")
    second = start(api, [asks("Which provider?")])
    wait_for(api, second, "waiting_for_information")

    assert api.client.post(f"/api/runs/{first}/stop").json()["status"] == "stopped"
    assert api.client.post(f"/api/runs/{second}/cancel").json()["status"] == "cancelled"
    assert api.client.get("/api/runs").json()["waiting"] == []  # nothing waits on a person any more


# ---------- around the edges ----------


def test_a_restart_marks_runs_that_were_running_paused_or_waiting_as_failed_but_leaves_the_rest(conn):
    for run_id, status in [
        ("a", "running"),
        ("b", "paused"),
        ("c", "waiting_for_information"),
        ("d", "awaiting_review"),
        ("e", "stopped"),
    ]:
        add_run(conn, run_id, status, drafts=[])

    assert fail_orphaned_runs(conn) == 3

    states = {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM runs").fetchall()}
    assert states == {"a": "failed", "b": "failed", "c": "failed", "d": "awaiting_review", "e": "stopped"}


def test_insights_counts_stopped_and_cancelled_runs_as_open_and_shows_them_on_their_own_line(api):
    add_run(api.conn, "ok", "applied", drafts=["created"], minutes=2)
    add_run(api.conn, "s", "stopped", drafts=[])
    add_run(api.conn, "c", "cancelled", drafts=[])
    add_run(api.conn, "w", "awaiting_review", drafts=["proposed"])

    n = api.client.get("/api/insights").json()

    assert (n["runs_started"], n["runs_decided"], n["runs_open"], n["runs_ended_early"]) == (4, 1, 3, 2)


async def test_a_checkpoint_lets_a_run_through_ends_it_on_stop_and_cancel_and_holds_while_paused(conn):
    add_run(conn, "r", "running", drafts=[])
    await checkpoint(conn, "r", poll=0.01)  # nothing asked: straight through

    for control, how in (("stop", "stopped"), ("cancel", "cancelled")):
        conn.execute("UPDATE runs SET control = %s WHERE id = 'r'", (control,))
        conn.commit()
        with pytest.raises(RunEnded) as ended:
            await checkpoint(conn, "r", poll=0.01)
        assert ended.value.how == how

    conn.execute("UPDATE runs SET control = 'pause' WHERE id = 'r'")
    conn.commit()
    waiter = asyncio.create_task(checkpoint(conn, "r", poll=0.01))
    await asyncio.sleep(0.1)
    assert not waiter.done()
    assert conn.execute("SELECT status FROM runs WHERE id = 'r'").fetchone()["status"] == "paused"

    conn.execute("UPDATE runs SET control = NULL WHERE id = 'r'")
    conn.commit()
    await asyncio.wait_for(waiter, 2)
    assert (
        conn.execute("SELECT status FROM runs WHERE id = 'r'").fetchone()["status"] == "running"
    )  # and it carries on
