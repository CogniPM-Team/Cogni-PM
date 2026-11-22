"""The control-plane API: JSON over FastAPI, consumed by the React frontend.

Run it with `uvicorn cognipm.api.main:app --reload` from backend/. The frontend's dev server proxies /api
to it; in production set CORS_ORIGINS to the frontend's URL.

THERE IS NO LOGIN YET: exactly one implicit reviewer (see cognipm.config.HUMAN_ACTOR). Do not expose this
API publicly until that changes: anyone who can reach it can approve a write to Jira. (Planned: Phase 7.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cognipm.api.launcher import fail_orphaned_runs
from cognipm.api.routes import audit, chat, modes, runs, stories
from cognipm.api.static import frontend_dist, mount_frontend
from cognipm.config import cors_origins
from cognipm.db.connection import get_connection


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    conn = get_connection()  # applies pending migrations once, and fails fast if the database is down
    fail_orphaned_runs(conn)  # a run that was in flight when the server stopped cannot continue
    conn.close()
    yield


app = FastAPI(title="CogniPM API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["*"], allow_headers=["*"])

for router in (runs.router, chat.router, audit.router, modes.router, stories.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"ok": True}


# Last, so it only answers what nothing above did. Does nothing unless the website has been built.
mount_frontend(app, frontend_dist())
