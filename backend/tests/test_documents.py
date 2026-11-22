"""Saved documents: keeping notes to draft from again, and, above all, deleting them. A deleted document must be
gone, while the runs made from it keep working (they hold their own copy of the text) and the audit log never
holds a document's text."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cognipm.api.main import app
from tests.test_api import NOTES, build_api, start_p1


@pytest.fixture
def api(conn):
    api = build_api(conn)
    with TestClient(app) as client:
        api.client = client
        yield api
    app.dependency_overrides.clear()


SECRET = "Payroll migration moves to Q3, confidential"


def save(api, title="Sprint notes", text=SECRET, **extra):
    response = api.client.post("/api/documents", json={"title": title, "text": text, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_saved_document_can_be_listed_opened_renamed_and_deleted(api):
    doc = save(api, title="  Sprint notes  ", kind="requirements", filename="notes.md")

    assert doc["title"] == "Sprint notes" and doc["kind"] == "requirements" and doc["filename"] == "notes.md"
    assert doc["text"] == SECRET and doc["char_count"] == len(SECRET) and doc["used_in_runs"] == 0

    [listed] = api.client.get("/api/documents").json()
    assert listed["id"] == doc["id"] and "text" not in listed  # the list never carries the text

    assert api.client.get(f"/api/documents/{doc['id']}").json()["text"] == SECRET

    renamed = api.client.patch(f"/api/documents/{doc['id']}", json={"title": "Retro notes"}).json()
    assert renamed["title"] == "Retro notes"
    assert api.client.get(f"/api/documents/{doc['id']}").json()["text"] == SECRET  # renaming keeps the text

    assert api.client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert api.client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert api.client.get("/api/documents").json() == []
    assert (
        api.conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"] == 0
    )  # gone from the database


def test_newest_documents_come_first(api):
    save(api, title="first")
    save(api, title="second")

    assert [d["title"] for d in api.client.get("/api/documents").json()] == ["second", "first"]


@pytest.mark.parametrize(
    "body",
    [
        {"title": "   ", "text": "x"},  # a name made of spaces
        {"title": "ok", "text": ""},
        {"title": "ok", "text": "x" * 200_001},  # the same limit as a run's input
        {"title": "ok", "text": "x", "kind": "secret"},
        {"title": "x" * 201, "text": "x"},
        {"text": "x"},
    ],
)
def test_a_document_needs_a_title_some_text_and_a_known_kind(api, body):
    assert api.client.post("/api/documents", json=body).status_code == 422
    assert api.client.get("/api/documents").json() == []


def test_a_blank_text_made_of_spaces_is_refused(api):
    assert api.client.post("/api/documents", json={"title": "ok", "text": "  \n "}).status_code == 422


def test_unknown_documents_are_404s(api):
    assert api.client.get("/api/documents/nope").status_code == 404
    assert api.client.patch("/api/documents/nope", json={"title": "x"}).status_code == 404
    assert api.client.delete("/api/documents/nope").status_code == 404


def test_a_run_started_from_a_document_is_counted_against_it(api):
    doc = save(api, text=NOTES)

    start_p1(api, document_id=doc["id"])
    start_p1(api, document_id=doc["id"])
    start_p1(api)  # drafted from pasted text: not counted

    assert api.client.get(f"/api/documents/{doc['id']}").json()["used_in_runs"] == 2


def test_a_run_cannot_be_started_from_a_document_that_does_not_exist(api):
    response = api.client.post("/api/runs", json={"task": "p1", "input_text": NOTES, "document_id": "nope"})

    assert response.status_code == 422 and "no longer exists" in response.json()["detail"]
    assert api.client.get("/api/runs").json()["waiting"] == []  # nothing was started


def test_deleting_a_document_removes_its_text_but_leaves_the_runs_made_from_it_working(api):
    doc = save(api, text=NOTES)
    detail = start_p1(api, document_id=doc["id"])
    run_id = detail["run"]["id"]

    api.client.delete(f"/api/documents/{doc['id']}")

    after = api.client.get(f"/api/runs/{run_id}").json()
    assert after["input_text"] == NOTES  # the run's own copy: the review screen and a rerun still work
    assert len(after["drafts"]) == 2
    row = api.conn.execute("SELECT document_id FROM runs WHERE id = %s", (run_id,)).fetchone()
    assert row["document_id"] is None  # the link is simply empty now


def test_the_audit_log_records_what_happened_to_a_document_but_never_its_text(api):
    doc = save(api)
    api.client.patch(f"/api/documents/{doc['id']}", json={"title": "Renamed"})
    api.client.delete(f"/api/documents/{doc['id']}")

    log = api.client.get("/api/audit").json()["rows"]

    assert {"save_document", "rename_document", "delete_document"} <= {r["action"] for r in log}
    assert SECRET not in str(log) and "Payroll" not in str(log)


def test_delete_all_removes_every_document_and_says_how_many(api):
    save(api, title="a")
    save(api, title="b")

    assert api.client.delete("/api/documents").json() == {"deleted": 2}
    assert api.client.get("/api/documents").json() == []
    assert api.client.delete("/api/documents").json() == {"deleted": 0}


def test_clearing_stored_inputs_keeps_runs_that_are_still_being_reviewed(api):
    finished = start_p1(api)
    api.client.post(f"/api/runs/{finished['run']['id']}/reject", json={"comment": "no"})
    waiting = start_p1(api)

    assert api.client.post("/api/settings/clear-run-inputs").json() == {"deleted": 1}

    done = api.client.get(f"/api/runs/{finished['run']['id']}").json()
    assert (
        done["input_text"] is None and len(done["drafts"]) == 2
    )  # the text is gone; the drafts and decision stay
    assert api.client.get(f"/api/runs/{waiting['run']['id']}").json()["input_text"] == NOTES
    assert "clear_run_inputs" in {r["action"] for r in api.client.get("/api/audit").json()["rows"]}
