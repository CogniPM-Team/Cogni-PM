"""FastAPI dependencies. Tests override these through `app.dependency_overrides` to inject a test
database, a fake Jira and a scripted model."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from functools import lru_cache

from google import genai

from cognipm.db.connection import Connection, connect
from cognipm.gateway.jira import JiraClient


def conn_factory() -> Callable[[], Connection]:
    """How background work (which outlives the request) opens its own connection."""
    return connect


def get_conn() -> Iterator[Connection]:
    """One connection per request. Migrations run once at startup, not here."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@lru_cache
def get_jira() -> JiraClient:
    return JiraClient()


def get_model_client() -> genai.Client | None:
    """The Gemini client for the Settings connection test; None when no key is set. Tests override this with a
    scripted model, so the suite never spends money."""
    key = os.environ.get("GEMINI_API_KEY")
    return genai.Client(api_key=key) if key else None


def get_run_options() -> dict[str, dict]:
    """Extra keyword arguments for the orchestrator, per surface: {"task": {...}, "chat": {...}} holding
    `gemini` and `mcp_server`. Empty in production, which means the real model and a real gateway
    subprocess; tests supply a scripted model and in-process gateways."""
    return {"task": {}, "chat": {}}
