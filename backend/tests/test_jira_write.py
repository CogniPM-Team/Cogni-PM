"""The Jira client's write path (creating issues for P1/P2) and the key validation
that guards it. The refusal tests matter most: each asserts that nothing reached
Jira, by checking the requests the mock transport saw."""

from __future__ import annotations

import json

import httpx
import pytest

from cognipm.gateway.jira import (
    SANDBOX_LABEL,
    InvalidIssueKey,
    NoDoneTransition,
    SandboxOnlyError,
    describe_error,
    draft_to_adf,
    key_in_jql,
    validate_issue_key,
)
from tests.helpers import ISSUE_TYPES, make_client, raw_issue


def jira_site(*, created_key="TEST-20", labels=("backend",)):
    """Canned answers for the endpoints the write path touches."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/rest/api/3/project/TEST":
            return httpx.Response(200, json={"key": "TEST", "issueTypes": ISSUE_TYPES})
        if request.method == "POST" and path == "/rest/api/3/issue":
            return httpx.Response(201, json={"id": "10099", "key": created_key})
        if request.method == "GET" and path.startswith("/rest/api/3/issue/"):
            return httpx.Response(200, json=raw_issue(path.rsplit("/", 1)[-1], labels=list(labels)))
        if request.method in ("POST", "DELETE") and path.startswith("/rest/api/3/issue/"):
            return httpx.Response(201 if request.method == "POST" else 204)
        return httpx.Response(404, json={"errorMessages": [f"unexpected {request.method} {path}"]})

    return handler


def methods(seen) -> list[str]:
    return [r.method for r in seen]


# ---------- key validation: keys come from model output ----------


@pytest.mark.parametrize("key", ["MCP-1", "AB-123", "PROJ_X-9"])
def test_valid_keys_pass_through_unchanged(key):
    assert validate_issue_key(key) == key


@pytest.mark.parametrize(
    "key",
    [
        "",
        "mcp-1",
        "MCP-",
        "MCP-1)",
        "MCP-1) OR project = SECRET",  # JQL injection
        "MCP-1\n",  # `$` would accept a trailing newline; fullmatch must not
        " MCP-1",
        "../admin",  # path traversal
        "MCP-1/comment",
        "MCP-1;DROP",
        None,
    ],
)
def test_malformed_keys_are_refused(key):
    with pytest.raises(InvalidIssueKey):
        validate_issue_key(key)


def test_key_in_jql_only_ever_contains_validated_keys():
    assert key_in_jql(["TEST-1", "TEST-2"]) == "key in (TEST-1, TEST-2)"
    with pytest.raises(InvalidIssueKey):
        key_in_jql(["TEST-1", "TEST-2) OR project = X"])
    with pytest.raises(ValueError, match="at least one"):
        key_in_jql([])


def test_every_method_that_puts_a_key_in_a_url_refuses_a_bad_key_before_any_request():
    client, seen = make_client(jira_site())
    bad = "TEST-1/../../admin"

    for call in (
        lambda: client.get_issue(bad),
        lambda: client.update_issue_fields(bad, {"summary": "x"}),
        lambda: client.add_comment(bad, "hello"),
        lambda: client.delete_issue(bad),
        lambda: client.close_issue(bad),
        lambda: client.get_project("test"),
        lambda: client.create_issue("Subtask", "Child", parent_key=bad),
    ):
        with pytest.raises(InvalidIssueKey):
            call()

    assert seen == []  # nothing reached Jira


# ---------- issue types ----------


def test_list_issue_types_reads_ids_names_and_the_subtask_flag():
    client, _ = make_client(jira_site())

    types = client.list_issue_types()

    assert [(t.id, t.name, t.subtask) for t in types] == [
        ("10001", "Story", False),
        ("10002", "Task", False),
        ("10003", "Subtask", True),
    ]


def test_issue_type_is_found_by_name_ignoring_case_and_cached():
    client, seen = make_client(jira_site())

    assert client.issue_type("story").id == "10001"
    assert client.issue_type("SUBTASK").subtask is True
    assert methods(seen) == ["GET"]  # one lookup, however many types are asked for


def test_an_unknown_issue_type_lists_what_is_available():
    client, _ = make_client(jira_site())

    with pytest.raises(ValueError, match="Available: Story, Task, Subtask"):
        client.issue_type("Epic")


# ---------- create_issue ----------


def test_create_issue_posts_the_whole_draft_and_returns_the_key():
    client, seen = make_client(jira_site(created_key="TEST-20"))
    description = draft_to_adf("As a PM I want X.", ["It works", "It is logged"])

    created = client.create_issue("Story", "  Add login  ", description=description, labels=["cognipm"])

    post = next(r for r in seen if r.method == "POST")
    fields = json.loads(post.content)["fields"]
    assert fields["project"] == {"key": "TEST"}
    assert fields["issuetype"] == {"id": "10001"}  # looked up by name, not hardcoded
    assert fields["summary"] == "Add login"  # trimmed
    assert fields["description"] == description
    assert fields["labels"] == ["cognipm"]
    assert "parent" not in fields
    assert (created.key, created.id) == ("TEST-20", "10099")
    assert created.url == "https://example.atlassian.net/browse/TEST-20"


def test_create_subtask_names_its_parent():
    client, seen = make_client(jira_site(created_key="TEST-21"))

    created = client.create_issue("Subtask", "Write the tests", parent_key="TEST-20")

    fields = json.loads(next(r for r in seen if r.method == "POST").content)["fields"]
    assert fields["issuetype"] == {"id": "10003"}
    assert fields["parent"] == {"key": "TEST-20"}
    assert created.key == "TEST-21"


def test_a_subtask_without_a_parent_is_refused_before_any_create_request():
    client, seen = make_client(jira_site())

    with pytest.raises(ValueError, match="needs a parent_key"):
        client.create_issue("Subtask", "Orphan")

    assert "POST" not in methods(seen)


@pytest.mark.parametrize("summary", ["", "   ", "x" * 256])
def test_a_bad_summary_is_refused_before_any_request(summary):
    client, seen = make_client(jira_site())

    with pytest.raises(ValueError):
        client.create_issue("Story", summary)

    assert seen == []


def test_a_jira_rejection_is_raised_not_swallowed_and_explained():
    def reject(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"issueTypes": ISSUE_TYPES})
        return httpx.Response(
            400,
            json={
                "errorMessages": [],
                "errors": {"description": "Operation value must be an Atlassian Document"},
            },
        )

    client, _ = make_client(reject)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.create_issue("Story", "Add login")

    assert describe_error(exc_info.value) == (
        "Jira returned 400: description: Operation value must be an Atlassian Document"
    )


def test_describe_error_copes_with_a_non_json_body():
    response = httpx.Response(502, text="<html>bad gateway</html>", request=httpx.Request("GET", "https://x"))
    error = httpx.HTTPStatusError("boom", request=response.request, response=response)

    assert describe_error(error) == "Jira returned 502"


# ---------- comments ----------


def test_add_comment_sends_the_text_as_adf():
    client, seen = make_client(jira_site())

    client.add_comment("TEST-20", "Approved by a PM.\nSecond line")

    request = seen[0]
    assert (request.method, request.url.path) == ("POST", "/rest/api/3/issue/TEST-20/comment")
    body = json.loads(request.content)["body"]
    assert body["type"] == "doc" and len(body["content"]) == 2
    assert body["content"][0]["content"][0]["text"] == "Approved by a PM."


def test_an_empty_comment_is_refused():
    client, seen = make_client(jira_site())

    with pytest.raises(ValueError, match="needs text"):
        client.add_comment("TEST-20", "  ")

    assert seen == []


# ---------- deletion: sandbox issues only ----------


def test_delete_refuses_an_issue_without_the_sandbox_label_and_never_sends_a_delete():
    client, seen = make_client(jira_site(labels=("backend",)))

    with pytest.raises(SandboxOnlyError, match="not labelled"):
        client.delete_issue("TEST-1")

    assert "DELETE" not in methods(seen)


def test_delete_removes_a_sandbox_issue_with_its_subtasks():
    client, seen = make_client(jira_site(labels=(SANDBOX_LABEL,)))

    client.delete_issue("TEST-20")

    delete = next(r for r in seen if r.method == "DELETE")
    assert delete.url.path == "/rest/api/3/issue/TEST-20"
    assert delete.url.params["deleteSubtasks"] == "true"


# ---------- closing: the fallback when delete is not permitted ----------


def workflow(*, labels, transitions):
    """jira_site plus a transitions endpoint."""
    base = jira_site(labels=labels)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/transitions"):
            if request.method == "GET":
                return httpx.Response(200, json={"transitions": transitions})
            return httpx.Response(204)
        return base(request)

    return handler


TO_DO = {"id": "11", "name": "To Do", "to": {"statusCategory": {"key": "new"}}}
DONE = {"id": "31", "name": "Done", "to": {"statusCategory": {"key": "done"}}}


def test_close_picks_the_transition_that_ends_in_a_done_status_not_one_by_name():
    client, seen = make_client(workflow(labels=(SANDBOX_LABEL,), transitions=[TO_DO, DONE]))

    assert client.close_issue("TEST-20") == "Done"

    post = next(r for r in seen if r.method == "POST")
    assert json.loads(post.content) == {"transition": {"id": "31"}}


def test_close_refuses_an_issue_without_the_sandbox_label_and_sends_no_transition():
    client, seen = make_client(workflow(labels=("backend",), transitions=[DONE]))

    with pytest.raises(SandboxOnlyError, match="refusing to close"):
        client.close_issue("TEST-1")

    assert "POST" not in methods(seen)


def test_close_says_so_when_the_workflow_offers_no_done_transition():
    client, seen = make_client(workflow(labels=(SANDBOX_LABEL,), transitions=[TO_DO]))

    with pytest.raises(NoDoneTransition, match="no transition to a done status"):
        client.close_issue("TEST-20")

    assert "POST" not in methods(seen)


# ---------- ADF for a drafted story ----------


def test_draft_to_adf_puts_acceptance_criteria_under_a_heading_as_a_list():
    adf = draft_to_adf("Description line", ["First", "  Second  ", ""])

    kinds = [node["type"] for node in adf["content"]]
    assert kinds == ["paragraph", "heading", "bulletList"]
    items = adf["content"][2]["content"]
    assert [i["content"][0]["content"][0]["text"] for i in items] == [
        "First",
        "Second",
    ]  # trimmed, blank dropped
    assert adf["content"][1]["content"][0]["text"] == "Acceptance criteria"


def test_draft_to_adf_omits_the_heading_when_there_are_no_criteria():
    assert [n["type"] for n in draft_to_adf("Just a description")["content"]] == ["paragraph"]
    assert [n["type"] for n in draft_to_adf("", ["Only criteria"])["content"]] == ["heading", "bulletList"]


# ---------- what Jira requires to create an issue ----------


def createmeta_site(fields):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/api/3/project/TEST":
            return httpx.Response(200, json={"key": "TEST", "issueTypes": ISSUE_TYPES})
        if "/createmeta/" in request.url.path:
            return httpx.Response(200, json={"fields": fields})
        return httpx.Response(404, json={"errorMessages": ["unexpected"]})

    return handler


def test_required_fields_lists_only_what_jira_insists_on_and_gives_no_default_for():
    client, seen = make_client(
        createmeta_site(
            [
                {"key": "summary", "name": "Summary", "required": True, "hasDefaultValue": False},
                {"key": "priority", "name": "Priority", "required": True, "hasDefaultValue": True},
                {"key": "customfield_10042", "name": "Team", "required": True, "hasDefaultValue": False},
                {"key": "labels", "name": "Labels", "required": False, "hasDefaultValue": False},
            ]
        )
    )

    assert client.required_fields("Story") == [
        {"key": "summary", "name": "Summary"},
        {"key": "customfield_10042", "name": "Team"},
    ]
    client.required_fields("story")  # asked again: answered from the cache
    assert [r.url.path.rsplit("/", 1)[-1] for r in seen].count("10001") == 1
