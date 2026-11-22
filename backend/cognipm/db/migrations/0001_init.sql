-- Core oversight schema: runs, the staging table for drafts, approval tokens,
-- the audit trail and the M1 chat. Based on the prototype's migrations, but
-- keyed on M1/M2/M3 and redesigned around drafts that CREATE Jira issues
-- (P1 backlog drafting, P2 task breakdown) instead of editing one field.

CREATE TABLE runs (
  id             TEXT PRIMARY KEY,                    -- uuid string
  mode           TEXT NOT NULL CHECK (mode IN ('M2', 'M3')),  -- M1 never starts a run
  task_type      TEXT NOT NULL,                       -- 'p1' | 'p2' (later: automation task types)
  agent          TEXT NOT NULL,                       -- who drove the gateway
  scope          TEXT NOT NULL,                       -- what the run was asked to work on
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  status         TEXT NOT NULL CHECK (status IN ('running', 'awaiting_review', 'applied', 'rejected', 'failed')),
  comment        TEXT,                                -- the PM's note on reject or rerun
  -- what the study measures
  model          TEXT,
  input_tokens   INTEGER,
  output_tokens  INTEGER,
  rerun_of       TEXT REFERENCES runs (id),           -- reruns chain back to the run they replace
  decided_at     TIMESTAMPTZ                          -- when the PM approved or rejected
);

CREATE TABLE staged_changes (
  id                  TEXT PRIMARY KEY,
  run_id              TEXT NOT NULL REFERENCES runs (id),
  kind                TEXT NOT NULL CHECK (kind IN ('backlog_item', 'task', 'subtask')),
  -- Always exactly what the agent proposed: summary, description,
  -- acceptance_criteria, issue_type, labels, and parent_key when the parent
  -- already exists in Jira.
  payload             JSONB NOT NULL,
  edited_payload      JSONB,                          -- the PM's version, when they changed anything
  parent_change_id    TEXT REFERENCES staged_changes (id),  -- parent is another draft in the same run
  sources             JSONB NOT NULL,                 -- input passages this draft cites (at least one)
  reasoning           TEXT NOT NULL,
  assumptions         TEXT NOT NULL DEFAULT 'NA',
  action_class        TEXT NOT NULL DEFAULT 'structural' CHECK (action_class IN ('read', 'internal', 'structural', 'external')),
  status              TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'applied', 'failed', 'rejected')),
  created_issue_key   TEXT,
  error               TEXT,                           -- why the Jira create failed, when status = 'failed'
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  applied_at          TIMESTAMPTZ,
  CHECK (jsonb_typeof(sources) = 'array' AND jsonb_array_length(sources) >= 1)
);
CREATE INDEX idx_staged_changes_run_id ON staged_changes (run_id);

CREATE TABLE approval_tokens (
  token        TEXT PRIMARY KEY,
  run_id       TEXT NOT NULL REFERENCES runs (id),
  issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  consumed_at  TIMESTAMPTZ
);
CREATE INDEX idx_approval_tokens_run_id ON approval_tokens (run_id);

CREATE TABLE audit_log (
  id       BIGSERIAL PRIMARY KEY,
  ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id   TEXT,
  actor    TEXT NOT NULL,                             -- 'agent:...' | 'human:reviewer' | 'gateway'
  mode     TEXT,
  action   TEXT NOT NULL,
  outcome  TEXT NOT NULL,
  detail   TEXT,
  before   JSONB,                                     -- the value an edit or change replaced
  after    JSONB                                      -- the value it was replaced with
);
CREATE INDEX idx_audit_log_run_id ON audit_log (run_id);

-- audit_log is append-only. The prototype stated this as a convention; here
-- the database enforces it.
CREATE FUNCTION audit_log_reject_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update_delete
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_reject_change();

CREATE TRIGGER audit_log_no_truncate
  BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_change();

-- M1 (Co-Pilot) conversational surface. Never tied to a run: M1 has no start_run.
CREATE TABLE chat_sessions (
  id          TEXT PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
  id          BIGSERIAL PRIMARY KEY,
  session_id  TEXT NOT NULL REFERENCES chat_sessions (id),
  role        TEXT NOT NULL CHECK (role IN ('user', 'agent')),
  content     TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_messages_session_id ON chat_messages (session_id);
