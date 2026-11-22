"""Persists what a run did to `run_steps` (and the study metrics to `runs`), so progress
survives a restart and the console can replay it. These are the orchestrator's own
bookkeeping rows - not a Jira write and not a gateway tool."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

import psycopg
from psycopg.types.json import Jsonb

StepListener = Callable[[dict], None]


class StepRecorder:
    """Writes each step to the database and tells an optional live listener (the SSE stream, later)."""

    def __init__(self, conn: psycopg.Connection, listener: StepListener | None = None):
        self.conn = conn
        self.listener = listener
        self.run_id: str | None = None

    def __call__(self, phase: str, state: str, *, tool: str | None = None, **detail: object) -> None:
        if self.run_id is not None:
            self.conn.execute(
                "INSERT INTO run_steps (run_id, phase, state, tool, detail) VALUES (%s, %s, %s, %s, %s)",
                (self.run_id, phase, state, tool, Jsonb(detail, dumps=_dumps) if detail else None),
            )
            self.conn.commit()
        if self.listener is not None:
            try:
                self.listener({"run_id": self.run_id, "phase": phase, "state": state, "tool": tool, **detail})
            except Exception as exc:  # noqa: BLE001 - a broken listener must never break the run
                print(f"progress listener failed: {exc!r}", file=sys.stderr)


def _dumps(value: object) -> str:
    return json.dumps(value, default=str)


def record_usage(
    conn: psycopg.Connection, run_id: str, *, model: str, input_tokens: int, output_tokens: int
) -> None:
    """Add a model call's cost to the run: tokens per run is one of the study's measures."""
    conn.execute(
        "UPDATE runs SET model = %s, input_tokens = COALESCE(input_tokens, 0) + %s, "
        "output_tokens = COALESCE(output_tokens, 0) + %s WHERE id = %s",
        (model, input_tokens, output_tokens, run_id),
    )
    conn.commit()


def record_input(
    conn: psycopg.Connection,
    run_id: str,
    *,
    input_text: str | None = None,
    instructions: str | None = None,
    story_key: str | None = None,
    rerun_of: str | None = None,
) -> None:
    """Keep what a run was asked to work on: the review screen shows each cited quote in this text, and
    a rerun starts from it. Only the values given are written."""
    columns = {
        "input_text": input_text,
        "instructions": instructions,
        "story_key": story_key,
        "rerun_of": rerun_of,
    }
    given = {k: v for k, v in columns.items() if v is not None}
    if not given:
        return
    assignments = ", ".join(f"{k} = %s" for k in given)  # column names are the fixed ones above, never input
    conn.execute(f"UPDATE runs SET {assignments} WHERE id = %s", (*given.values(), run_id))
    conn.commit()


def mark_run_failed(conn: psycopg.Connection, run_id: str, reason: str) -> None:
    """The run cannot continue. Drafts already staged stay staged for the PM to see."""
    conn.rollback()
    conn.execute("UPDATE runs SET status = 'failed', comment = %s WHERE id = %s", (reason, run_id))
    conn.commit()
