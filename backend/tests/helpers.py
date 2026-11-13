"""Test doubles shared across the Jira tests: a client served by canned HTTP
responses (httpx.MockTransport), so no test needs a network or real credentials."""

from __future__ import annotations

import json

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


def issue_creating_site(*, fail_on_summary: str | None = None, first_number: int = 100):
    """A fake Jira that accepts issue creation: GET /project/TEST lists the issue types and each
    POST /issue gets the next key (TEST-100, TEST-101, ...). A summary equal to `fail_on_summary`
    is refused with a 400. Returns (handler, created) where `created` collects the POSTed fields."""
    created: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/rest/api/3/project/TEST":
            return httpx.Response(200, json={"key": "TEST", "issueTypes": ISSUE_TYPES})
        if request.method == "POST" and request.url.path == "/rest/api/3/issue":
            fields = json.loads(request.content)["fields"]
            if fields["summary"] == fail_on_summary:
                return httpx.Response(
                    400, json={"errorMessages": [], "errors": {"summary": "refused by the fake"}}
                )
            created.append(fields)
            number = first_number + len(created) - 1
            return httpx.Response(201, json={"id": str(10000 + number), "key": f"TEST-{number}"})
        return httpx.Response(
            404, json={"errorMessages": [f"unexpected {request.method} {request.url.path}"]}
        )

    return handler, created


def fake_jira(**site_options):
    """(JiraClient, requests seen, fields of issues created) over issue_creating_site."""
    handler, created = issue_creating_site(**site_options)
    client, seen = make_client(handler)
    return client, seen, created


def posts(seen) -> list[httpx.Request]:
    """The requests that tried to create an issue."""
    return [r for r in seen if r.method == "POST"]
