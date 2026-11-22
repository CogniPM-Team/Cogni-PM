"""Starts an orchestrator run in the background and returns its id as soon as the gateway has opened it.

The run keeps going after the HTTP request that started it has returned; the page follows it through
GET /runs/{id}/events. Runs live in this process only: a restart abandons any run in flight, so startup
marks those `failed` (see `fail_orphaned_runs`) rather than leaving them `running` forever. Move to a
persisted queue before running more than one API process.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from collections.abc import Callable
from typing import Literal

from cognipm.db.connection import Connection
from cognipm.orchestrator.steps import mark_run_failed
from cognipm.orchestrator.tasks import OrchestratorError, run_task

BACKGROUND: set[asyncio.Task] = set()  # keeps a reference, or the task could be garbage-collected mid-run
START_TIMEOUT = 60.0  # how long to wait for the gateway to open the run
_UNEXPECTED = "The run hit an unexpected error. The server log has the details."


class StartFailed(Exception):
    """The run could not begin (the gateway refused it, or the story could not be read)."""


async def start_task_run(
    *,
    open_connection: Callable[[], Connection],
    options: dict,
    task: Literal["p1", "p2"],
    input_text: str = "",
    story_key: str | None = None,
    context_jql: str | None = None,
    instructions: str = "",
    rerun_of: str | None = None,
) -> str:
    """Start the run and return its id. Raises StartFailed if it could not be opened."""
    loop = asyncio.get_running_loop()
    started: asyncio.Future[str] = loop.create_future()
    holder: dict[str, str] = {}

    def on_started(run_id: str) -> None:
        holder["run_id"] = run_id
        if not started.done():
            started.set_result(run_id)

    async def work() -> None:
        conn = open_connection()
        try:
            await run_task(
                conn=conn,
                task=task,
                input_text=input_text,
                story_key=story_key,
                context_jql=context_jql,
                instructions=instructions,
                rerun_of=rerun_of,
                on_run_started=on_started,
                **options,
            )
        except OrchestratorError as exc:
            # Written for humans, and run_task has already marked a started run failed.
            if not started.done():
                started.set_exception(StartFailed(str(exc)))
        except (Exception, BaseExceptionGroup):  # anyio wraps stdio failures in a group
            traceback.print_exc(file=sys.stderr)
            if "run_id" in holder:
                mark_run_failed(conn, holder["run_id"], _UNEXPECTED)
            if not started.done():
                started.set_exception(StartFailed(_UNEXPECTED))
        finally:
            conn.close()
            if not started.done():
                started.set_exception(StartFailed("the run ended before it started"))

    background = loop.create_task(work())
    BACKGROUND.add(background)
    background.add_done_callback(BACKGROUND.discard)
    try:
        return await asyncio.wait_for(asyncio.shield(started), START_TIMEOUT)
    except TimeoutError as exc:
        raise StartFailed("the run did not start in time") from exc


def fail_orphaned_runs(conn: Connection) -> int:
    """Mark runs that were `running` when the server stopped as failed. Returns how many."""
    rows = conn.execute(
        "UPDATE runs SET status = 'failed', comment = 'The server restarted while this run was in progress.' "
        "WHERE status = 'running' RETURNING id"
    ).fetchall()
    conn.commit()
    return len(rows)
