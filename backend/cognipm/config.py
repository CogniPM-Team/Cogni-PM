"""Finds the repo root and loads its .env. Modules that read credentials from the
environment import this for the side effect.

Nothing in the backend may print to stdout: the MCP gateway speaks over stdio, and a
stray print() corrupts the protocol. Log to stderr instead.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")

# Before sign-in existed every decision was recorded as this one shared reviewer. Those rows stay as they were; new
# ones name the person (see cognipm/auth.py: User.actor).
LEGACY_REVIEWER = "human:reviewer"
TOKEN_TTL_MINUTES = 15


def database_url() -> str:
    """Read at call time, not import time, so tests can monkeypatch the environment."""
    return os.environ.get("DATABASE_URL", "postgresql://cognipm:cognipm@localhost:5432/cognipm")


def orchestrator_model() -> str:
    return os.environ.get("ORCHESTRATOR_MODEL", "gemini-3.6-flash")


def max_items_per_run() -> int:
    """How many issues one run may stage or create, so a bad run (or a hostile document) cannot flood
    the backlog. Read at call time so tests can change it."""
    return int(os.environ.get("COGNIPM_MAX_ITEMS_PER_RUN", "20"))


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API (the frontend's URL in production; in development Vite
    proxies /api, so this only matters when deployed)."""
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]
