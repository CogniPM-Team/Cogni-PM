import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../lib/auth'
import type { DocumentSummary, SavedDocument, StartedRun, StartRunBody, Story } from '../api/types'
import { useFetch } from '../api/useFetch'
import { notifyRunsChanged } from '../lib/chatEvents'
import FileButton from './FileButton'
import Spinner from './Spinner'

const MAX_INPUT = 200_000 // the API's limit

export type Task = 'p1' | 'p2'

interface Props {
  /** Which task is selected when the form first appears (Home's "Break down a story" button sets it). */
  initialTask?: Task
  /** A saved document to start from (Library's "Draft a backlog from this" sets it): its text fills the form. */
  initialDocumentId?: string | null
  onStarted: (runId: string, task: Task) => void
}

/** The Super-Pilot (M2): hand the agent a task. It drafts; nothing is created in Jira until you approve. */
export default function TaskStarter({ initialTask = 'p1', initialDocumentId = null, onStarted }: Props) {
  const { canChange } = useAuth()
  const [task, setTask] = useState<Task>(initialTask)
  const [text, setText] = useState('')
  const [instructions, setInstructions] = useState('')
  const [storyKey, setStoryKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stories = useFetch<Story[]>(task === 'p2' ? '/api/stories' : null)
  const documents = useFetch<DocumentSummary[]>(task === 'p1' ? '/api/documents' : null)
  const [documentId, setDocumentId] = useState<string | null>(null) // the saved document the text came from
  const [saving, setSaving] = useState<{ title: string } | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null) // the file the text was loaded from

  async function loadDocument(id: string) {
    try {
      const doc = await api.get<SavedDocument>(`/api/documents/${id}`)
      setText(doc.text)
      setDocumentId(doc.id)
      setSaved(null)
      setError(null)
    } catch (e) {
      setError(`Could not open that document: ${(e as Error).message}`)
    }
  }

  // Arriving from the Library: fill the form from the chosen document, once it has loaded.
  const initial = useFetch<SavedDocument>(initialDocumentId ? `/api/documents/${initialDocumentId}` : null)
  const [appliedInitial, setAppliedInitial] = useState<string | null>(null)
  if (initial.data && appliedInitial !== initial.data.id) {
    setAppliedInitial(initial.data.id)
    setText(initial.data.text)
    setDocumentId(initial.data.id)
  }

  async function saveAsDocument() {
    if (!saving) return
    try {
      const doc = await api.post<SavedDocument>('/api/documents', { title: saving.title, text })
      setDocumentId(doc.id)
      setSaved(doc.title)
      setSaving(null)
      documents.reload()
    } catch (e) {
      setError((e as Error).message)
    }
  }

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
    setFileName(file.name)
    setDocumentId(null)
  }

  async function start() {
    const body: StartRunBody =
      task === 'p1'
        ? { task, input_text: text, instructions, document_id: documentId }
        : { task, story_key: storyKey, instructions }
    setBusy(true)
    setError(null)
    try {
      const started = await api.post<StartedRun>('/api/runs', body)
      onStarted(started.run_id, task)
      notifyRunsChanged()
      setText('')
      setFileName(null)
      setInstructions('')
      setStoryKey(null)
      setDocumentId(null)
      setSaved(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Start a task" className="mode-M2 card task-card">
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
        className="task-form"
        onSubmit={(event) => {
          event.preventDefault()
          void start()
        }}
      >
        {task === 'p1' ? (
          <>
            {documents.data && documents.data.length > 0 && (
              <label className="field">
                <span>Choose from your library</span>
                <select
                  value={documentId ?? ''}
                  onChange={(e) => (e.target.value ? void loadDocument(e.target.value) : setDocumentId(null))}
                >
                  <option value="">Pasted text</option>
                  {documents.data.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="field grow">
              <span>Requirements or meeting notes</span>
              <textarea
                value={text}
                onChange={(e) => {
                  setText(e.target.value)
                  if (e.target.value === '') {
                    setDocumentId(null)
                    setFileName(null)
                  }
                  setSaved(null)
                }}
                placeholder="Paste the text here. Use anonymised or synthetic text if the project is sensitive: it is sent to the AI model."
              />
            </label>
            <FileButton label="Load a text file" fileName={fileName} onFile={(file) => void load(file)} />
            {saved ? (
              <p className="meta" role="status">
                Saved to your library as {saved}.
              </p>
            ) : saving ? (
              <div className="inline-form">
                <input
                  type="text"
                  aria-label="Document title"
                  placeholder="Title"
                  value={saving.title}
                  maxLength={200}
                  onChange={(e) => setSaving({ title: e.target.value })}
                />
                <button type="button" className="small primary" disabled={!saving.title.trim()} onClick={() => void saveAsDocument()}>
                  Save
                </button>
                <button type="button" className="small" onClick={() => setSaving(null)}>
                  Cancel
                </button>
              </div>
            ) : (
              documentId === null &&
              text.trim() !== '' && (
                <button type="button" className="small" onClick={() => setSaving({ title: '' })}>
                  Save as document
                </button>
              )
            )}
          </>
        ) : (
          <fieldset className="fieldset grow">
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

        {initial.error && <p className="error">Could not open that saved document: {initial.error.message}</p>}
        {error && <p className="error">{error}</p>}
        <button type="submit" className="primary" disabled={!ready || busy || !canChange}
          title={canChange ? undefined : 'Only a PM can start a task'}>
          {busy && <Spinner />}
          {busy ? 'Starting...' : 'Start the task'}
        </button>
        <p className="fine-print">
          Nothing is created in Jira until you approve it. Drafts wait for you in <Link to="/approvals">Approvals</Link>.
        </p>
      </form>
    </section>
  )
}
