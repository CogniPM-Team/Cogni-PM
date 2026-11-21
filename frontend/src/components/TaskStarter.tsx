import { useState } from 'react'
import { api } from '../api/client'
import type { StartedRun, StartRunBody, Story } from '../api/types'
import { useFetch } from '../api/useFetch'
import Spinner from './Spinner'

const MAX_INPUT = 200_000 // the API's limit

export type Task = 'p1' | 'p2'

interface Props {
  onStarted: (runId: string, task: Task) => void
}

/** The Super-Pilot (M2): hand the agent a task. It drafts; nothing is created in Jira until you approve. */
export default function TaskStarter({ onStarted }: Props) {
  const [task, setTask] = useState<Task>('p1')
  const [text, setText] = useState('')
  const [instructions, setInstructions] = useState('')
  const [storyKey, setStoryKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stories = useFetch<Story[]>(task === 'p2' ? '/api/stories' : null)

  const ready = task === 'p1' ? text.trim().length > 0 && text.length <= MAX_INPUT : storyKey !== null

  async function load(file: File | undefined) {
    if (!file) return
    const content = await file.text()
    if (content.length > MAX_INPUT) {
      setError(`That file is too long (${content.length.toLocaleString()} characters; the limit is ${MAX_INPUT.toLocaleString()}).`)
      return
    }
    setError(null)
    setText(content)
  }

  async function start() {
    const body: StartRunBody =
      task === 'p1'
        ? { task, input_text: text, instructions }
        : { task, story_key: storyKey, instructions }
    setBusy(true)
    setError(null)
    try {
      const started = await api.post<StartedRun>('/api/runs', body)
      onStarted(started.run_id, task)
      setText('')
      setInstructions('')
      setStoryKey(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Start a task" className="mode-M2">
      <p className="page-subtitle">
        Give the Super-Pilot a task. It drafts Jira issues for you to review; <strong>nothing is created in Jira
        until you approve it</strong> in Approvals.
      </p>

      <div className="task-choice" role="group" aria-label="Task">
        <button type="button" aria-pressed={task === 'p1'} onClick={() => setTask('p1')}>
          Draft backlog
          <small>Turn requirements or meeting notes into stories</small>
        </button>
        <button type="button" aria-pressed={task === 'p2'} onClick={() => setTask('p2')}>
          Break down a story
          <small>Split an existing story into sub-tasks</small>
        </button>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          void start()
        }}
      >
        {task === 'p1' ? (
          <>
            <label className="field">
              <span>Requirements or meeting notes</span>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                style={{ minHeight: '11rem' }}
                placeholder="Paste the text here. Use anonymised or synthetic text if the project is sensitive: it is sent to the AI model."
              />
            </label>
            <label className="field">
              <span>Or load a text file</span>
              <input type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(e) => void load(e.target.files?.[0])} />
            </label>
          </>
        ) : (
          <fieldset className="fieldset" style={{ border: 'none', padding: 0, margin: '0 0 12px' }}>
            <legend style={{ fontWeight: 500, marginBottom: 6 }}>Which story?</legend>
            {stories.loading && <p className="muted">Loading stories...</p>}
            {stories.error && <p className="error">Could not load stories: {stories.error.message}</p>}
            {stories.data?.length === 0 && <p className="empty">There are no open stories in the project.</p>}
            <div className="story-list">
              {stories.data?.map((story) => (
                <label key={story.key} className="story-option">
                  <input
                    type="radio"
                    name="story"
                    checked={storyKey === story.key}
                    onChange={() => setStoryKey(story.key)}
                  />
                  <span className="mono">{story.key}</span>
                  <span>{story.summary}</span>
                </label>
              ))}
            </div>
            <p className="meta">Its title and description are sent to the AI model.</p>
          </fieldset>
        )}

        <label className="field">
          <span>Anything the agent should know (optional)</span>
          <input type="text" value={instructions} onChange={(e) => setInstructions(e.target.value)} maxLength={4000} />
        </label>

        {error && <p className="error">{error}</p>}
        <button type="submit" className="primary" disabled={!ready || busy}>
          {busy && <Spinner />}
          {busy ? 'Starting...' : 'Start the task'}
        </button>
      </form>
    </section>
  )
}
