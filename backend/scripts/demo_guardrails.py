"""Live proof that the guardrails refuse, name themselves, and leave Jira unchanged.

Against your real Jira project it tries four things an agent must not manage, through the gateway's
own propose tools at M2: a sub-task whose parent is in another project, a backlog item whose title is
already open in Jira, a sub-task under a parent that does not exist, and a Story with no acceptance
criteria. Then it stages one good draft to show the same chain lets a proper draft through. It prints
each refusal with the guardrail that made it, the audit rows, and the project's issue count before and
after. Nothing is created in Jira (propose never writes), and no model is called.

Needs the JIRA_* values in .env. For the database, set DATABASE_URL, or pip install -e ".[embedded-db]"
and a throwaway Postgres is started for you. Run from backend/:

    python scripts/demo_guardrails.py
"""

from __future__ import annotations

import os
import sys
import tempfile

from cognipm.db.connection import get_connection
from cognipm.gateway.jira import JiraClient, JiraConfigError
from cognipm.gateway.server import GatewayTools

REASONING = "Part of the guardrail demonstration."


def main() -> int:
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
        os.environ["DATABASE_URL"] = server.get_uri()
        cleanup = (server, data_dir)

    try:
        with jira:
            ok = run(jira)
    finally:
        if cleanup:
            cleanup[0].cleanup()
            cleanup[1].cleanup()

    print(
        "\nPASS: every bad draft was refused and logged, a good one passed, and Jira is unchanged."
        if ok
        else "\nFAIL"
    )
    return 0 if ok else 1


def run(jira: JiraClient) -> bool:
    conn = get_connection()
    project = jira.config.project_key
    open_issues = jira.search_issues(
        f"project = {project} AND statusCategory != Done ORDER BY key ASC", max_results=20
    )
    before = sorted(i.key for i in jira.search_issues(f"project = {project}", max_results=100))
    if not open_issues:
        print("The project has no open issue to use as a duplicate; add one and retry.")
        return False
    existing = open_issues[0]
    print(
        f"Project {project} has {len(before)} issues. Open example for the duplicate test: {existing.key} {existing.summary!r}\n"
    )

    tools = GatewayTools(jira, conn, "M2", agent="demo")
    run_id = tools.start_run("p2", "guardrail demonstration")

    def attempt(label: str, call, expect: str) -> bool:
        try:
            call()
        except Exception as exc:  # noqa: BLE001 - the point is to show the refusal
            refused = expect in str(exc) or expect in " ".join(a for a in conn_refusals())
            print(f"  REFUSED  {label}\n           {exc}")
            return refused
        print(f"  NOT REFUSED (bad)  {label}")
        return False

    def conn_refusals() -> list[str]:
        return [
            r["action"]
            for r in conn.execute("SELECT action FROM audit_log WHERE outcome = 'refused'").fetchall()
        ]

    results = [
        attempt(
            "sub-task under a parent in another project",
            lambda: tools.propose_task_breakdown(
                run_id, "Orphan in another project", "d", REASONING, "NA", ["q"], parent_key="OTHER-1"
            ),
            "outside project",
        ),
        attempt(
            f"backlog item titled like the open issue {existing.key}",
            lambda: tools.propose_backlog_item(
                run_id, existing.summary.upper(), "d", ["It works"], REASONING, "NA", ["q"]
            ),
            "already open",
        ),
        attempt(
            "sub-task under a parent that does not exist",
            lambda: tools.propose_task_breakdown(
                run_id, "Orphan sub-task", "d", REASONING, "NA", ["q"], parent_key=f"{project}-9999"
            ),
            "could not be read",
        ),
        attempt(
            "Story with no acceptance criteria",
            lambda: tools.propose_backlog_item(
                run_id, "Story without criteria", "d", [], REASONING, "NA", ["q"]
            ),
            "acceptance criterion",
        ),
    ]

    print("\n  A good draft goes through the same chain:")
    tools.propose_backlog_item(
        run_id, "[CogniPM demo] A well-formed story", "d", ["It works"], REASONING, "NA", ["q"]
    )
    print("  STAGED   a well-formed story (nothing created in Jira)")

    print("\nAudit log (refusals, in order):")
    for row in conn.execute(
        "SELECT action, detail FROM audit_log WHERE outcome = 'refused' ORDER BY id"
    ).fetchall():
        print(f"  {row['action']:34} {row['detail'][:70]}")

    after = sorted(i.key for i in jira.search_issues(f"project = {project}", max_results=100))
    print(f"\nProject {project} has {len(after)} issues after.")
    return all(results) and before == after


if __name__ == "__main__":
    sys.exit(main())
