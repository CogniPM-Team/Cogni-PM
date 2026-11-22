"""Sign in, sign out, who am I, and (for a PM) who else has an account.

This router is the one that does NOT sit behind the sign-in rule in main.py: signing in has to be possible when
nobody is signed in. Everything else the API serves does.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from cognipm.api.deps import get_conn, get_user, require_pm
from cognipm.api.schemas import LoginBody, UserCreate, UserOut, UserPatch
from cognipm.auth import (
    COOKIE_NAME,
    SESSION_HOURS,
    User,
    authenticate,
    create_user,
    end_all_sessions,
    end_session,
    hash_password,
    password_problem,
    start_session,
)
from cognipm.db.audit import log_audit
from cognipm.db.connection import Connection

router = APIRouter(tags=["auth"])


def _out(row: dict) -> UserOut:
    return UserOut(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        disabled=row["disabled_at"] is not None,
    )


def _signed_in(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name, role=user.role, disabled=False
    )


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginBody, response: Response, conn: Connection = Depends(get_conn)) -> UserOut:
    user = authenticate(conn, body.email, body.password)
    if user is None:
        # The same words whether the email or the password was wrong, so this cannot be used to find who has an account.
        log_audit(
            conn,
            run_id=None,
            actor="anonymous",
            mode=None,
            action="login",
            outcome="refused",
            detail=f"failed sign-in for {body.email[:100]}",
        )
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    token = start_session(conn, user.id)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,  # scripts in the page cannot read it
        samesite="lax",  # another website cannot make the browser send it with a change
        secure=os.environ.get("COGNIPM_COOKIE_SECURE") == "1",
        path="/",
    )
    log_audit(conn, run_id=None, actor=user.actor, mode=None, action="login", outcome="ok")
    return _signed_in(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, conn: Connection = Depends(get_conn)) -> Response:
    """Always succeeds, even with no valid session: the aim is only that this browser ends up signed out."""
    end_session(conn, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_user)) -> UserOut:
    return _signed_in(user)


# ---------- people (PM only) ----------


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_pm), conn: Connection = Depends(get_conn)) -> list[UserOut]:
    return [_out(r) for r in conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()]


@router.post("/users", response_model=UserOut, status_code=201)
def add_user(
    body: UserCreate, pm: User = Depends(require_pm), conn: Connection = Depends(get_conn)
) -> UserOut:
    try:
        created = create_user(
            conn, email=body.email, display_name=body.display_name, role=body.role, password=body.password
        )
    except ValueError as problem:
        raise HTTPException(status_code=409, detail=str(problem)) from problem
    log_audit(
        conn,
        run_id=None,
        actor=pm.actor,
        mode=None,
        action="create_user",
        outcome="ok",
        detail=f"added {created.email} as {created.role}",
    )
    return _signed_in(created)


def _active_pms(conn: Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'pm' AND disabled_at IS NULL"
    ).fetchone()["n"]


@router.patch("/users/{user_id}", response_model=UserOut)
def change_user(
    user_id: str, body: UserPatch, pm: User = Depends(require_pm), conn: Connection = Depends(get_conn)
) -> UserOut:
    target = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="no such person")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="nothing to change")

    # Someone must always be able to approve and manage people: refuse the change that would leave nobody.
    removes_a_pm = (
        target["role"] == "pm"
        and target["disabled_at"] is None
        and (changes.get("role") == "developer" or changes.get("disabled") is True)
    )
    if removes_a_pm and _active_pms(conn) <= 1:
        raise HTTPException(status_code=409, detail="At least one active PM must remain.")
    if "password" in changes and (problem := password_problem(changes["password"])):
        raise HTTPException(status_code=422, detail=problem)

    if "display_name" in changes:
        conn.execute(
            "UPDATE users SET display_name = %s WHERE id = %s", (changes["display_name"].strip(), user_id)
        )
    if "role" in changes:
        conn.execute("UPDATE users SET role = %s WHERE id = %s", (changes["role"], user_id))
    if "disabled" in changes:
        conn.execute(
            "UPDATE users SET disabled_at = CASE WHEN %s THEN now() ELSE NULL END WHERE id = %s",
            (changes["disabled"], user_id),
        )
    if "password" in changes:
        conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(changes["password"]), user_id)
        )
    conn.commit()
    # A new password, a lower role or a disabled account must take effect now, not when the old sign-in runs out.
    if {"password", "role", "disabled"} & changes.keys():
        end_all_sessions(conn, user_id)
    log_audit(
        conn,
        run_id=None,
        actor=pm.actor,
        mode=None,
        action="update_user",
        outcome="ok",
        detail=f"changed {sorted(changes)} for {target['email']}",  # the fields, never a password
    )
    return _out(conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone())
