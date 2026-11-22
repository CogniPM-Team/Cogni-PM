-- People who can sign in, and their sessions.
--
-- Two roles: a PM can do everything (start tasks, approve, reject, edit, change settings, manage people); a developer
-- can only look (every list, run, log and number, but nothing that changes anything). The role is checked on the
-- server for every request, so hiding a button in the website is a courtesy and never the control.
--
-- Passwords are stored only as a salted scrypt hash. A session is a random token held in an HttpOnly cookie; the
-- database keeps only the token's SHA-256, so a copy of this table cannot be used to sign in.
--
-- The audit log keeps naming people as "human:<users.id>", so a decision stays attributed to the same person if their
-- name changes. Rows written before sign-in existed say "human:reviewer" and are shown as such.

CREATE TABLE users (
  id             TEXT PRIMARY KEY,                       -- uuid string
  email          TEXT NOT NULL,
  display_name   TEXT NOT NULL,
  role           TEXT NOT NULL CHECK (role IN ('pm', 'developer')),
  password_hash  TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  disabled_at    TIMESTAMPTZ                             -- a disabled person cannot sign in; their history stays
);
-- One account per email address, whatever its capitalisation.
CREATE UNIQUE INDEX idx_users_email ON users (lower(email));

CREATE TABLE sessions (
  token_hash    TEXT PRIMARY KEY,                        -- sha256 of the cookie value
  user_id       TEXT NOT NULL REFERENCES users (id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user_id ON sessions (user_id);
