-- What the review screen and a rerun need to know about a run.
--
-- input_text is the passage the drafts were made from (pasted notes, or the story's text as fetched from
-- Jira), kept so the PM can see each cited quote in context and so a rerun starts from the same input.
-- It is project data: apply the retention policy in docs/phases.md (H4) before real users.
-- ready_at is when the drafts became reviewable; decided_at - ready_at is the study's "time to decision".

ALTER TABLE runs
  ADD COLUMN input_text   TEXT,
  ADD COLUMN instructions TEXT,
  ADD COLUMN story_key    TEXT,
  ADD COLUMN ready_at     TIMESTAMPTZ;

-- A model call that was rate-limited and tried again is worth showing in the step trace.
ALTER TABLE run_steps DROP CONSTRAINT run_steps_state_check;
ALTER TABLE run_steps
  ADD CONSTRAINT run_steps_state_check CHECK (state IN ('start', 'end', 'error', 'retry'));
