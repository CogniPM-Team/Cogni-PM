"""Finds the repo root and loads its .env. Modules that read credentials from the
environment import this for the side effect.

Nothing in the backend may print to stdout: the MCP gateway speaks over stdio, and a
stray print() corrupts the protocol. Log to stderr instead.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")
