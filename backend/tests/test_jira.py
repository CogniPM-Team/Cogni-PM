"""The Jira client, exercised against canned HTTP responses (httpx.MockTransport).
No network and no real credentials: the suite must pass on a fresh checkout and in CI."""

from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest

from cognipm.gateway.jira import (
    JiraClient,
    JiraConfig,
    JiraConfigError,
    _adf_to_text,
    _normalize_list,
    text_to_adf,
)

CONFIG = JiraConfig(
    base_url="https://example.atlassian.net",
    email="tester@example.com",
    api_token="secret-token",
    project_key="TEST",
    story_points_field="customfield_10016",
)


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


# ---------- configuration ----------


def test_config_from_env_strips_the_trailing_slash(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net/")
    monkeypatch.setenv("JIRA_EMAIL", "a@b.c")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "MCP")
    monkeypatch.delenv("JIRA_STORY_POINTS_FIELD", raising=False)

    config = JiraConfig.from_env()

    assert config.base_url == "https://example.atlassian.net"
    assert config.story_points_field == ""  # optional: discovered once, then stored in .env


def test_config_from_env_names_every_missing_variable(monkeypatch):
    for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JIRA_EMAIL", "a@b.c")

    with pytest.raises(JiraConfigError) as exc_info:
        JiraConfig.from_env()

    message = str(exc_info.value)
    assert "JIRA_BASE_URL" in message and "JIRA_API_TOKEN" in message and "JIRA_PROJECT_KEY" in message
    assert "JIRA_EMAIL" not in message


# ---------- requests ----------


def test_every_request_uses_basic_auth_with_email_and_token():
    client, seen = make_client(lambda r: httpx.Response(200, json={"accountId": "1"}))

    client.myself()

    expected = base64.b64encode(b"tester@example.com:secret-token").decode()
    assert seen[0].headers["authorization"] == f"Basic {expected}"
    assert seen[0].url.path == "/rest/api/3/myself"


def test_get_project_defaults_to_the_configured_project():
    client, seen = make_client(lambda r: httpx.Response(200, json={"key": "TEST"}))

    client.get_project()
    client.get_project("OTHER")

    assert [r.url.path for r in seen] == ["/rest/api/3/project/TEST", "/rest/api/3/project/OTHER"]


def test_search_issues_posts_jql_to_the_current_search_endpoint_and_parses_issues():
    client, seen = make_client(
        lambda r: httpx.Response(
            200, json={"issues": [raw_issue("TEST-1"), raw_issue("TEST-2", points=None)]}
        )
    )

    issues = client.search_issues("project = TEST", max_results=10)

    request = seen[0]
    assert (request.method, request.url.path) == ("POST", "/rest/api/3/search/jql")
    body = json.loads(request.content)
    assert body["jql"] == "project = TEST" and body["maxResults"] == 10
    assert "customfield_10016" in body["fields"]  # story points are a custom field, never hardcoded
    assert [(i.key, i.story_points, i.status, i.issue_type) for i in issues] == [
        ("TEST-1", 3.0, "To Do", "Story"),
        ("TEST-2", None, "To Do", "Story"),
    ]
    assert issues[0].labels == ["backend"] and issues[0].due_date == "2026-12-01"
    assert issues[0].description is None  # descriptions are only read by get_issue


def test_get_issue_reads_the_description_as_plain_text():
    adf = text_to_adf("First line\nSecond line")
    client, seen = make_client(lambda r: httpx.Response(200, json=raw_issue("TEST-9", description=adf)))

    issue = client.get_issue("TEST-9")

    assert (seen[0].method, seen[0].url.path) == ("GET", "/rest/api/3/issue/TEST-9")
    assert "description" in seen[0].url.params["fields"]
    assert issue.description == "First line\nSecond line\n"


def test_search_for_analytics_adds_status_category_and_dates():
    row = raw_issue(
        "TEST-3",
        status_category="done",
        resolutiondate="2026-10-01T00:00:00.000+0000",
        created="2026-09-01T00:00:00.000+0000",
    )
    client, _ = make_client(lambda r: httpx.Response(200, json={"issues": [row]}))

    rows = client.search_issues_for_analytics("project = TEST")

    assert rows[0]["status_category"] == "done"
    assert rows[0]["resolved_at"] == "2026-10-01T00:00:00.000+0000"
    assert rows[0]["created"] == "2026-09-01T00:00:00.000+0000"
    assert rows[0]["story_points"] == 3.0


def test_update_issue_fields_puts_only_the_given_fields():
    client, seen = make_client(lambda r: httpx.Response(204))

    client.update_issue_fields("TEST-1", {"customfield_10016": 5.0})

    assert (seen[0].method, seen[0].url.path) == ("PUT", "/rest/api/3/issue/TEST-1")
    assert json.loads(seen[0].content) == {"fields": {"customfield_10016": 5.0}}


def test_discover_field_matches_names_case_insensitively():
    fields = [
        {"id": "customfield_10016", "name": "Story point estimate"},
        {"id": "customfield_10020", "name": "Sprint"},
        {"id": "customfield_10030", "name": "Story Points (legacy)"},
    ]
    client, _ = make_client(lambda r: httpx.Response(200, json=fields))

    found = client.discover_field("story point")

    assert [f["id"] for f in found] == ["customfield_10016", "customfield_10030"]


def test_http_errors_are_logged_to_stderr_and_raised(caplog):
    client, _ = make_client(lambda r: httpx.Response(401, text="bad credentials"))

    with caplog.at_level(logging.ERROR, logger="cognipm.gateway.jira"), pytest.raises(httpx.HTTPStatusError):
        client.myself()

    assert "401" in caplog.text and "bad credentials" in caplog.text


# ---------- payload helpers ----------


def test_normalize_list_accepts_each_shape_jira_uses():
    assert _normalize_list([1, 2]) == [1, 2]  # bare array (/field)
    assert _normalize_list({"issues": [1]}) == [1]  # /search/jql
    assert _normalize_list({"values": [3]}) == [3]  # paginated endpoints
    with pytest.raises(ValueError, match="Unrecognised"):
        _normalize_list({"something": "else"})


def test_adf_round_trip_and_blank_lines():
    adf = text_to_adf("one\n\nthree")

    assert [len(p["content"]) for p in adf["content"]] == [1, 0, 1]  # a blank line is an empty paragraph
    assert _adf_to_text(adf) == "one\n\nthree\n"
    assert _adf_to_text(None) == "" and _adf_to_text("plain") == "plain"
