"""The test that proves the thesis: the server's advertised tool list at M1 contains no write
tool at all, and commit_changes exists only at M3. Autonomy is enforced by which tools exist,
not by asking the model to behave."""

from __future__ import annotations

import asyncio

import pytest

from cognipm.gateway.server import TOOLS_BY_MODE, build_server
from tests.helpers import make_client

READ_TOOLS = {"search_issues", "get_issue"}
PROPOSE_TOOLS = {"start_run", "propose_backlog_item", "propose_task_breakdown", "finish_run"}


def _tool_names(conn, mode: str) -> set[str]:
    jira, _ = make_client(lambda request: None)
    server = build_server(mode, jira=jira, conn=conn)
    return {t.name for t in asyncio.run(server.list_tools())}


def test_m1_registers_only_read_tools(conn):
    names = _tool_names(conn, "M1")

    assert names == READ_TOOLS
    assert not names & PROPOSE_TOOLS  # absent, not disabled: M1 has no write surface at all
    assert "commit_changes" not in names


def test_m2_registers_read_and_propose_tools_but_not_commit(conn):
    names = _tool_names(conn, "M2")

    assert names == READ_TOOLS | PROPOSE_TOOLS
    assert "commit_changes" not in names


def test_m3_adds_commit_changes(conn):
    assert _tool_names(conn, "M3") == READ_TOOLS | PROPOSE_TOOLS | {"commit_changes"}


def test_registered_tools_always_match_the_enforcement_table(conn):
    for mode, expected in TOOLS_BY_MODE.items():
        assert _tool_names(conn, mode) == set(expected)


@pytest.mark.parametrize("mode", ["L2", "M4", "", "m2"])
def test_an_unknown_mode_is_rejected(conn, mode):
    jira, _ = make_client(lambda request: None)
    with pytest.raises(ValueError, match="Unknown mode"):
        build_server(mode, jira=jira, conn=conn)


async def test_the_reason_for_a_refusal_reaches_the_caller_so_it_can_fix_the_draft(conn):
    from mcp.client import Client

    jira, _ = make_client(lambda request: None)
    async with Client(build_server("M2", jira=jira, conn=conn)) as client:
        started = await client.call_tool("start_run", {"task_type": "p1", "scope": "notes"})
        refused = await client.call_tool(
            "propose_backlog_item",
            {
                "run_id": started.structured_content["result"],
                "summary": "A story",
                "description": "d",
                "acceptance_criteria": ["c"],
                "reasoning": "too short",
                "assumptions": "NA",
                "sources": ["quote"],
            },
        )

    assert refused.is_error
    assert "reasoning must be at least 20 characters" in refused.content[0].text
