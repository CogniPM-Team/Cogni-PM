-- What an orchestrator run did, step by step (model calls, gateway tool calls, source
-- checks), so the console can stream it and the activity log can replay it after a
-- restart. The prototype kept this in an in-memory dict and lost it on restart.

CREATE TABLE run_steps (
  id      BIGSERIAL PRIMARY KEY,
  run_id  TEXT NOT NULL REFERENCES runs (id),
  ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  phase   TEXT NOT NULL,                              -- 'analysing' | 'generating' | 'verifying' | 'staging'
  state   TEXT NOT NULL CHECK (state IN ('start', 'end', 'error')),
  tool    TEXT,                                       -- the gateway tool, for tool steps
  detail  JSONB
);
CREATE INDEX idx_run_steps_run_id ON run_steps (run_id, id);
