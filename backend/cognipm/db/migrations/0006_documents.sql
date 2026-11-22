-- Saved input documents: meeting notes or requirements a person wants to draft from more than once.
--
-- A document is the PM's own text, kept so it can be reused and deleted. A run never depends on it: runs.input_text
-- (migration 0003) already holds the exact text each run used, so deleting a document removes the document and
-- leaves every run and the audit trail intact (the link just becomes empty). Like input_text, this is project
-- data: see the retention notes in docs/phases.md (H4).

CREATE TABLE documents (
  id          TEXT PRIMARY KEY,                       -- uuid string
  title       TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'notes' CHECK (kind IN ('notes', 'requirements', 'other')),
  filename    TEXT,                                   -- the file it was loaded from, when it was
  text        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which document a run was started from, so a document can say "used in 3 runs".
ALTER TABLE runs
  ADD COLUMN document_id TEXT REFERENCES documents (id) ON DELETE SET NULL;
CREATE INDEX idx_runs_document_id ON runs (document_id);
