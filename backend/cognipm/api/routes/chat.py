"""The Co-Pilot chat (M1): read-only questions about the project.

The model behind it is offered only the gateway's two read tools, so it cannot propose or create anything
whatever it is asked. The conversation is kept in chat_sessions / chat_messages; this route replays it into
every turn."""

from __future__ import annotations

import sys
import traceback
import uuid

from fastapi import APIRouter, Depends, HTTPException

from cognipm.api.deps import get_conn, get_run_options
from cognipm.api.schemas import ChatBody, ChatResult
from cognipm.db.audit import log_audit
from cognipm.db.connection import Connection
from cognipm.orchestrator.chat import ChatError, run_chat_turn
from cognipm.orchestrator.mcp_bridge import agent_identity

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResult)
async def chat(
    body: ChatBody, conn: Connection = Depends(get_conn), options: dict = Depends(get_run_options)
) -> ChatResult:
    """One Co-Pilot turn. Leave `session_id` out to start a conversation; pass the returned one to continue it."""
    session_id = body.session_id
    if session_id is None:
        session_id = str(uuid.uuid4())
        conn.execute("INSERT INTO chat_sessions (id) VALUES (%s)", (session_id,))
        conn.commit()
    elif conn.execute("SELECT 1 FROM chat_sessions WHERE id = %s", (session_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="chat session not found")

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

    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, 'user', %s), (%s, 'agent', %s)",
        (session_id, body.message, session_id, answer),
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
    return ChatResult(session_id=session_id, answer=answer, tool_calls=tool_calls)
