"""Insights: is human oversight happening, and is the AI useful? Every number follows the definitions in
docs/phases.md ("Insights: what the numbers mean"); change a definition there first and the code second.

Nothing new is stored. One query returns a line per run in the group (the runs started in the date range), and both
the numbers and the downloadable CSV are made from those same lines, so the page and the file cannot disagree.
"""

from __future__ import annotations

import csv
import io
import math
import statistics
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from cognipm.api.deps import get_conn
from cognipm.api.schemas import InsightsOut, RefusalCount
from cognipm.db.connection import Connection

router = APIRouter(tags=["insights"])

DECIDED = ("applied", "rejected")  # a run is decided once the reviewer approved or rejected it

# One line per run in the group. The draft counts say what became of each draft; "reviewed" drafts are the ones that
# ended created or left out (every draft of a decided run does).
RUNS = """
SELECT r.id, r.task_type, r.mode, r.status, r.created_at, r.ready_at, r.decided_at, r.rerun_of,
       r.input_tokens, r.output_tokens,
       COUNT(c.id) FILTER (WHERE c.status IN ('applied', 'rejected')) AS reviewed,
       COUNT(c.id) FILTER (WHERE c.status = 'applied' AND c.edited_payload IS NULL) AS as_written,
       COUNT(c.id) FILTER (WHERE c.status = 'applied' AND c.edited_payload IS NOT NULL) AS after_edit,
       COUNT(c.id) FILTER (WHERE c.status = 'rejected') AS left_out,
       COUNT(c.id) FILTER (WHERE c.status IN ('applied', 'rejected') AND c.edited_payload IS NOT NULL) AS edited,
       COUNT(c.id) FILTER (WHERE c.status <> 'applied') AS not_created
FROM runs r
LEFT JOIN staged_changes c ON c.run_id = r.id
WHERE {where}
GROUP BY r.id
ORDER BY r.created_at, r.id
"""

REFUSALS = """
SELECT substring(a.action FROM 11) AS rule, COUNT(*) AS n
FROM audit_log a
WHERE a.action LIKE 'guardrail:%%' AND a.outcome = 'refused'
  AND a.run_id IN (SELECT r.id FROM runs r WHERE {where})
GROUP BY rule
ORDER BY n DESC, rule
"""


def _where(
    since: datetime | None, until: datetime | None, task: str | None, mode: str | None
) -> tuple[str, list[object]]:
    """The group of runs: those started in the range, for the chosen task and mode. Nothing typed is put in the SQL."""
    clauses, params = ["TRUE"], []
    for clause, value in (
        ("r.created_at >= %s", since),
        ("r.created_at < %s", until),
        ("r.task_type = %s", task),
        ("r.mode = %s", mode),
    ):
        if value is not None:
            clauses.append(clause)
            params.append(value)
    return " AND ".join(clauses), params


def _nearest_rank(sorted_values: list[float], fraction: float) -> float:
    """The value that `fraction` of the values are at or below (nearest-rank, as the definitions say)."""
    return sorted_values[math.ceil(fraction * len(sorted_values)) - 1]


def seconds_to_decision(run: dict) -> float | None:
    """decided_at minus ready_at, for a decided run that became reviewable; otherwise nothing to measure."""
    if run["status"] not in DECIDED or run["ready_at"] is None or run["decided_at"] is None:
        return None
    return max(0.0, (run["decided_at"] - run["ready_at"]).total_seconds())


def summarise(runs: list[dict], refusals: list[tuple[str, int]]) -> InsightsOut:
    """The numbers, from the per-run lines. Pure: the tests check it against the worked example in the definitions."""
    decided = [r for r in runs if r["status"] in DECIDED]
    approved = [r for r in decided if r["status"] == "applied"]
    times = sorted(t for t in (seconds_to_decision(r) for r in decided) if t is not None)
    with_tokens = [r for r in runs if r["input_tokens"] is not None and r["output_tokens"] is not None]
    tokens_total = sum(r["input_tokens"] + r["output_tokens"] for r in with_tokens)
    return InsightsOut(
        runs_started=len(runs),
        runs_decided=len(decided),
        runs_open=len(runs) - len(decided),
        runs_approved=len(approved),
        runs_rejected=len(decided) - len(approved),
        drafts_reviewed=sum(r["reviewed"] for r in decided),
        drafts_created_as_written=sum(r["as_written"] for r in decided),
        drafts_created_after_edit=sum(r["after_edit"] for r in decided),
        drafts_left_out=sum(r["left_out"] for r in decided),
        drafts_edited=sum(r["edited"] for r in decided),
        decisions_timed=len(times),
        decision_seconds_median=statistics.median(times) if times else None,
        decision_seconds_p90=_nearest_rank(times, 0.9) if times else None,
        reruns=sum(1 for r in runs if r["rerun_of"] is not None),
        refusals=[RefusalCount(rule=rule, count=n) for rule, n in refusals],
        refusals_total=sum(n for _, n in refusals),
        tokens_total=tokens_total,
        tokens_runs=len(with_tokens),
        tokens_average=tokens_total / len(with_tokens) if with_tokens else None,
        approved_untouched=sum(1 for r in approved if r["not_created"] == 0 and r["edited"] == 0),
    )


def _fetch(conn: Connection, since, until, task, mode) -> tuple[list[dict], list[tuple[str, int]]]:
    where, params = _where(since, until, task, mode)
    runs = conn.execute(RUNS.format(where=where), params).fetchall()
    refusals = [(r["rule"], r["n"]) for r in conn.execute(REFUSALS.format(where=where), params).fetchall()]
    return runs, refusals


@router.get("/insights", response_model=InsightsOut)
def insights(
    since: datetime | None = Query(
        default=None, alias="from", description="Only runs started at or after this time"
    ),
    until: datetime | None = Query(
        default=None, alias="to", description="Only runs started before this time"
    ),
    task: Literal["p1", "p2"] | None = None,
    mode: Literal["M2", "M3"] | None = None,
    conn: Connection = Depends(get_conn),
) -> InsightsOut:
    """The oversight numbers for the runs started in the range. Reads only the runs, drafts and activity log."""
    return summarise(*_fetch(conn, since, until, task, mode))


COLUMNS = (
    "run",
    "task",
    "mode",
    "status",
    "started",
    "ready_for_review",
    "decided",
    "minutes_to_decision",
    "replaces_run",
    "drafts_reviewed",
    "created_as_written",
    "created_after_edit",
    "left_out",
    "edited",
    "input_tokens",
    "output_tokens",
)


@router.get("/insights/export.csv", response_class=Response)
def export_insights(
    since: datetime | None = Query(default=None, alias="from"),
    until: datetime | None = Query(default=None, alias="to"),
    task: Literal["p1", "p2"] | None = None,
    mode: Literal["M2", "M3"] | None = None,
    conn: Connection = Depends(get_conn),
) -> Response:
    """One line per run in the group, with the figures each number is made from, so any number on the page can be
    checked by hand. Same filters as the page."""
    runs, _ = _fetch(conn, since, until, task, mode)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for r in runs:
        seconds = seconds_to_decision(r)
        writer.writerow(
            [
                r["id"],
                r["task_type"],
                r["mode"],
                r["status"],
                r["created_at"].isoformat(),
                r["ready_at"].isoformat() if r["ready_at"] else "",
                r["decided_at"].isoformat() if r["decided_at"] else "",
                "" if seconds is None else round(seconds / 60, 2),
                r["rerun_of"] or "",
                r["reviewed"],
                r["as_written"],
                r["after_edit"],
                r["left_out"],
                r["edited"],
                "" if r["input_tokens"] is None else r["input_tokens"],
                "" if r["output_tokens"] is None else r["output_tokens"],
            ]
        )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cognipm-insights.csv"'},
    )
