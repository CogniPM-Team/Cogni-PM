-- Pause, stop, cancel, and the agent asking a question.
--
-- A run used to be running, then awaiting_review, then decided (or failed). Now a person can also hold it, end it early,
-- or be asked something by the agent:
--   paused                   held at a step boundary; Resume continues it
--   waiting_for_information  the agent asked a question and is waiting for an answer
--   stopped                  ended early on request; whatever was staged stays as it is
--   cancelled                ended early on request; anything staged is discarded
--
-- A person asks by setting `control`; the running task reads it between steps (never in the middle of one) and does it,
-- so a model call or a Jira request in flight always finishes cleanly. Nothing here is a Jira write.

ALTER TABLE runs DROP CONSTRAINT runs_status_check;
ALTER TABLE runs ADD CONSTRAINT runs_status_check CHECK (
  status IN ('running', 'paused', 'waiting_for_information', 'awaiting_review', 'applied', 'rejected', 'stopped', 'cancelled', 'failed')
);

ALTER TABLE runs
  ADD COLUMN control  TEXT CHECK (control IN ('pause', 'stop', 'cancel')),  -- what a person asked for; cleared when done
  ADD COLUMN question TEXT;                                                 -- what the agent asked, while it waits
