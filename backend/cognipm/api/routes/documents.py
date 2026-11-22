"""Saved input documents: notes or requirements kept so they can be drafted from again, and deleted.

Deleting a document removes its text for good. Runs made from it keep their own copy of the text they used (that
is what the review screen and a rerun read), so the review history and the audit trail stay whole.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from cognipm.api.deps import current_user, get_conn
from cognipm.api.schemas import Deleted, DocumentIn, DocumentOut, DocumentRename, DocumentSummary
from cognipm.auth import User
from cognipm.db.audit import log_audit
from cognipm.db.connection import Connection

router = APIRouter(tags=["documents"])

SUMMARY = """
SELECT d.id, d.title, d.kind, d.filename, length(d.text) AS char_count, d.created_at, d.updated_at,
       (SELECT COUNT(*) FROM runs r WHERE r.document_id = d.id) AS used_in_runs
FROM documents d
"""


def _get(conn: Connection, document_id: str) -> dict:
    row = conn.execute(SUMMARY + " WHERE d.id = %s", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such document")
    return row


def _log(conn: Connection, user: User, action: str, detail: str, **extra: dict) -> None:
    """The audit log records that a document was saved, renamed or deleted, and its title: never its text."""
    log_audit(
        conn, run_id=None, actor=user.actor, mode=None, action=action, outcome="ok", detail=detail, **extra
    )


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(conn: Connection = Depends(get_conn)) -> list[DocumentSummary]:
    """Newest first. The text is not included: open one document to read it."""
    return [DocumentSummary(**r) for r in conn.execute(SUMMARY + " ORDER BY d.created_at DESC").fetchall()]


@router.post("/documents", response_model=DocumentOut, status_code=201)
def save_document(
    body: DocumentIn, conn: Connection = Depends(get_conn), user: User = Depends(current_user)
) -> DocumentOut:
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="a document needs some text")
    document_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO documents (id, title, kind, filename, text) VALUES (%s, %s, %s, %s, %s)",
        (document_id, body.title, body.kind, body.filename, body.text),
    )
    conn.commit()
    _log(conn, user, "save_document", f"saved {body.title!r} ({len(body.text):,} characters)")
    return DocumentOut(**_get(conn, document_id), text=body.text)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def open_document(document_id: str, conn: Connection = Depends(get_conn)) -> DocumentOut:
    row = _get(conn, document_id)
    text = conn.execute("SELECT text FROM documents WHERE id = %s", (document_id,)).fetchone()["text"]
    return DocumentOut(**row, text=text)


@router.patch("/documents/{document_id}", response_model=DocumentSummary)
def rename_document(
    document_id: str,
    body: DocumentRename,
    conn: Connection = Depends(get_conn),
    user: User = Depends(current_user),
) -> DocumentSummary:
    old = _get(conn, document_id)
    conn.execute(
        "UPDATE documents SET title = %s, updated_at = now() WHERE id = %s", (body.title, document_id)
    )
    conn.commit()
    _log(
        conn,
        user,
        "rename_document",
        f"renamed {old['title']!r} to {body.title!r}",
        before={"title": old["title"]},
        after={"title": body.title},
    )
    return DocumentSummary(**_get(conn, document_id))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str, conn: Connection = Depends(get_conn), user: User = Depends(current_user)
) -> Response:
    old = _get(conn, document_id)
    conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))  # runs' links become empty (SET NULL)
    conn.commit()
    _log(
        conn,
        user,
        "delete_document",
        f"deleted {old['title']!r}; it was used in {old['used_in_runs']} run(s)",
    )
    return Response(status_code=204)


@router.delete("/documents", response_model=Deleted)
def delete_all_documents(conn: Connection = Depends(get_conn), user: User = Depends(current_user)) -> Deleted:
    """Every saved document, for the Settings privacy buttons. Runs keep their own copy of what they used."""
    count = conn.execute(
        "WITH gone AS (DELETE FROM documents RETURNING 1) SELECT COUNT(*) AS n FROM gone"
    ).fetchone()["n"]
    conn.commit()
    _log(conn, user, "delete_documents", f"deleted all saved documents ({count})")
    return Deleted(deleted=count)
