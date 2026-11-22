"""Live proof that the Jira write path works, before the gateway exists.

Creates ONE clearly-labelled sandbox Story and ONE Sub-task under it in the project
from your .env, reads them back, adds a comment, then deletes both and checks they
are gone. It prints before and after so you can see nothing is left behind.

Safety:
  - It refuses to run without --confirm, because it WRITES to the real Jira site.
  - Everything it creates carries the label `cognipm-sandbox`, and the client will
    only delete issues with that label, so it cannot remove real work.
  - Cleanup deletes the issues. If the API user lacks the Delete Issues permission
    (403), it closes them instead, so they stay in Jira as Done. If that also fails
    it prints the keys to remove by hand.
  - Creating and deleting consumes two issue numbers in your project (e.g. MCP-11,
    MCP-12 will be skipped afterwards). Jira does not reuse them.

Run from backend/:

    python scripts/verify_write.py --confirm
"""

from __future__ import annotations

import sys
from datetime import datetime

import httpx

from cognipm.gateway.jira import SANDBOX_LABEL, JiraClient, JiraConfigError, describe_error, draft_to_adf


def sandbox_issues(client: JiraClient) -> list:
    jql = (
        f'project = {client.config.project_key} AND labels = "{SANDBOX_LABEL}" '
        "AND statusCategory != Done ORDER BY created ASC"
    )
    return client.search_issues(jql, max_results=50)


def main() -> int:
    if "--confirm" not in sys.argv[1:]:
        print(__doc__)
        print("Not run: pass --confirm to proceed.")
        return 2

    try:
        client = JiraClient()
    except JiraConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created: list[str] = []
    ok = False

    with client:
        project = client.config.project_key
        print(f"Project: {project}")
        print(f"Open sandbox issues before: {[i.key for i in sandbox_issues(client)] or 'none'}")

        subtask_type = next((t for t in client.list_issue_types() if t.subtask), None)
        if subtask_type is None:
            print("This project has no sub-task issue type, so P2 (task breakdown) cannot work here.")
            return 1
        print(f"Using issue types: Story, {subtask_type.name}")

        try:
            story = client.create_issue(
                "Story",
                f"[CogniPM sandbox] verify_write story {stamp}",
                description=draft_to_adf(
                    "Created by scripts/verify_write.py to prove the write path. Safe to delete.",
                    ["Created through the Jira client", "Removed again by the same script"],
                ),
                labels=[SANDBOX_LABEL],
            )
            created.append(story.key)
            print(f"Created story    {story.key}  {story.url}")

            subtask = client.create_issue(
                subtask_type.name,
                f"[CogniPM sandbox] verify_write sub-task {stamp}",
                parent_key=story.key,
                labels=[SANDBOX_LABEL],
            )
            created.append(subtask.key)
            print(f"Created sub-task {subtask.key}  (parent {story.key})")

            client.add_comment(story.key, "Provenance comment from verify_write.py.")
            print(f"Commented on     {story.key}")

            back_story = client.get_issue(story.key)
            back_subtask = client.get_issue(subtask.key)
            assert back_story.issue_type == "Story" and SANDBOX_LABEL in back_story.labels
            assert back_story.description and "Acceptance criteria" in back_story.description
            assert back_subtask.issue_type == subtask_type.name
            print(
                f"Read back        {back_story.key} [{back_story.issue_type}], {back_subtask.key} [{back_subtask.issue_type}]"
            )
            print(f"Description reads as:\n{back_story.description}")
            ok = True
        except httpx.HTTPStatusError as exc:
            print(f"Jira refused: {describe_error(exc)}")
        except AssertionError:
            print("Read-back did not match what was created.")
        finally:
            if created and not cleanup(client, created):
                ok = False

        # JQL search is eventually consistent, so this may still list issues closed a moment ago.
        print(
            f"Open sandbox issues after (search may lag): {[i.key for i in sandbox_issues(client)] or 'none'}"
        )

    print(
        "\nPASS: the write path works and left nothing open behind." if ok else "\nFAIL: see messages above."
    )
    return 0 if ok else 1


def cleanup(client: JiraClient, created: list[str]) -> bool:
    """Delete the story (and its sub-task). If Jira refuses (the API user may lack the
    Delete Issues permission), close every created issue instead, sub-task first."""
    try:
        client.delete_issue(created[0])
        print(f"Deleted          {created[0]} (and its sub-task)")
        return True
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            print(
                f"CLEANUP FAILED for {created[0]}: {describe_error(exc)}. Remove {created} by hand in Jira."
            )
            return False
        print("Delete not permitted for this API user; closing the sandbox issues instead.")
    ok = True
    for key in reversed(created):
        try:
            via = client.close_issue(key)
            status = client.get_issue(key).status  # read back: JQL search lags right after a write
            print(f"Closed           {key} via '{via}', status now {status}")
            ok = ok and status == "Done"
        except Exception as exc:  # noqa: BLE001 - report, then tell the human what to do
            print(f"CLEANUP FAILED for {key}: {exc}. Close or delete it by hand in Jira.")
            ok = False
    return ok


if __name__ == "__main__":
    sys.exit(main())
