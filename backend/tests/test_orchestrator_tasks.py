"""P1 and P2 runs, end to end through the real graph and the real gateway tool registration
(an in-process MCP server), with only Gemini and Jira faked. The refusal cases matter most: a
quote that is not in the input, a malformed draft, and a mode that has no start_run."""

from __future__ import annotations

import pytest

from cognipm.gateway.jira import text_to_adf
from cognipm.gateway.server import build_server
from cognipm.orchestrator.tasks import OrchestratorError, run_task
from tests.fake_gemini import FakeGemini, backlog_item, drafts_reply, raw_text_reply, subtask
from tests.helpers import creates, issue_creating_site, make_client

NOTES = (
    "Meeting 12 Nov. Customers keep asking to reset their password by email.\n"
    "Admins need an audit trail of every login. Nothing else came up."
)
RESET = "Customers keep asking to reset their password by email."
AUDIT = "Admins need an audit trail of every login."
STORY_TEXT = "Users can reset their password. They request a link by email and it expires after one hour."


def jira_site(*, story_description: str | None = STORY_TEXT):
    """Canned Jira: two open issues, and TEST-1 as the story P2 breaks down."""
    story = {"summary": "Reset password"}
    if story_description is not None:
        story["description"] = text_to_adf(story_description)
    handler, _ = issue_creating_site(
        open_issues={"TEST-1": "Summary of TEST-1", "TEST-2": "Summary of TEST-2"}, existing={"TEST-1": story}
    )
    return handler


@pytest.fixture
def env(conn):
    jira, seen = make_client(jira_site())
    return conn, build_server("M2", jira=jira, conn=conn, agent="orchestrator:test"), seen


def staged(conn) -> list[dict]:
    return conn.execute(
        "SELECT kind, payload, sources, status FROM staged_changes ORDER BY created_at"
    ).fetchall()


def run_row(conn) -> dict:
    return conn.execute("SELECT * FROM runs").fetchone()


async def p1(env, gemini, **kwargs):
    conn, server, _ = env
    return await run_task(conn=conn, task="p1", input_text=NOTES, gemini=gemini, mcp_server=server, **kwargs)


# ---------- P1 ----------


async def test_p1_stages_a_cited_draft_per_item_and_never_touches_jira(env):
    conn, _, seen = env
    gemini = FakeGemini(
        [drafts_reply([backlog_item("Password reset", RESET), backlog_item("Login audit", AUDIT)])]
    )

    result = await p1(env, gemini)

    assert len(result.change_ids) == 2 and result.dropped == []
    rows = staged(conn)
    assert [r["payload"]["summary"] for r in rows] == ["Password reset", "Login audit"]
    assert rows[0]["sources"] == [RESET] and rows[0]["status"] == "proposed"
    run = run_row(conn)
    assert run["status"] == "awaiting_review" and run["task_type"] == "p1"
    assert run["agent"] == "orchestrator:test"
    assert (run["model"], run["input_tokens"], run["output_tokens"]) == ("gemini-3.6-flash", 100, 50)
    assert creates(seen) == []  # it read Jira to check the rules, but created nothing


async def test_p1_records_every_step_in_order_so_a_restart_can_replay_it(env):
    conn, _, _ = env
    gemini = FakeGemini([drafts_reply([backlog_item("Password reset", RESET)])])

    await p1(env, gemini)

    steps = conn.execute("SELECT phase, state, tool FROM run_steps ORDER BY id").fetchall()
    phases = [s["phase"] for s in steps]
    assert phases == sorted(phases, key=["analysing", "generating", "verifying", "staging"].index)
    assert ("staging", "end", "finish_run") in [(s["phase"], s["state"], s["tool"]) for s in steps]


async def test_p1_listener_sees_the_steps_and_a_broken_listener_does_not_break_the_run(env):
    seen_events = []

    def flaky(event):
        seen_events.append(event)
        raise RuntimeError("listener bug")

    gemini = FakeGemini([drafts_reply([backlog_item("Password reset", RESET)])])

    result = await p1(env, gemini, on_step=flaky)

    assert len(result.change_ids) == 1
    assert {"analysing", "generating", "verifying", "staging"} <= {e["phase"] for e in seen_events}


async def test_p1_shows_the_model_the_existing_backlog_to_avoid_duplicates(env):
    gemini = FakeGemini([drafts_reply([backlog_item("Password reset", RESET)])])

    await p1(env, gemini, context_jql="project = TEST")

    assert "TEST-1: Summary of TEST-1" in gemini.prompts[0]


async def test_a_quote_that_is_not_in_the_input_is_dropped_and_its_draft_is_not_staged(env):
    conn, _, _ = env
    invented = "The CEO demanded single sign-on by Friday."
    gemini = FakeGemini(
        [drafts_reply([backlog_item("Password reset", RESET), backlog_item("Single sign-on", invented)])]
    )

    result = await p1(env, gemini)

    assert [r["payload"]["summary"] for r in staged(conn)] == ["Password reset"]
    assert any("Single sign-on" in d and "not in the input" in d for d in result.dropped)


async def test_a_typographic_difference_does_not_make_a_real_quote_look_invented(env):
    conn, _, _ = env
    curly = "Customers keep asking to reset their  PASSWORD by email."  # extra space, different case
    gemini = FakeGemini([drafts_reply([backlog_item("Password reset", curly)])])

    await p1(env, gemini)

    assert len(staged(conn)) == 1


async def test_when_nothing_is_traceable_the_model_gets_one_more_try_with_feedback(env):
    conn, _, _ = env
    gemini = FakeGemini(
        [
            drafts_reply([backlog_item("Single sign-on", "Not in the notes at all.")]),
            drafts_reply([backlog_item("Password reset", RESET)]),
        ]
    )

    result = await p1(env, gemini)

    assert len(gemini.calls) == 2
    assert (
        "Your previous attempt was rejected" in gemini.prompts[1] and "Not in the notes" in gemini.prompts[1]
    )
    assert len(result.change_ids) == 1
    assert run_row(conn)["input_tokens"] == 200  # both attempts are counted


async def test_when_nothing_is_ever_traceable_the_run_fails_and_stages_nothing(env):
    conn, _, _ = env
    bad = drafts_reply([backlog_item("Single sign-on", "Invented quote.")])
    gemini = FakeGemini([bad, bad])

    with pytest.raises(OrchestratorError, match="no draft could be traced"):
        await p1(env, gemini)

    assert staged(conn) == []
    assert run_row(conn)["status"] == "failed"
    assert len(gemini.calls) == 2  # bounded: it does not loop forever


async def test_a_malformed_draft_is_rejected_before_the_gateway_ever_sees_it(env):
    conn, _, _ = env
    no_criteria = backlog_item("Password reset", RESET, acceptance_criteria=[])
    gemini = FakeGemini([drafts_reply([no_criteria]), raw_text_reply("not json at all")])

    with pytest.raises(OrchestratorError, match="no draft could be traced"):
        await p1(env, gemini)

    assert staged(conn) == []
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE action = 'propose_backlog_item'"
    ).fetchone() == {"n": 0}


async def test_a_draft_the_gateway_refuses_is_reported_and_the_rest_still_stage(env):
    conn, _, _ = env
    blank_title = backlog_item("   ", RESET)  # passes the schema, refused by the gateway's own rules
    gemini = FakeGemini([drafts_reply([blank_title, backlog_item("Login audit", AUDIT)])])

    result = await p1(env, gemini)

    assert [r["payload"]["summary"] for r in staged(conn)] == ["Login audit"]
    assert any("the gateway refused it" in d and "summary must not be empty" in d for d in result.dropped)


async def test_p1_needs_input_text(env):
    conn, server, _ = env
    with pytest.raises(ValueError, match="input_text"):
        await run_task(conn=conn, task="p1", input_text="  ", gemini=FakeGemini([]), mcp_server=server)


# ---------- P2 ----------


async def test_p2_breaks_an_existing_story_into_subtasks_under_it(env):
    conn, _, seen = env
    quote = "They request a link by email and it expires after one hour."
    gemini = FakeGemini(
        [drafts_reply([subtask("Send the reset email", quote), subtask("Expire the link", quote)])]
    )

    result = await run_task(conn=conn, task="p2", story_key="TEST-1", gemini=gemini, mcp_server=env[1])

    assert len(result.change_ids) == 2
    rows = staged(conn)
    assert {r["kind"] for r in rows} == {"subtask"}
    assert all(r["payload"]["parent_key"] == "TEST-1" for r in rows)
    assert run_row(conn)["task_type"] == "p2" and run_row(conn)["scope"] == "story TEST-1"
    assert "Reset password" in gemini.prompts[0] and quote in gemini.prompts[0]
    assert creates(seen) == []  # it read the story and checked the rules, nothing more


async def test_p2_cannot_cite_text_that_is_not_in_the_story(env):
    conn, _, _ = env
    gemini = FakeGemini([drafts_reply([subtask("Add SSO", "Single sign-on is required.")])] * 2)

    with pytest.raises(OrchestratorError, match="no draft could be traced"):
        await run_task(conn=conn, task="p2", story_key="TEST-1", gemini=gemini, mcp_server=env[1])

    assert staged(conn) == [] and run_row(conn)["status"] == "failed"


async def test_p2_on_a_story_with_no_description_fails_without_calling_gemini(conn):
    jira, _ = make_client(jira_site(story_description=None))
    server = build_server("M2", jira=jira, conn=conn)
    gemini = FakeGemini([])

    with pytest.raises(OrchestratorError, match="no description"):
        await run_task(conn=conn, task="p2", story_key="TEST-1", gemini=gemini, mcp_server=server)

    assert gemini.calls == []
    assert run_row(conn)["status"] == "failed"


async def test_p2_needs_a_story_key(env):
    conn, server, _ = env
    with pytest.raises(ValueError, match="story_key"):
        await run_task(conn=conn, task="p2", gemini=FakeGemini([]), mcp_server=server)


# ---------- the thesis: the mode decides what a run can do ----------


async def test_a_run_at_m1_cannot_begin_because_start_run_does_not_exist_for_it(conn):
    jira, seen = make_client(jira_site())
    m1_server = build_server("M1", jira=jira, conn=conn)
    gemini = FakeGemini([])

    with pytest.raises(OrchestratorError, match="refused to open a run"):
        await run_task(conn=conn, task="p1", input_text=NOTES, mode="M1", gemini=gemini, mcp_server=m1_server)

    assert gemini.calls == []  # it never even asked the model
    assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone() == {"n": 0}
    assert seen == []
