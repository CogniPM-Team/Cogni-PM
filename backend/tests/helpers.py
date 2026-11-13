"""Test doubles shared across the Jira tests: a client served by canned HTTP
responses (httpx.MockTransport), so no test needs a network or real credentials."""

from __future__ import annotations

import httpx

from cognipm.gateway.jira import JiraClient, JiraConfig

CONFIG = JiraConfig(
    base_url="https://example.atlassian.net",
    email="tester@example.com",
    api_token="secret-token",
    project_key="TEST",
    story_points_field="customfield_10016",
)

# What GET /project/TEST returns for its issue types (ids differ per Jira site).
ISSUE_TYPES = [
    {"id": "10001", "name": "Story", "subtask": False},
    {"id": "10002", "name": "Task", "subtask": False},
    {"id": "10003", "name": "Subtask", "subtask": True},
]


def make_client(handler) -> tuple[JiraClient, list[httpx.Request]]:
    """A JiraClient whose HTTP layer is `handler(request) -> httpx.Response`;
    also returns every request it received."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return JiraClient(CONFIG, transport=httpx.MockTransport(record)), seen


def raw_issue(key="TEST-1", *, points=3.0, status_category="new", **extra) -> dict:
    fields = {
        "summary": f"Summary of {key}",
        "status": {"name": "To Do", "statusCategory": {"key": status_category}},
        "issuetype": {"name": "Story"},
        "customfield_10016": points,
        "duedate": "2026-12-01",
        "labels": ["backend"],
    }
    fields.update(extra)
    return {"key": key, "fields": fields}
