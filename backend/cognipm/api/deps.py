"""FastAPI dependencies. Tests override these through `app.dependency_overrides` to inject a test
database, a fake Jira and a scripted model."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from google import genai

from cognipm.auth import COOKIE_NAME, User, session_user
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


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_user(request: Request, conn: Connection = Depends(get_conn)) -> User:
    """Who is signed in, from the session cookie. 401 when nobody is."""
    user = session_user(conn, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def current_user(request: Request, user: User = Depends(get_user)) -> User:
    """The rule for the whole API, in one place: anyone signed in may look, and only a PM may change anything. Every
    router except sign-in depends on this, so a new route cannot forget it."""
    if request.method not in SAFE_METHODS and not user.is_pm:
        raise HTTPException(
            status_code=403, detail="Your account can look but not change anything. Ask a PM."
        )
    return user


def require_pm(user: User = Depends(get_user)) -> User:
    """For what even looking at is a PM's business (the list of people)."""
    if not user.is_pm:
        raise HTTPException(status_code=403, detail="Only a PM can do that.")
    return user


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
