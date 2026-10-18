"""Smoke test: prove the Jira client can authenticate against your real site.

Run from backend/ after creating .env at the repo root (see .env.example):

    pip install -e ".[dev]"
    python scripts/check_connection.py

It only reads - nothing is changed in Jira. Use it to confirm credentials, find your
project, and discover the story-points custom field id (put it in .env as
JIRA_STORY_POINTS_FIELD).
"""

from __future__ import annotations

import sys

from cognipm.gateway.jira import JiraClient, JiraConfigError


def main() -> int:
    try:
        client = JiraClient()
    except JiraConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    with client:
        me = client.myself()
        print(f"Authenticated as: {me['displayName']} <{me['emailAddress']}>")

        project = client.get_project()
        print(
            f"\nProject: {project['key']} - {project['name']} [{project['projectTypeKey']}, {project['style']}]"
        )

        print("\nStory point field(s) found via /rest/api/3/field:")
        for field in client.discover_field("story point"):
            marker = " <- configured in .env" if field["id"] == client.config.story_points_field else ""
            print(f"  {field['id']}  |  {field['name']}{marker}")

        issues = client.search_issues(
            f"project = {client.config.project_key} ORDER BY created DESC", max_results=5
        )
        print(f"\nMost recent issues in {client.config.project_key}:")
        if not issues:
            print("  (none yet)")
        for issue in issues:
            print(f"  {issue.key}  {issue.summary}  [{issue.status}]  points={issue.story_points}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
