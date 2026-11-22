"""Serves the built website from the API, so the whole product is one address and one process.

In development the website runs on Vite's own server and this does nothing. In the Docker image the website is built
into `frontend/dist` and this serves it: files that exist are returned as they are, and every other path returns
`index.html`, so a page opened directly (`/approvals/<id>`) or reloaded still loads the app and lets the browser
router take over. `/api` paths are never answered with the page: an unknown API path is a plain 404.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from cognipm.config import REPO_ROOT


def frontend_dist() -> Path:
    """Where the built website is: `frontend/dist`, or wherever COGNIPM_FRONTEND_DIST says."""
    return Path(os.environ.get("COGNIPM_FRONTEND_DIST") or REPO_ROOT / "frontend" / "dist")


def mount_frontend(app: FastAPI, dist: Path) -> bool:
    """Serve `dist` from `app`. Returns False (and adds nothing) when there is no built website there."""
    index = dist / "index.html"
    if not index.is_file():
        return False
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def website(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):  # never a file outside dist
            return FileResponse(candidate)
        return FileResponse(index)

    return True
