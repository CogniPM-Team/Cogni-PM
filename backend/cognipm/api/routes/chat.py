"""The Co-Pilot chat (M1): read-only questions about the project, kept as sessions the user can return to.

The model behind it is offered only the gateway's two read tools, so it cannot propose or create anything
whatever it is asked. Each conversation is a session with a title and an optional folder; this route replays
a session's messages into every turn, and the rest of the file is the housekeeping (list, open, rename, move,
delete, folders)."""

from __future__ import annotations

import re
import sys
import traceback
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from cognipm.api.deps import current_user, get_conn, get_run_options
from cognipm.api.schemas import (
    ChatBody,
    ChatFolderOut,
    ChatMessageOut,
    ChatResult,
    ChatSessionDetail,
    ChatSessionList,
    ChatSessionOut,
    FolderBody,
    SessionPatch,
)
from cognipm.auth import User
from cognipm.db.audit import log_audit
from cognipm.db.connection import Connection
from cognipm.orchestrator.chat import ChatError, run_chat_turn
from cognipm.orchestrator.mcp_bridge import agent_identity

router = APIRouter(tags=["chat"])

TITLE_LENGTH = 60

_SESSION_COLUMNS = (
    "s.id, s.title, s.folder_id, s.created_at, s.updated_at, "
    "(SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count"
)


def title_from(question: str) -> str:
    """A chat's first title: the opening of the first question, on one line."""
    text = re.sub(r"\s+", " ", question).strip()
    return text if len(text) <= TITLE_LENGTH else text[: TITLE_LENGTH - 1].rstrip() + "…"


def _session(conn: Connection, session_id: str) -> ChatSessionOut:
    row = conn.execute(
        f"SELECT {_SESSION_COLUMNS} FROM chat_sessions s WHERE s.id = %s", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return ChatSessionOut(**row)


def _require_folder(conn: Connection, folder_id: str) -> None:
    if conn.execute("SELECT 1 FROM chat_folders WHERE id = %s", (folder_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="folder not found")


# ---------- asking ----------


@router.post("/chat", response_model=ChatResult)
async def chat(
    body: ChatBody, conn: Connection = Depends(get_conn), options: dict = Depends(get_run_options)
) -> ChatResult:
    """One Co-Pilot turn. Leave `session_id` out to start a conversation (it is created, and titled from this
    question, once the answer is ready); pass the returned one to continue it."""
    session_id = body.session_id
    history: list[dict] = []
    if session_id is not None:
        _session(conn, session_id)  # 404 if it is not there
        history = conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY id", (session_id,)
        ).fetchall()

    try:
        answer, tool_calls = await run_chat_turn(history=history, message=body.message, **options["chat"])
    except ChatError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (Exception, BaseExceptionGroup) as exc:  # anyio wraps stdio failures in a group
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(
            status_code=502, detail="The assistant is unavailable right now. Try again shortly."
        ) from exc

    if session_id is None:  # only now, so a failed first turn leaves no empty chat behind
        session_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO chat_sessions (id, title) VALUES (%s, %s)", (session_id, title_from(body.message))
        )
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content, reads) VALUES (%s, 'user', %s, NULL), (%s, 'agent', %s, %s)",
        (session_id, body.message, session_id, answer, len(tool_calls)),
    )
    conn.execute(
        "UPDATE chat_sessions SET updated_at = now(), title = COALESCE(title, %s) WHERE id = %s",
        (title_from(body.message), session_id),
    )
    conn.commit()
    log_audit(  # what was asked stays out of the log: the conversation itself is in chat_messages
        conn,
        run_id=None,
        actor=agent_identity(suffix="chat"),
        mode="M1",
        action="chat_turn",
        outcome="answered",
        detail=f"session {session_id}; {len(tool_calls)} read(s)",
    )
    return ChatResult(
        session_id=session_id,
        title=_session(conn, session_id).title or "",
        answer=answer,
        tool_calls=tool_calls,
    )


# ---------- the list of chats ----------


@router.get("/chat/sessions", response_model=ChatSessionList)
def list_sessions(conn: Connection = Depends(get_conn)) -> ChatSessionList:
    """Every chat, most recently used first, and every folder."""
    folders = conn.execute("SELECT id, name FROM chat_folders ORDER BY lower(name), created_at").fetchall()
    sessions = conn.execute(
        f"SELECT {_SESSION_COLUMNS} FROM chat_sessions s ORDER BY s.updated_at DESC, s.id"
    ).fetchall()
    return ChatSessionList(
        folders=[ChatFolderOut(**f) for f in folders], sessions=[ChatSessionOut(**s) for s in sessions]
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetail)
def open_session(session_id: str, conn: Connection = Depends(get_conn)) -> ChatSessionDetail:
    session = _session(conn, session_id)
    rows = conn.execute(
        "SELECT id, role, content, reads, created_at FROM chat_messages WHERE session_id = %s ORDER BY id",
        (session_id,),
    ).fetchall()
    return ChatSessionDetail(session=session, messages=[ChatMessageOut(**r) for r in rows])


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionOut)
def update_session(
    session_id: str, body: SessionPatch, conn: Connection = Depends(get_conn)
) -> ChatSessionOut:
    """Rename a chat, or move it into a folder (`folder_id` null takes it out of its folder). Only what is sent
    changes; renaming does not move a chat up the list."""
    _session(conn, session_id)
    sent = body.model_fields_set
    if not sent & {"title", "folder_id"}:
        raise HTTPException(status_code=422, detail="nothing to change")
    if "title" in sent:
        if body.title is None or not body.title.strip():
            raise HTTPException(status_code=422, detail="a chat needs a name")
        conn.execute("UPDATE chat_sessions SET title = %s WHERE id = %s", (body.title.strip(), session_id))
    if "folder_id" in sent:
        if body.folder_id is not None:
            _require_folder(conn, body.folder_id)
        conn.execute("UPDATE chat_sessions SET folder_id = %s WHERE id = %s", (body.folder_id, session_id))
    conn.commit()
    return _session(conn, session_id)


@router.delete("/chat/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str, conn: Connection = Depends(get_conn), user: User = Depends(current_user)
) -> Response:
    """Delete a chat and every message in it. This cannot be undone."""
    _session(conn, session_id)
    conn.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
    conn.commit()
    log_audit(
        conn,
        run_id=None,
        actor=user.actor,
        mode="M1",
        action="delete_chat",
        outcome="deleted",
        detail=f"session {session_id}",
    )
    return Response(status_code=204)


# ---------- folders ----------


@router.post("/chat/folders", response_model=ChatFolderOut, status_code=201)
def create_folder(body: FolderBody, conn: Connection = Depends(get_conn)) -> ChatFolderOut:
    folder_id = str(uuid.uuid4())
    conn.execute("INSERT INTO chat_folders (id, name) VALUES (%s, %s)", (folder_id, body.name.strip()))
    conn.commit()
    return ChatFolderOut(id=folder_id, name=body.name.strip())


@router.patch("/chat/folders/{folder_id}", response_model=ChatFolderOut)
def rename_folder(folder_id: str, body: FolderBody, conn: Connection = Depends(get_conn)) -> ChatFolderOut:
    _require_folder(conn, folder_id)
    conn.execute("UPDATE chat_folders SET name = %s WHERE id = %s", (body.name.strip(), folder_id))
    conn.commit()
    return ChatFolderOut(id=folder_id, name=body.name.strip())


@router.delete("/chat/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, conn: Connection = Depends(get_conn)) -> Response:
    """Delete a folder. Its chats are kept and move out of the folder."""
    _require_folder(conn, folder_id)
    conn.execute("DELETE FROM chat_folders WHERE id = %s", (folder_id,))  # the chats' folder_id becomes NULL
    conn.commit()
    return Response(status_code=204)
