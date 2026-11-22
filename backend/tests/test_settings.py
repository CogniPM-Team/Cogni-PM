"""The Settings API: what it shows, what it must never show, and the two connection tests including how they
fail. Uses the fake Jira and a scripted model, so nothing here touches the network or costs money."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from cognipm.api.deps import get_jira, get_model_client
from cognipm.api.main import app
from cognipm.gateway.guardrails import GUARDRAILS
from tests.fake_gemini import FakeGemini, raw_text_reply
from tests.helpers import CONFIG, make_client


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-key")
    jira, _ = make_client(lambda request: httpx.Response(404))
    gemini = FakeGemini([])
    app.dependency_overrides[get_jira] = lambda: jira
    app.dependency_overrides[get_model_client] = lambda: gemini
    with TestClient(app) as c:
        c.gemini = gemini
        c.set_jira = lambda handler: app.dependency_overrides.__setitem__(
            get_jira, lambda: make_client(handler)[0]
        )
        yield c
    app.dependency_overrides.clear()


def test_settings_show_the_setup_and_never_a_secret(client):
    body = client.get("/api/settings").json()
    text = json.dumps(body)

    assert body["jira_host"] == "example.atlassian.net" and body["jira_project"] == "TEST"
    assert body["ai_key_set"] is True and body["story_points_field_set"] is True
    assert body["max_items_per_run"] == 20
    for secret in ("gemini-secret-key", CONFIG.api_token, CONFIG.email):
        assert secret not in text


def test_settings_say_when_no_model_key_is_set(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")

    assert client.get("/api/settings").json()["ai_key_set"] is False


def test_every_guardrail_is_listed_with_a_sentence(client):
    rules = client.get("/api/settings").json()["guardrails"]

    assert len(rules) == len(GUARDRAILS) == 9
    assert "max_items_per_run" in [r["name"] for r in rules]  # the id the activity log shows on a refusal
    assert all(r["description"].strip() for r in rules)
    # a rule added to the chain without a sentence for this page would be a KeyError, not a silent gap
    assert {r["name"] for r in rules} == {g.__name__.removesuffix("_rule") for g in GUARDRAILS}


def test_it_says_what_is_sent_to_the_model(client):
    sent = " ".join(client.get("/api/settings").json()["sent_to_model"])

    assert "never sent" in sent and "token" in sent


def test_jira_test_reports_who_is_signed_in_and_not_their_email(client):
    result = client.post("/api/settings/test-jira").json()

    assert result["ok"] is False  # the default fake answers 404 to everything

    def site(request):
        if request.url.path == "/rest/api/3/myself":
            return httpx.Response(
                200, json={"displayName": "Ada Lovelace", "emailAddress": "ada@example.com"}
            )
        return httpx.Response(200, json={"key": "TEST", "issueTypes": []})

    client.set_jira(site)
    result = client.post("/api/settings/test-jira").json()
    assert result == {
        "ok": True,
        "detail": "Signed in as Ada Lovelace. Project TEST is reachable.",
        "problem": None,
    }
    assert "ada@example.com" not in json.dumps(result)


def test_jira_test_explains_a_rejected_login(client):
    client.set_jira(lambda request: httpx.Response(401, json={}))

    result = client.post("/api/settings/test-jira").json()

    assert result["ok"] is False and "JIRA_API_TOKEN" in result["problem"]


def test_jira_test_explains_a_project_the_account_cannot_see(client):
    def site(request):
        if request.url.path == "/rest/api/3/myself":
            return httpx.Response(200, json={"displayName": "Ada"})
        return httpx.Response(404, json={})

    client.set_jira(site)

    result = client.post("/api/settings/test-jira").json()

    assert (
        result["ok"] is False
        and "Signed in as Ada" in result["problem"]
        and "JIRA_PROJECT_KEY" in result["problem"]
    )


def test_jira_test_explains_an_unreachable_site(client):
    def down(request):
        raise httpx.ConnectError("no route", request=request)

    client.set_jira(down)

    result = client.post("/api/settings/test-jira").json()

    assert result["ok"] is False and "JIRA_BASE_URL" in result["problem"]


def test_model_test_succeeds_with_one_tiny_request(client):
    client.gemini.models.replies.append(raw_text_reply("OK"))

    result = client.post("/api/settings/test-model").json()

    assert result["ok"] is True and "answered" in result["detail"]
    [call] = client.gemini.calls
    assert call["config"].max_output_tokens <= 16  # the point is that it costs almost nothing


def test_model_test_says_so_when_no_key_is_set(client):
    app.dependency_overrides[get_model_client] = lambda: None

    result = client.post("/api/settings/test-model").json()

    assert result["ok"] is False and "GEMINI_API_KEY" in result["problem"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (genai_errors.ClientError(429, {"error": {"message": "quota"}}), "out of credit"),
        (genai_errors.ClientError(402, {"error": {"message": "credits depleted"}}), "out of credit"),
        (genai_errors.ClientError(400, {"error": {"message": "API key not valid"}}), "rejected the key"),
        (genai_errors.ClientError(403, {"error": {"message": "denied"}}), "rejected the key"),
        (genai_errors.ClientError(404, {"error": {"message": "no such model"}}), "ORCHESTRATOR_MODEL"),
        (genai_errors.ServerError(503, {"error": {"message": "overloaded"}}), "having trouble"),
    ],
)
def test_model_test_turns_each_failure_into_a_sentence_that_says_what_to_check(client, error, expected):
    def fail(contents):
        raise error

    client.gemini.models.replies.append(fail)

    result = client.post("/api/settings/test-model").json()

    assert result["ok"] is False and expected in result["problem"]
    assert "gemini-secret-key" not in json.dumps(result)
