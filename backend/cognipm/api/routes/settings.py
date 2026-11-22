"""The Settings page: how this install is set up, and two buttons that check the connections.

Read-only. Nothing here changes configuration (that stays in `.env`), and nothing returns a secret: the
settings say whether a key is set, never what it is, and the Jira check reports a display name, never an
email address.
"""

from __future__ import annotations

import asyncio
import os
from importlib.metadata import PackageNotFoundError, version

import httpx
from fastapi import APIRouter, Depends
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from cognipm.api.deps import get_jira, get_model_client
from cognipm.api.schemas import ConnectionTestOut, GuardrailOut, SettingsOut
from cognipm.config import max_items_per_run, orchestrator_model
from cognipm.gateway.guardrails import GUARDRAILS
from cognipm.gateway.jira import JiraClient, describe_error

router = APIRouter(tags=["settings"])

MODEL_TEST_SECONDS = 20

# What leaves this machine for the AI model, in the words a participant should read.
SENT_TO_MODEL = [
    "Draft a backlog: the text you paste or load, and any instructions you add.",
    "Break down a story: that story's title and description, and any instructions you add.",
    "Co-Pilot: your questions, and the Jira issues it reads to answer them.",
    "Your Jira API token and email address are never sent to the model.",
]


# One plain sentence per rule, for the page. The docstrings in gateway/guardrails.py are written for developers;
# a test fails if a rule is added there without a sentence here.
GUARDRAIL_HELP = {
    "required_fields": "Every draft needs a title, and every story needs at least one acceptance criterion.",
    "create_only": "Agents can only create new issues. They can never edit, move, link or delete an existing one.",
    "external_is_gated": "Anything that affects people outside the project always needs a person to approve it.",
    "max_items_per_run": "One run can draft or create only a limited number of issues, so a bad run cannot flood the backlog.",
    "no_milestone_date_change": "No agent can set a due date on a milestone (an Epic, or an issue labelled milestone).",
    "in_project_scope": "Everything an agent creates stays inside the configured Jira project.",
    "valid_parent": "A sub-task must sit under a real story or task. Nothing else can have a parent.",
    "no_duplicate": "A draft is refused if an open issue, or another draft in the same run, already has its title.",
    "jira_required_fields": "A draft is refused up front if Jira would demand a field the agent cannot fill in.",
}


def _version() -> str:
    try:
        return version("cognipm-backend")
    except PackageNotFoundError:  # running from a checkout that was never installed
        return "dev"


@router.get("/settings", response_model=SettingsOut)
def read_settings(jira: JiraClient = Depends(get_jira)) -> SettingsOut:
    base = jira.config.base_url
    return SettingsOut(
        version=_version(),
        jira_host=base.removeprefix("https://").removeprefix("http://"),
        jira_project=jira.config.project_key,
        story_points_field_set=bool(jira.config.story_points_field),
        ai_model=orchestrator_model(),
        ai_key_set=bool(os.environ.get("GEMINI_API_KEY")),
        max_items_per_run=max_items_per_run(),
        guardrails=[
            GuardrailOut(name=name, description=GUARDRAIL_HELP[name])
            for name in (g.__name__.removesuffix("_rule") for g in GUARDRAILS)
        ],
        sent_to_model=SENT_TO_MODEL,
    )


@router.post("/settings/test-jira", response_model=ConnectionTestOut)
def test_jira(jira: JiraClient = Depends(get_jira)) -> ConnectionTestOut:
    """Ask Jira who we are signed in as, then whether the project is reachable. Reads only."""
    project = jira.config.project_key
    try:
        who = jira.myself().get("displayName") or "an unnamed account"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            return ConnectionTestOut(
                ok=False,
                problem=f"Jira rejected the login ({exc.response.status_code}). Check JIRA_EMAIL and JIRA_API_TOKEN in .env.",
            )
        return ConnectionTestOut(ok=False, problem=describe_error(exc))
    except httpx.RequestError:
        return ConnectionTestOut(
            ok=False, problem=f"Could not reach {jira.config.base_url}. Check JIRA_BASE_URL and your network."
        )
    try:
        jira.get_project()
    except httpx.HTTPStatusError as exc:
        return ConnectionTestOut(
            ok=False,
            problem=f"Signed in as {who}, but project {project} could not be read ({exc.response.status_code}). "
            "Check JIRA_PROJECT_KEY and that this account can see the project.",
        )
    except httpx.RequestError:
        return ConnectionTestOut(
            ok=False, problem=f"Signed in as {who}, but the project request did not get through."
        )
    return ConnectionTestOut(ok=True, detail=f"Signed in as {who}. Project {project} is reachable.")


def describe_model_error(exc: Exception) -> str:
    """A reason a person can act on, for the failures that actually happen with a Gemini key."""
    if isinstance(exc, TimeoutError):
        return f"The model did not answer within {MODEL_TEST_SECONDS} seconds. Try again."
    if not isinstance(exc, genai_errors.APIError):
        return f"Could not reach the model ({type(exc).__name__}). Check your network."
    code = exc.code
    message = str(exc.message or "")
    if code in (401, 403) or (code == 400 and "api key" in message.lower()):
        return f"The model rejected the key ({code}). Check GEMINI_API_KEY in .env."
    if code in (402, 429):
        return (
            f"The model refused the request ({code}): the account is out of credit, over its quota, or being "
            "rate limited. Check billing and limits for this key."
        )
    if code == 404:
        return f"The model {orchestrator_model()!r} was not found ({code}). Check ORCHESTRATOR_MODEL in .env."
    if code >= 500:
        return f"The model service is having trouble ({code}). Try again shortly."
    return f"The model returned {code}: {message[:200]}"


@router.post("/settings/test-model", response_model=ConnectionTestOut)
async def test_model(client: genai.Client | None = Depends(get_model_client)) -> ConnectionTestOut:
    """The smallest possible request, to prove the key works and has credit. It costs a few tokens."""
    if client is None:
        return ConnectionTestOut(
            ok=False, problem="No model key is set. Add GEMINI_API_KEY to .env and restart."
        )
    model = orchestrator_model()
    try:
        await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents="Reply with the single word OK.",
                config=genai_types.GenerateContentConfig(max_output_tokens=8),
            ),
            timeout=MODEL_TEST_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - every failure becomes a sentence for the page, never a 500
        return ConnectionTestOut(ok=False, problem=describe_model_error(exc))
    return ConnectionTestOut(ok=True, detail=f"The model {model} answered.")
