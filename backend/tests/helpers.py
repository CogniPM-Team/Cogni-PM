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


def issue_creating_site(
    *,
    fail_on_summary: str | None = None,
    first_number: int = 100,
    open_issues: dict[str, str] | None = None,
    existing: dict[str, dict] | None = None,
    required: list[dict] | None = None,
    stamped: dict[str, str] | None = None,
):
    """A fake Jira, enough for proposing and creating drafts:

    - GET /project/TEST lists the issue types; GET .../createmeta lists the required fields
      (summary, issuetype, project, plus `required` extras such as {"key": "customfield_9", "name": "Team"}).
    - POST /search/jql returns `open_issues` ({key: summary}) - what the duplicate check compares against.
    - GET /issue/<key> answers for the keys in `existing` ({key: raw-issue overrides}; TEST-1 by default).
    - A search for a draft's stamp label (`cognipm-draft-<id>`) finds the issue in `stamped` ({draft id: key}),
      standing for an issue an earlier, crashed attempt already created.
    - POST /issue/<key>/comment is accepted and kept in `handler.comments`.
    - Each POST /issue gets the next key (TEST-100, TEST-101, ...). A summary equal to `fail_on_summary`
      is refused with a 400.

    Returns (handler, created) where `created` collects the POSTed issue fields."""
    created: list[dict] = []
    comments: list[tuple[str, str]] = []
    known = {"TEST-1": {}} if existing is None else existing
    meta = [
        {"key": k, "name": k.title(), "required": True, "hasDefaultValue": False}
        for k in ("summary", "issuetype", "project")
    ] + [{**f, "required": True, "hasDefaultValue": False} for f in (required or [])]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/rest/api/3/project/TEST":
            return httpx.Response(200, json={"key": "TEST", "issueTypes": ISSUE_TYPES})
        if request.method == "GET" and "/createmeta/" in path:
            return httpx.Response(200, json={"fields": meta})
        if request.method == "POST" and path == "/rest/api/3/search/jql":
            jql = json.loads(request.content)["jql"]
            if 'labels = "cognipm-draft-' in jql:
                draft_id = jql.split('labels = "cognipm-draft-')[1].split('"')[0]
                key = (stamped or {}).get(draft_id)
                found = [raw_issue(key, labels=[f"cognipm-draft-{draft_id}"])] if key else []
                return httpx.Response(200, json={"issues": found})
            issues = [raw_issue(k, summary=v) for k, v in (open_issues or {}).items()]
            return httpx.Response(200, json={"issues": issues})
        if request.method == "POST" and path.endswith("/comment"):
            body = json.loads(request.content)["body"]
            comments.append((path.split("/")[-2], body["content"][0]["content"][0]["text"]))
            return httpx.Response(201, json={"id": "1"})
        if request.method == "GET" and path.startswith("/rest/api/3/issue/"):
            key = path.rsplit("/", 1)[-1]
            if key in known:
                return httpx.Response(200, json=raw_issue(key, **known[key]))
            return httpx.Response(404, json={"errorMessages": ["Issue does not exist"]})
        if request.method == "POST" and path == "/rest/api/3/issue":
            fields = json.loads(request.content)["fields"]
            if fields["summary"] == fail_on_summary:
                return httpx.Response(
                    400, json={"errorMessages": [], "errors": {"summary": "refused by the fake"}}
                )
            created.append(fields)
            number = first_number + len(created) - 1
            return httpx.Response(201, json={"id": str(10000 + number), "key": f"TEST-{number}"})
        return httpx.Response(404, json={"errorMessages": [f"unexpected {request.method} {path}"]})

    handler.comments = comments
    return handler, created


def fake_jira(**site_options):
    """(JiraClient, requests seen, fields of issues created) over issue_creating_site."""
    handler, created = issue_creating_site(**site_options)
    client, seen = make_client(handler)
    client.comments = handler.comments  # what was commented on which issue, for tests that care
    return client, seen, created


def creates(seen) -> list[httpx.Request]:
    """The requests that tried to create an issue - the only writes there are."""
    return [r for r in seen if r.method == "POST" and r.url.path == "/rest/api/3/issue"]


posts = creates  # the name the older tests use
