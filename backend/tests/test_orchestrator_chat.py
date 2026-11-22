"""The M1 chat loop against the real tool registration: the model is offered only the two read
tools, and a model that tries to call a write tool anyway gets a refusal, not a result."""

from __future__ import annotations

import httpx
import pytest

from cognipm.gateway.server import build_server
from cognipm.orchestrator.chat import MAX_TOOL_CALLS, ChatError, run_chat_turn
from tests.fake_gemini import FakeGemini, call_reply, text_chat_reply
from tests.helpers import make_client, raw_issue


def jira_site():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rest/api/3/search/jql":
            return httpx.Response(200, json={"issues": [raw_issue("TEST-1")]})
        return httpx.Response(404, json={"errorMessages": ["unexpected"]})

    return handler


@pytest.fixture
def m1_server(conn):
    jira, seen = make_client(jira_site())
    return build_server("M1", jira=jira, conn=conn), seen


def offered_tools(gemini: FakeGemini) -> set[str]:
    declarations = gemini.calls[0]["config"].tools[0].function_declarations
    return {d.name for d in declarations}


async def test_the_model_is_offered_only_the_read_tools_and_answers_from_what_it_read(m1_server):
    server, seen = m1_server
    gemini = FakeGemini(
        [call_reply("search_issues", jql="project = TEST"), text_chat_reply("TEST-1 is in scope.")]
    )

    answer, tool_calls = await run_chat_turn(
        history=[], message="What is in scope?", gemini=gemini, mcp_server=server
    )

    assert answer == "TEST-1 is in scope."
    assert tool_calls == ["search_issues({'jql': 'project = TEST'})"]
    assert offered_tools(gemini) == {"search_issues", "get_issue"}
    assert [r.method for r in seen] == ["POST"]


async def test_a_model_that_asks_for_a_write_tool_gets_a_refusal_and_nothing_happens(m1_server, conn):
    server, seen = m1_server
    gemini = FakeGemini(
        [
            call_reply("start_run", task_type="p1", scope="sneaky"),
            text_chat_reply("I can't change anything from here."),
        ]
    )

    answer, _ = await run_chat_turn(history=[], message="Create a story", gemini=gemini, mcp_server=server)

    assert answer == "I can't change anything from here."
    response = gemini.calls[1]["contents"][-1].parts[0].function_response
    assert response.name == "start_run" and "error" in response.response  # the tool is not there to call
    assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone() == {"n": 0}
    assert seen == []


async def test_earlier_turns_are_replayed_so_the_model_has_the_context(m1_server):
    server, _ = m1_server
    gemini = FakeGemini([text_chat_reply("Yes.")])
    history = [{"role": "user", "content": "Hi"}, {"role": "agent", "content": "Hello"}]

    await run_chat_turn(history=history, message="Still there?", gemini=gemini, mcp_server=server)

    roles = [c.role for c in gemini.calls[0]["contents"]]
    assert roles == ["user", "model", "user"]


async def test_a_question_that_needs_too_many_reads_fails_clearly_instead_of_looping(m1_server):
    server, _ = m1_server
    gemini = FakeGemini([call_reply("search_issues", jql="project = TEST")] * (MAX_TOOL_CALLS + 5))

    with pytest.raises(ChatError, match="narrower question"):
        await run_chat_turn(history=[], message="Everything", gemini=gemini, mcp_server=server)

    assert len(gemini.calls) == MAX_TOOL_CALLS  # it stopped at the cap
