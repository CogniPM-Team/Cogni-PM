"""Pause, stop and cancel, and how a run ends early.

A person asks by setting `runs.control` (through the API). The running task looks at it BETWEEN steps, in
`checkpoint`, and never in the middle of one: a model call or a Jira request that has started always finishes, so a
request can never leave something half done.

- pause   the run holds at the next step boundary (status `paused`) until someone resumes it
- stop    the run ends at the next boundary; whatever is already staged stays (status `stopped`)
- cancel  the run ends at the next boundary and its staged drafts are discarded (status `cancelled`)

A run also ends early, without being asked, when the agent needs an answer: `waiting_for_information`.

THE LIMITS: this is in memory, in the API process. After a restart a run that was running, paused or waiting is marked
failed (the launcher does that), not resumed: saving a run's graph state to the database so it could survive a restart
would need a LangGraph checkpoint store, which is a new dependency and not needed yet.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from cognipm.db.audit import log_audit
from cognipm.db.connection import Connection

POLL_SECONDS = 0.5  # how often a paused run looks to see whether it was resumed
LIVE = (
    "running",
    "paused",
    "waiting_for_information",
)  # a run a person can still pause, stop, cancel or answer
Ending = Literal["stopped", "cancelled", "waiting_for_information"]


class RunEnded(Exception):
    """Raised at a checkpoint (or when the agent asks a question) to leave the graph cleanly. Not an error."""

    def __init__(self, how: Ending):
        super().__init__(how)
        self.how = how


async def checkpoint(conn: Connection, run_id: str, *, poll: float = POLL_SECONDS) -> None:
    """The one place a person's request takes effect. Returns when the run may carry on; raises RunEnded to end it."""
    while True:
        row = conn.execute("SELECT control, status FROM runs WHERE id = %s", (run_id,)).fetchone()
        conn.commit()  # end the read transaction so the next look sees what the API has written meanwhile
        control, status = row["control"], row["status"]
        if control == "cancel":
            raise RunEnded("cancelled")
        if control == "stop":
            raise RunEnded("stopped")
        if control == "pause":
            if status != "paused":
                conn.execute("UPDATE runs SET status = 'paused' WHERE id = %s", (run_id,))
                conn.commit()
            await asyncio.sleep(poll)
            continue
        if status == "paused":  # resumed: the request was withdrawn
            conn.execute("UPDATE runs SET status = 'running' WHERE id = %s", (run_id,))
            conn.commit()
        return


def settle(
    conn: Connection, run_id: str, how: Ending, *, question: str | None = None, agent: str = ""
) -> None:
    """Record how a run ended early. A cancelled run's staged drafts are discarded (marked rejected, so the audit trail
    still shows they existed); a stopped run keeps them. The person's request was already written to the audit log
    when they made it; an agent's question is written here, by the agent."""
    conn.execute(
        "UPDATE runs SET status = %s, control = NULL, question = %s WHERE id = %s",
        (how, question if how == "waiting_for_information" else None, run_id),
    )
    if how == "cancelled":
        conn.execute(
            "UPDATE staged_changes SET status = 'rejected' WHERE run_id = %s AND status IN ('proposed', 'failed')",
            (run_id,),
        )
    conn.commit()
    if how == "waiting_for_information":
        log_audit(
            conn,
            run_id=run_id,
            actor=agent,
            mode="M2",
            action="ask_clarification",
            outcome="asked",
            detail="the agent needs an answer before it can draft",
        )
