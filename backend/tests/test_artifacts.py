"""The Library API: the issues CogniPM created, joined with what Jira says about them now. The cases that matter
are the awkward ones: Jira down, an issue deleted in Jira, and a list too long for one search."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from cognipm.api.deps import get_jira
from cognipm.api.main import app
from cognipm.api.routes import artifacts as artifacts_route
from tests.helpers import make_client
from tests.test_api import build_api, draft_ids, start_p1


@pytest.fixture
def api(conn):
    # TEST-100 (the first issue created) is listed by Jira; TEST-101 is not, as if it had been deleted there
    # (its title must differ from the drafts', or the duplicate rule would refuse the draft that becomes TEST-100)
    api = build_api(conn, jira_options={"open_issues": {"TEST-100": "Listed by Jira"}})
    with TestClient(app) as client:
        api.client = client
        yield api
    app.dependency_overrides.clear()


def approve(api, how_many=2):
    detail = start_p1(api)
    run_id = detail["run"]["id"]
    response = api.client.post(
        f"/api/runs/{run_id}/approve", json={"change_ids": draft_ids(detail)[:how_many]}
    )
    assert response.status_code == 200, response.text
    return run_id


def library(api):
    response = api.client.get("/api/artifacts")
    assert response.status_code == 200, response.text
    return response.json()


def test_nothing_created_means_an_empty_library(api):
    start_p1(api)  # drafts exist, but none was approved

    assert library(api) == {"items": [], "jira_reachable": True}


def test_created_issues_are_listed_with_their_live_status_and_who_approved_them(api):
    run_id = approve(api)

    body = library(api)

    assert body["jira_reachable"] is True
    by_key = {i["issue_key"]: i for i in body["items"]}
    assert set(by_key) == {"TEST-100", "TEST-101"}
    first = by_key["TEST-100"]
    assert (first["jira_state"], first["jira_status"]) == ("found", "To Do")
    assert first["title"] == "Password reset" and first["run_id"] == run_id
    assert first["approved_by"] == "human:reviewer" and first["created_at"]
    assert first["url"] == "https://example.atlassian.net/browse/TEST-100"


def test_an_issue_deleted_in_jira_is_missing_not_silently_dropped(api):
    approve(api)

    gone = next(i for i in library(api)["items"] if i["issue_key"] == "TEST-101")

    assert (gone["jira_state"], gone["jira_status"]) == ("missing", None)
    assert gone["title"] == "Login audit"  # our own record of it is still there


def test_the_list_still_loads_when_jira_is_down_with_every_status_unknown(api):
    approve(api)
    broken, _ = make_client(lambda request: httpx.Response(503, json={}))
    app.dependency_overrides[get_jira] = lambda: broken

    body = library(api)

    assert body["jira_reachable"] is False
    assert {i["issue_key"] for i in body["items"]} == {"TEST-100", "TEST-101"}
    assert {i["jira_state"] for i in body["items"]} == {"unknown"}
    assert {i["jira_status"] for i in body["items"]} == {None}


def test_a_search_too_long_for_one_page_never_claims_an_issue_is_missing(api, monkeypatch):
    approve(api)
    monkeypatch.setattr(
        artifacts_route, "JIRA_PAGE", 1
    )  # Jira returns one issue: we cannot tell about the rest

    states = {i["issue_key"]: i["jira_state"] for i in library(api)["items"]}

    assert states == {"TEST-100": "found", "TEST-101": "unknown"}


def test_an_edited_title_is_the_title_listed(api):
    detail = start_p1(api)
    first = draft_ids(detail)[0]
    api.client.patch(f"/api/changes/{first}", json={"summary": "Reset password by email"})
    api.client.post(f"/api/runs/{detail['run']['id']}/approve", json={"change_ids": [first]})

    assert [i["title"] for i in library(api)["items"]] == ["Reset password by email"]


def test_rejected_drafts_are_not_in_the_library(api):
    detail = start_p1(api)
    api.client.post(f"/api/runs/{detail['run']['id']}/reject", json={"comment": "not now"})

    assert library(api)["items"] == []
