"""The control-plane API: JSON over FastAPI, consumed by the React frontend.

Run it with `uvicorn cognipm.api.main:app --reload` from backend/. The frontend's dev server proxies /api
to it; in production set CORS_ORIGINS to the frontend's URL.

Everything except signing in needs a signed-in person, and only a PM may change anything (see api/deps.py and
cognipm/auth.py, including the limits). Sign-in attempts are not rate-limited yet: put something that does that in
front of the API before it is reachable from the open internet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cognipm.api.deps import current_user
from cognipm.api.launcher import fail_orphaned_runs
from cognipm.api.routes import (
    artifacts,
    audit,
    auth,
    chat,
    documents,
    insights,
    modes,
    runs,
    settings,
    stories,
)
from cognipm.api.static import frontend_dist, mount_frontend
from cognipm.auth import ensure_first_user
from cognipm.config import cors_origins
from cognipm.db.connection import get_connection


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    conn = get_connection()  # applies pending migrations once, and fails fast if the database is down
    fail_orphaned_runs(conn)  # a run that was in flight when the server stopped cannot continue
    ensure_first_user(conn)  # a new install gets its first PM from .env, so someone can sign in
    conn.close()
    yield


app = FastAPI(title="CogniPM API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth.router, prefix="/api")  # the one router that works without being signed in

for router in (
    runs.router,
    chat.router,
    audit.router,
    artifacts.router,
    documents.router,
    insights.router,
    modes.router,
    settings.router,
    stories.router,
):
    app.include_router(router, prefix="/api", dependencies=[Depends(current_user)])


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"ok": True}


# Last, so it only answers what nothing above did. Does nothing unless the website has been built.
mount_frontend(app, frontend_dist())
