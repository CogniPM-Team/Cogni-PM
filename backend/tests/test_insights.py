"""Insights: the oversight numbers. The seeded database is the worked example from docs/phases.md ("Insights: what
the numbers mean"), so the tests prove the code gives the answers the definitions give, including the awkward cases:
nothing to divide by, a run that failed part-way, a run that never became reviewable, and a range that cuts a group."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from cognipm.api.deps import get_conn
from cognipm.api.main import app
from cognipm.api.routes.insights import _nearest_rank, seconds_to_decision, summarise
from tests.test_api import _Shared

DAY = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def add_run(
    conn,
    run_id,
    status,
    *,
    drafts=(),
    minutes=None,
    tokens=None,
    started=DAY,
    task="p1",
    mode="M2",
    rerun_of=None,
    ready=True,
):
    """A run with its drafts. Each draft is "created", "edited" (created after the reviewer edited it), "left_out",
    "edited_left_out" or "proposed"."""
    ready_at = started + timedelta(minutes=1) if ready else None
    decided_at = ready_at + timedelta(minutes=minutes) if minutes is not None and ready_at else None
    conn.execute(
        "INSERT INTO runs (id, mode, task_type, agent, scope, status, created_at, ready_at, decided_at, rerun_of, "
        "input_tokens, output_tokens) VALUES (%s, %s, %s, 'orchestrator:test', 'scope', %s, %s, %s, %s, %s, %s, %s)",
        (
            run_id,
            mode,
            task,
            status,
            started,
            ready_at,
            decided_at,
            rerun_of,
            *((tokens[0], tokens[1]) if tokens else (None, None)),
        ),
    )
    for n, outcome in enumerate(drafts):
        payload = Jsonb({"summary": f"{run_id} draft {n}"})
        edited = payload if outcome in ("edited", "edited_left_out") else None
        state = {
            "created": "applied",
            "edited": "applied",
            "left_out": "rejected",
            "edited_left_out": "rejected",
            "proposed": "proposed",
        }[outcome]
        conn.execute(
            "INSERT INTO staged_changes (id, run_id, kind, payload, edited_payload, sources, reasoning, status) "
            "VALUES (%s, %s, 'backlog_item', %s, %s, %s, 'because', %s)",
            (f"{run_id}-d{n}", run_id, payload, edited, Jsonb(["quote"]), state),
        )
    conn.commit()


def refuse(conn, run_id, rule):
    conn.execute(
        "INSERT INTO audit_log (run_id, actor, mode, action, outcome, detail) "
        "VALUES (%s, 'orchestrator:test', 'M2', %s, 'refused', 'no')",
        (run_id, f"guardrail:{rule}"),
    )
    conn.commit()


def worked_example(conn):
    add_run(conn, "A", "applied", drafts=["created", "created", "edited"], minutes=4, tokens=(600, 300))
    add_run(conn, "B", "applied", drafts=["created", "created"], minutes=10, tokens=(450, 250))
    add_run(
        conn, "C", "rejected", drafts=["left_out"] * 3 + ["edited_left_out"], minutes=2, tokens=(700, 400)
    )
    add_run(conn, "D", "rejected", drafts=["left_out"] * 3, minutes=6, tokens=(500, 300))
    add_run(conn, "E", "awaiting_review", drafts=["proposed"] * 2, tokens=(300, 200), rerun_of="D")
    refuse(conn, "C", "no_duplicate")
    refuse(conn, "C", "no_duplicate")
    refuse(conn, "A", "valid_parent")


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: _Shared(conn)
    with TestClient(app) as c:
        c.conn = conn
        yield c
    app.dependency_overrides.clear()


def numbers(client, **params):
    response = client.get("/api/insights", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_worked_example_gives_the_answers_the_definitions_give(client):
    worked_example(client.conn)

    n = numbers(client)

    assert (n["runs_started"], n["runs_decided"], n["runs_open"]) == (5, 4, 1)
    assert (n["runs_approved"], n["runs_rejected"]) == (2, 2)  # approval 2 of 4, rejection 2 of 4
    assert n["drafts_reviewed"] == 12
    assert (n["drafts_created_as_written"], n["drafts_created_after_edit"], n["drafts_left_out"]) == (4, 1, 7)
    assert n["drafts_edited"] == 2  # edit rate 2 of 12: one in A, one in C
    assert (n["decisions_timed"], n["decision_seconds_median"], n["decision_seconds_p90"]) == (4, 300, 600)
    assert n["reruns"] == 1  # 1 of 5 runs: E replaced D
    assert n["refusals"] == [{"rule": "no_duplicate", "count": 2}, {"rule": "valid_parent", "count": 1}]
    assert n["refusals_total"] == 3
    assert (n["tokens_total"], n["tokens_runs"], n["tokens_average"]) == (
        4000,
        5,
        800,
    )  # the open run costs too
    assert n["approved_untouched"] == 1  # B only: A had an edit


def test_every_reviewed_draft_ends_in_exactly_one_of_the_three_states(client):
    worked_example(client.conn)

    n = numbers(client)

    assert (
        n["drafts_created_as_written"] + n["drafts_created_after_edit"] + n["drafts_left_out"]
        == n["drafts_reviewed"]
    )
    assert n["runs_approved"] + n["runs_rejected"] == n["runs_decided"]
    assert n["runs_decided"] + n["runs_open"] == n["runs_started"]


def test_with_nothing_to_divide_by_every_figure_is_zero_or_empty_not_an_error(client):
    n = numbers(client)

    assert (n["runs_started"], n["runs_decided"], n["drafts_reviewed"], n["reruns"]) == (0, 0, 0, 0)
    assert (n["decision_seconds_median"], n["decision_seconds_p90"], n["tokens_average"]) == (
        None,
        None,
        None,
    )
    assert n["refusals"] == [] and n["tokens_total"] == 0 and n["approved_untouched"] == 0


def test_only_runs_started_in_the_range_are_in_the_group_and_the_end_is_exclusive(client):
    add_run(client.conn, "early", "applied", drafts=["created"], minutes=1, started=DAY - timedelta(days=3))
    add_run(client.conn, "inside", "applied", drafts=["created"], minutes=1, started=DAY)
    add_run(client.conn, "late", "applied", drafts=["created"], minutes=1, started=DAY + timedelta(days=3))
    refuse(client.conn, "early", "no_duplicate")  # a refusal on a run outside the range is not counted

    inside = numbers(
        client, **{"from": (DAY - timedelta(days=1)).isoformat(), "to": (DAY + timedelta(days=1)).isoformat()}
    )

    assert (inside["runs_started"], inside["refusals_total"]) == (1, 0)
    assert numbers(client, to=DAY.isoformat())["runs_started"] == 1  # a run started exactly at "to" is out
    assert (
        numbers(client, **{"from": DAY.isoformat()})["runs_started"] == 2
    )  # and one started exactly at "from" is in


def test_the_group_can_be_narrowed_to_one_task_and_one_mode(client):
    add_run(client.conn, "p1-run", "applied", drafts=["created"], minutes=1, task="p1")
    add_run(client.conn, "p2-run", "applied", drafts=["created", "created"], minutes=1, task="p2")

    assert numbers(client, task="p2")["drafts_reviewed"] == 2
    assert numbers(client, task="p1")["drafts_reviewed"] == 1
    assert numbers(client, mode="M3")["runs_started"] == 0
    assert client.get("/api/insights", params={"task": "p3"}).status_code == 422


def test_a_run_that_failed_part_way_is_open_and_its_drafts_are_not_counted_as_reviewed(client):
    add_run(client.conn, "half", "failed", drafts=["created", "proposed"], minutes=None)

    n = numbers(client)

    assert (n["runs_started"], n["runs_decided"], n["runs_open"]) == (1, 0, 1)
    assert n["drafts_reviewed"] == 0 and n["decision_seconds_median"] is None


def test_a_decided_run_that_never_became_reviewable_is_decided_but_has_no_time(client):
    add_run(client.conn, "odd", "rejected", drafts=["left_out"], ready=False)
    add_run(client.conn, "ok", "applied", drafts=["created"], minutes=8)

    n = numbers(client)

    assert (n["runs_decided"], n["decisions_timed"]) == (2, 1)
    assert n["decision_seconds_median"] == 480


def test_a_run_approved_with_a_draft_left_out_counts_as_approved_but_not_untouched(client):
    add_run(client.conn, "mixed", "applied", drafts=["created", "left_out"], minutes=3)

    n = numbers(client)

    assert (n["runs_approved"], n["approved_untouched"]) == (1, 0)
    assert (n["drafts_created_as_written"], n["drafts_left_out"]) == (1, 1)


def test_nearest_rank_and_median_follow_the_definition():
    assert _nearest_rank([2, 4, 6, 10], 0.9) == 10  # the 4th of 4
    assert _nearest_rank([5], 0.9) == 5
    assert _nearest_rank(list(range(1, 11)), 0.9) == 9  # the 9th of 10
    runs = [
        {
            "status": "applied",
            "ready_at": DAY,
            "decided_at": DAY + timedelta(seconds=s),
            "input_tokens": None,
            "output_tokens": None,
            "rerun_of": None,
            "reviewed": 0,
            "as_written": 0,
            "after_edit": 0,
            "left_out": 0,
            "edited": 0,
            "not_created": 0,
        }
        for s in (60, 120, 180, 240)
    ]
    assert summarise(runs, []).decision_seconds_median == 150  # the middle two, averaged


def test_a_time_is_never_negative(client):
    run = {"status": "applied", "ready_at": DAY, "decided_at": DAY - timedelta(seconds=5)}

    assert seconds_to_decision(run) == 0.0


def test_the_download_has_a_line_per_run_with_the_figures_each_number_is_made_from(client):
    worked_example(client.conn)

    response = client.get("/api/insights/export.csv")

    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [r["run"] for r in rows] == ["A", "B", "C", "D", "E"]
    a = rows[0]
    assert (a["status"], a["minutes_to_decision"], a["drafts_reviewed"], a["created_after_edit"]) == (
        "applied",
        "4.0",
        "3",
        "1",
    )
    assert rows[4]["minutes_to_decision"] == "" and rows[4]["replaces_run"] == "D"
    # a hand count from the file gives the page's numbers
    assert sum(int(r["created_as_written"]) for r in rows) == 4
    assert sum(int(r["left_out"]) for r in rows) == 7
    assert sum(int(r["input_tokens"]) + int(r["output_tokens"]) for r in rows) == 4000


def test_the_download_uses_the_same_group_as_the_page(client):
    add_run(client.conn, "p1-run", "applied", drafts=["created"], minutes=1, task="p1")
    add_run(client.conn, "p2-run", "applied", drafts=["created"], minutes=1, task="p2")

    rows = list(
        csv.DictReader(io.StringIO(client.get("/api/insights/export.csv", params={"task": "p2"}).text))
    )

    assert [r["run"] for r in rows] == ["p2-run"]
