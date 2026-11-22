"""Who is asking: accounts, passwords and sessions.

No outside library: passwords use scrypt from the standard library, and a session is a random token in an HttpOnly
cookie whose SHA-256 is all the database keeps.

THE LIMITS, so nobody is surprised later:
- There is no limit on sign-in attempts yet (a research prototype with a handful of accounts). Put the API behind
  something that rate-limits before exposing it to the open internet.
- Cookies are SameSite=Lax, which stops another website from making your browser change things. Set
  COGNIPM_COOKIE_SECURE=1 when the site is served over https.
- Jira writes still come from one shared token. The approving person is on record in the audit log and in the Jira
  comment, but Jira itself sees the shared account (per-person OAuth is a later decision: docs/phases.md, H3).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from cognipm.db.connection import Connection

Role = Literal["pm", "developer"]
COOKIE_NAME = "cognipm_session"
SESSION_HOURS = 12
MIN_PASSWORD_LENGTH = 10

# scrypt cost: about 50 ms and 16 MB here, which is cheap for a person signing in and costly for a thief with a copy
# of the table. Stored with each hash, so raising it later still verifies the old ones.
_N, _R, _P = 2**14, 8, 1


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    role: Role

    @property
    def actor(self) -> str:
        """How the audit log names this person: by id, so a rename never rewrites who did what."""
        return f"human:{self.id}"

    @property
    def is_pm(self) -> bool:
        return self.role == "pm"


# ---------- passwords ----------


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A hash to check against when the email is unknown, so "no such account" takes as long as "wrong password".
_DECOY = hash_password(secrets.token_urlsafe(16))


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"A password needs at least {MIN_PASSWORD_LENGTH} characters."
    return None


# ---------- accounts ----------


def _row_to_user(row: dict) -> User:
    return User(id=row["id"], email=row["email"], display_name=row["display_name"], role=row["role"])


def create_user(conn: Connection, *, email: str, display_name: str, role: Role, password: str) -> User:
    """Add an account. Raises ValueError with a sentence for a person if the password is too short or the email is
    already taken."""
    if problem := password_problem(password):
        raise ValueError(problem)
    email = email.strip()
    taken = conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,)).fetchone()
    if taken:
        raise ValueError("Someone already has an account with that email address.")
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, email, display_name, role, password_hash) VALUES (%s, %s, %s, %s, %s)",
        (user_id, email, display_name.strip(), role, hash_password(password)),
    )
    conn.commit()
    return User(id=user_id, email=email, display_name=display_name.strip(), role=role)


def authenticate(conn: Connection, email: str, password: str) -> User | None:
    """The account, if the email and password are right and the account is not disabled. Takes the same time whether
    or not the email exists, and never says which part was wrong."""
    row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(%s)", (email.strip(),)).fetchone()
    ok = verify_password(password, row["password_hash"] if row else _DECOY)
    if row is None or not ok or row["disabled_at"] is not None:
        return None
    return _row_to_user(row)


def ensure_first_user(conn: Connection) -> None:
    """With no accounts at all, create the first PM from COGNIPM_ADMIN_EMAIL and COGNIPM_ADMIN_PASSWORD, so a new
    install can sign in. Does nothing once anyone exists, so changing these later never resets a password."""
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    email, password = os.environ.get("COGNIPM_ADMIN_EMAIL", ""), os.environ.get("COGNIPM_ADMIN_PASSWORD", "")
    if not email or not password:
        print(
            "There are no accounts yet. Set COGNIPM_ADMIN_EMAIL and COGNIPM_ADMIN_PASSWORD in .env and restart, or run "
            "scripts/create_user.py, so someone can sign in.",
            file=sys.stderr,
        )
        return
    try:
        create_user(
            conn,
            email=email,
            display_name=os.environ.get("COGNIPM_ADMIN_NAME") or email,
            role="pm",
            password=password,
        )
    except ValueError as problem:
        print(f"Could not create the first account: {problem}", file=sys.stderr)


# ---------- sessions ----------


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(conn: Connection, user_id: str) -> str:
    """A new sign-in. Returns the token for the cookie; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (_digest(token), user_id, datetime.now(UTC) + timedelta(hours=SESSION_HOURS)),
    )
    conn.commit()
    return token


def session_user(conn: Connection, token: str | None) -> User | None:
    """Who the cookie belongs to, or None when it is missing, unknown, expired, or the account is disabled."""
    if not token:
        return None
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = %s AND s.expires_at > now() AND u.disabled_at IS NULL",
        (_digest(token),),
    ).fetchone()
    return _row_to_user(row) if row else None


def end_session(conn: Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_digest(token),))
        conn.commit()


def end_all_sessions(conn: Connection, user_id: str) -> None:
    """Sign a person out everywhere: used when their password is reset or the account is disabled."""
    conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    conn.commit()
