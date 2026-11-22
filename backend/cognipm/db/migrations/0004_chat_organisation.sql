-- Co-Pilot chats the user can come back to: a title, an optional folder, and when they were last used.
--
-- Deleting a chat deletes its messages for real (the code removes them), which is also how a user gets their
-- own words out of the system. The activity log keeps only a content-free "answered a question" row.

CREATE TABLE chat_folders (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE chat_sessions
  ADD COLUMN title      TEXT,
  ADD COLUMN folder_id  TEXT REFERENCES chat_folders (id) ON DELETE SET NULL,  -- deleting a folder keeps its chats
  ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- How many times the agent read Jira to answer, so a reopened chat still shows "Read Jira 3 times".
ALTER TABLE chat_messages ADD COLUMN reads INTEGER;

CREATE INDEX idx_chat_sessions_updated_at ON chat_sessions (updated_at DESC);
