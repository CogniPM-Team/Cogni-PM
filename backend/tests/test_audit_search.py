"""Finding things in the activity log: date range, text search, and a CSV of everything that matches. The CSV
must be safe to open in a spreadsheet, because the text in it can come from a document or a model."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from cognipm.api.deps import get_conn
from cognipm.api.main import app
from tests.test_api import _Shared


def add(conn, ts, action, *, detail=None, actor="human:reviewer", mode="M2", before=None, run_id=None):
    conn.execute(
        "INSERT INTO audit_log (ts, run_id, actor, mode, action, outcome, detail, before) "
        "VALUES (%s, %s, %s, %s, %s, 'ok', %s, %s)",
        (ts, run_id, actor, mode, action, detail, None if before is None else Jsonb(before)),
    )
    conn.commit()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: _Shared(conn)
    with TestClient(app) as c:
        c.conn = conn
        yield c
    app.dependency_overrides.clear()


def actions(client, **params):
    return [r["action"] for r in client.get("/api/audit", params=params).json()["rows"]]


def test_a_date_range_keeps_the_start_and_drops_the_end(client):
    add(client.conn, "2026-11-17T09:00:00+00:00", "monday")
    add(client.conn, "2026-11-18T09:00:00+00:00", "tuesday")
    add(client.conn, "2026-11-19T09:00:00+00:00", "wednesday")

    assert actions(client, **{"from": "2026-11-18T00:00:00+00:00", "to": "2026-11-19T00:00:00+00:00"}) == [
        "tuesday"
    ]
    assert actions(client, **{"from": "2026-11-18T09:00:00+00:00"}) == [
        "wednesday",
        "tuesday",
    ]  # inclusive start
    assert actions(client, to="2026-11-18T09:00:00+00:00") == ["monday"]  # exclusive end


def test_search_finds_the_note_the_actor_and_the_text_of_an_edit(client):
    add(client.conn, "2026-11-18T09:00:00+00:00", "create_issue", detail="2 issue(s) created for invoices")
    add(client.conn, "2026-11-18T10:00:00+00:00", "edit_draft", before={"summary": "Invoice export"})
    add(
        client.conn,
        "2026-11-18T11:00:00+00:00",
        "chat_turn",
        detail="answered",
        actor="orchestrator:invoicebot",
    )
    add(client.conn, "2026-11-18T12:00:00+00:00", "unrelated", detail="nothing here")

    assert sorted(actions(client, q="INVOICE")) == [
        "chat_turn",
        "create_issue",
        "edit_draft",
    ]  # any case, any field
    assert actions(client, q="  ") == [
        "unrelated",
        "chat_turn",
        "edit_draft",
        "create_issue",
    ]  # blank means no search


def test_a_percent_or_underscore_in_the_search_is_just_text(client):
    add(client.conn, "2026-11-18T09:00:00+00:00", "a", detail="done 100% of it")
    add(client.conn, "2026-11-18T09:01:00+00:00", "b", detail="done 1000 of it")
    add(client.conn, "2026-11-18T09:02:00+00:00", "c", detail="snake_case name")
    add(client.conn, "2026-11-18T09:03:00+00:00", "d", detail="snakeXcase name")

    assert actions(client, q="100%") == ["a"]
    assert actions(client, q="snake_case") == ["c"]


def test_search_combines_with_the_filter_and_the_dates(client):
    add(client.conn, "2026-11-18T09:00:00+00:00", "chat_turn", detail="invoices?", mode="M1")
    add(client.conn, "2026-11-18T09:00:00+00:00", "start_run", detail="invoices", mode="M2")
    add(client.conn, "2026-11-25T09:00:00+00:00", "chat_turn", detail="invoices again", mode="M1")

    assert actions(client, filter="advice_only", q="invoices", to="2026-11-20T00:00:00+00:00") == [
        "chat_turn"
    ]


def test_a_search_is_not_sql(client):
    add(client.conn, "2026-11-18T09:00:00+00:00", "a", detail="x")

    assert actions(client, q="'; DROP TABLE audit_log; --") == []
    assert actions(client) == ["a"]


def test_the_export_has_every_row_not_just_the_first_500(client):
    client.conn.execute(
        "INSERT INTO audit_log (actor, mode, action, outcome) SELECT 'human:reviewer', 'M2', 'bulk', 'ok' "
        "FROM generate_series(1, 650)"
    )
    client.conn.commit()

    response = client.get("/api/audit/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["time", "run", "actor", "mode", "action", "outcome", "detail", "before", "after"]
    assert len(rows) - 1 == 650
    assert len(client.get("/api/audit", params={"limit": 500}).json()["rows"]) == 500


def test_the_export_uses_the_same_filters_as_the_list(client):
    add(client.conn, "2026-11-18T09:00:00+00:00", "keep", detail="invoices")
    add(client.conn, "2026-11-18T09:00:00+00:00", "drop", detail="other")
    add(client.conn, "2026-12-30T09:00:00+00:00", "late", detail="invoices")

    text = client.get(
        "/api/audit/export.csv", params={"q": "invoices", "to": "2026-12-01T00:00:00+00:00"}
    ).text

    assert [r[4] for r in list(csv.reader(io.StringIO(text)))[1:]] == ["keep"]


@pytest.mark.parametrize("lead", ["=", "+", "-", "@"])
def test_the_export_defuses_cells_a_spreadsheet_would_run_as_a_formula(client, lead):
    add(client.conn, "2026-11-18T09:00:00+00:00", "a", detail=f'{lead}HYPERLINK("http://evil","x")')

    [_, row] = list(csv.reader(io.StringIO(client.get("/api/audit/export.csv").text)))

    assert (
        row[6] == f'\'{lead}HYPERLINK("http://evil","x")'
    )  # an apostrophe in front: it is text, not a formula


def test_the_export_keeps_commas_quotes_and_line_breaks_in_one_cell(client):
    add(client.conn, "2026-11-18T09:00:00+00:00", "a", detail='said "hi", then\nleft')

    [_, row] = list(csv.reader(io.StringIO(client.get("/api/audit/export.csv").text)))

    assert row[6] == 'said "hi", then\nleft'
