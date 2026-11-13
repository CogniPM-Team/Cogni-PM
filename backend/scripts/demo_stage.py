"""Live proof that the gateway enforces autonomy by which tools exist, and that M2 stages a
draft without touching Jira.

It launches the gateway as a real MCP client over stdio (the way an orchestrator will), once per
mode, and prints what each mode was offered. Then, as M2, it runs one P1 run: start_run,
propose_backlog_item, finish_run - and compares the project's issues in Jira before and after
to show nothing was created. It also tries commit_changes at M2 to show the tool is not there.

Needs a database: set DATABASE_URL (see README), or pass nothing and the demo starts a throwaway
embedded Postgres if `pip install -e ".[embedded-db]"` was done. Run from backend/:

    python scripts/demo_stage.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from cognipm.gateway.jira import JiraClient, JiraConfigError

SOURCE = "Customers must be able to reset their password by email."


async def call(session: ClientSession, tool: str, **arguments):
    result = await session.call_tool(tool, arguments)
    if result.is_error:
        raise RuntimeError(f"{tool} failed: {result.content[0].text}")
    return result


async def run_as(mode: str, env: dict[str, str], work=None) -> list[str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cognipm.gateway.server"],
        env={**os.environ, **env, "COGNIPM_MODE": mode, "COGNIPM_AGENT": "demo"},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = sorted(t.name for t in (await session.list_tools()).tools)
        if work:
            await work(session)
        return tools


async def stage_one_draft(session: ClientSession) -> None:
    started = await call(session, "start_run", task_type="p1", scope="demo: password reset notes")
    run_id = started.structured_content["result"]
    proposed = await call(
        session,
        "propose_backlog_item",
        run_id=run_id,
        summary="[CogniPM demo] Reset password by email",
        description="As a customer I can reset my password using a link sent by email.",
        acceptance_criteria=["The email arrives within a minute", "The link expires after one hour"],
        reasoning="The notes state this requirement directly.",
        assumptions="NA",
        sources=[SOURCE],
    )
    print(f"Staged draft {proposed.structured_content['result']} in run {run_id}")
    finished = await call(session, "finish_run", run_id=run_id)
    summary = json.loads(finished.content[0].text)  # a dict result comes back as JSON text
    print(f"Run is now {summary['status']} with {len(summary['staged_changes'])} draft(s)")
    try:
        await call(session, "commit_changes", run_id=run_id, approval_token="x")
    except Exception as exc:  # noqa: BLE001 - the point is that it fails
        print(f"commit_changes at M2 -> refused by the protocol: {str(exc)[:90]}")


def issues_in_project(jira: JiraClient) -> list[str]:
    return sorted(i.key for i in jira.search_issues(f"project = {jira.config.project_key}", max_results=100))


def main() -> int:
    try:
        jira = JiraClient()
    except JiraConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    env: dict[str, str] = {}
    cleanup = None
    if not os.environ.get("DATABASE_URL"):
        try:
            import pgserver
        except ImportError:
            print("Set DATABASE_URL, or pip install -e '.[embedded-db]' for a throwaway database.")
            return 1
        data_dir = tempfile.TemporaryDirectory()
        server = pgserver.get_server(data_dir.name, cleanup_mode="stop")
        env["DATABASE_URL"] = server.get_uri()
        cleanup = (server, data_dir)

    try:
        with jira:
            before = issues_in_project(jira)
            print(f"Project {jira.config.project_key} has {len(before)} issues before.\n")
            for mode in ("M1", "M2", "M3"):
                tools = asyncio.run(run_as(mode, env, stage_one_draft if mode == "M2" else None))
                print(f"{mode} offered: {', '.join(tools)}")
            after = issues_in_project(jira)
            print(f"\nProject {jira.config.project_key} has {len(after)} issues after.")
            ok = before == after
    finally:
        if cleanup:
            cleanup[0].cleanup()
            cleanup[1].cleanup()

    print("PASS: a draft was staged and Jira is unchanged." if ok else "FAIL: Jira changed during the demo.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
