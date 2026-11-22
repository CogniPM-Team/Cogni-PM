-- Chats made before they had titles and folders: name each after its first question (the same rule the API
-- uses for new chats), put it in the order it was last used, and drop the empty ones.
--
-- An empty chat is what a first question that failed used to leave behind (the chat was created before the
-- answer was ready). It holds no messages, so removing it loses nothing.

UPDATE chat_sessions s
SET title = CASE
      WHEN length(t.question) <= 60 THEN t.question
      ELSE rtrim(left(t.question, 59)) || '…'
    END,
    updated_at = t.last_message_at
FROM (
  SELECT session_id,
         regexp_replace(trim((array_agg(content ORDER BY id) FILTER (WHERE role = 'user'))[1]), '\s+', ' ', 'g') AS question,
         max(created_at) AS last_message_at
  FROM chat_messages
  GROUP BY session_id
) t
WHERE t.session_id = s.id AND s.title IS NULL AND t.question IS NOT NULL;

DELETE FROM chat_sessions s
WHERE NOT EXISTS (SELECT 1 FROM chat_messages m WHERE m.session_id = s.id);
