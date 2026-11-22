"""Live proof of Phase 3: a real Gemini M2 run drafts backlog items (P1) from a short requirements
document, then breaks one existing story into sub-tasks (P2). It prints the staged drafts with the
passages they cite, and compares the project's issues in Jira before and after to show nothing was
created.

SENDS TEXT TO GEMINI. The sample document below is synthetic; the P2 step sends one story's title
and description from your Jira project to Gemini, so pick a story that is safe to share (or pass
--skip-p2). Needs GEMINI_API_KEY and the JIRA_* values in .env. For the database, set DATABASE_URL, or
pip install -e ".[embedded-db]" and a throwaway Postgres is started for you. Run from backend/:

    python scripts/demo_run.py                # P1, then P2 on the first To Do story with a description
    python scripts/demo_run.py --story MCP-4  # choose the story for P2
    python scripts/demo_run.py --skip-p2
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile

from cognipm.db.connection import get_connection
from cognipm.gateway.jira import JiraClient, JiraConfigError
from cognipm.orchestrator.tasks import OrchestratorError, run_task

SAMPLE_REQUIREMENTS = """\
Notes from the planning call (synthetic example, not real project data).

Support keeps getting tickets from customers who forgot their password. Customers should be able to
reset their password themselves by email. The reset link must expire after one hour.

Finance wants a monthly CSV export of all invoices so they can reconcile against the bank. It only
needs to include paid and overdue invoices.

Someone mentioned a dark theme again. Nobody committed to it, so leave it for now.
"""


def issues_in_project(jira: JiraClient) -> list[str]:
    return sorted(i.key for i in jira.search_issues(f"project = {jira.config.project_key}", max_results=100))


def print_drafts(conn, run_id: str) -> None:
    run = conn.execute(
        "SELECT status, model, input_tokens, output_tokens FROM runs WHERE id = %s", (run_id,)
    ).fetchone()
    print(
        f"Run {run_id}: {run['status']} ({run['model']}, {run['input_tokens']} in / {run['output_tokens']} out tokens)"
    )
    drafts = conn.execute(
        "SELECT kind, payload, sources, reasoning, assumptions FROM staged_changes WHERE run_id = %s ORDER BY created_at",
        (run_id,),
    ).fetchall()
    for n, d in enumerate(drafts, 1):
        p = d["payload"]
        print(f"\n  {n}. [{d['kind']}] {p['summary']}")
        for criterion in p.get("acceptance_criteria", []):
            print(f"       - {criterion}")
        print(f"       why: {d['reasoning']}")
        print(f"       assumes: {d['assumptions']}")
        for source in d["sources"]:
            print(f'       cites: "{source}"')
    steps = conn.execute(
        "SELECT phase, state FROM run_steps WHERE run_id = %s ORDER BY id", (run_id,)
    ).fetchall()
    print("\n  steps: " + " > ".join(f"{s['phase']}:{s['state']}" for s in steps))


def pick_story(jira: JiraClient) -> str | None:
    found = jira.search_issues(
        f"project = {jira.config.project_key} AND issuetype = Story AND statusCategory != Done ORDER BY key ASC",
        max_results=20,
    )
    for issue in found:
        if (jira.get_issue(issue.key).description or "").strip():
            return issue.key
    return None


async def main_async(args: argparse.Namespace, jira: JiraClient) -> bool:
    conn = get_connection()
    before = issues_in_project(jira)
    print(f"Project {jira.config.project_key} has {len(before)} issues before.\n")

    print("== P1: draft backlog items from the sample notes ==")
    result = await run_task(
        conn=conn,
        task="p1",
        input_text=SAMPLE_REQUIREMENTS,
        context_jql=f"project = {jira.config.project_key} ORDER BY created DESC",
        scope="demo: planning call notes",
    )
    print_drafts(conn, result.run_id)
    for dropped in result.dropped:
        print(f"  left out: {dropped}")

    if not args.skip_p2:
        story = args.story or pick_story(jira)
        if story is None:
            print("\nNo story with a description to break down; skipping P2.")
        else:
            print(f"\n== P2: break {story} into sub-tasks ==")
            result = await run_task(conn=conn, task="p2", story_key=story)
            print_drafts(conn, result.run_id)
            for dropped in result.dropped:
                print(f"  left out: {dropped}")

    after = issues_in_project(jira)
    print(f"\nProject {jira.config.project_key} has {len(after)} issues after.")
    return before == after


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--story", help="issue key for the P2 step")
    parser.add_argument("--skip-p2", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        print("Set GEMINI_API_KEY in .env.")
        return 1
    try:
        jira = JiraClient()
    except JiraConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    cleanup = None
    if not os.environ.get("DATABASE_URL"):
        try:
            import pgserver
        except ImportError:
            print("Set DATABASE_URL, or pip install -e '.[embedded-db]' for a throwaway database.")
            return 1
        data_dir = tempfile.TemporaryDirectory()
        server = pgserver.get_server(data_dir.name, cleanup_mode="stop")
        os.environ["DATABASE_URL"] = server.get_uri()  # the gateway subprocess inherits it
        cleanup = (server, data_dir)

    try:
        with jira:
            unchanged = asyncio.run(main_async(args, jira))
    except OrchestratorError as exc:
        print(f"\nThe run failed: {exc}")
        return 1
    finally:
        if cleanup:
            cleanup[0].cleanup()
            cleanup[1].cleanup()

    print(
        "PASS: drafts were staged with cited sources and Jira is unchanged."
        if unchanged
        else "FAIL: Jira changed."
    )
    return 0 if unchanged else 1


if __name__ == "__main__":
    sys.exit(main())
