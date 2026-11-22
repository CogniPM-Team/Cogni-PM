import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DocumentSummary, SavedDocument } from '../api/types'
import { useFetch } from '../api/useFetch'
import { ago, formatTime, plural } from '../lib/format'
import FileButton from './FileButton'
import Icon from './Icon'
import { EmptyState, ErrorState } from './PageParts'

const MAX_TEXT = 200_000 // the API's limit
const KINDS = [
  { id: 'notes', label: 'Meeting notes' },
  { id: 'requirements', label: 'Requirements' },
  { id: 'other', label: 'Other' },
] as const

const kindLabel = (kind: string) => KINDS.find((k) => k.id === kind)?.label ?? kind

function Opened({ id }: { id: string }) {
  const { data, error, loading } = useFetch<SavedDocument>(`/api/documents/${id}`)
  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <p className="error">Could not open it: {error?.message}</p>
  return <pre className="doc-text">{data.text}</pre>
}

function AddForm({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<string>('notes')
  const [text, setText] = useState('')
  const [filename, setFilename] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function load(file: File | undefined) {
    if (!file) return
    const content = await file.text()
    if (content.length > MAX_TEXT) {
      setProblem(`That file is too long (${content.length.toLocaleString()} characters; the limit is ${MAX_TEXT.toLocaleString()}).`)
      return
    }
    setProblem(null)
    setText(content)
    setFilename(file.name)
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  async function save() {
    setBusy(true)
    setProblem(null)
    try {
      await api.post('/api/documents', { title, kind, text, filename })
      onSaved()
    } catch (e) {
      setProblem((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="card doc-form"
      onSubmit={(event) => {
        event.preventDefault()
        void save()
      }}
    >
      <label className="field">
        <span>Title</span>
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
      </label>
      <label className="field">
        <span>Kind</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Text</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the text, or load a file below." />
      </label>
      <FileButton label="Load a text file" fileName={filename} onFile={(file) => void load(file)} />
      <p className="meta">Saved text stays on this install. It is sent to the AI model only when you draft from it.</p>
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
      <div className="row-actions">
        <button type="submit" className="primary" disabled={busy || !title.trim() || !text.trim()}>
          {busy ? 'Saving...' : 'Save document'}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function Row({ doc, reload }: { doc: DocumentSummary; reload: () => void }) {
  const [open, setOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState(doc.title)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function run(work: () => Promise<unknown>) {
    setBusy(true)
    setProblem(null)
    try {
      await work()
      setRenaming(false)
      setConfirming(false)
      reload()
    } catch (e) {
      setProblem((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <tr>
        <td>
          {renaming ? (
            <form
              className="inline-form"
              onSubmit={(event) => {
                event.preventDefault()
                void run(() => api.patch(`/api/documents/${doc.id}`, { title }))
              }}
            >
              <input type="text" aria-label="New title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
              <button type="submit" className="small primary" disabled={busy || !title.trim()}>
                Save
              </button>
              <button type="button" className="small" onClick={() => setRenaming(false)}>
                Cancel
              </button>
            </form>
          ) : (
            <strong>{doc.title}</strong>
          )}
          {doc.filename && <div className="meta">{doc.filename}</div>}
        </td>
        <td>{kindLabel(doc.kind)}</td>
        <td>{doc.char_count.toLocaleString()} characters</td>
        <td>
          <time dateTime={doc.created_at} title={ago(doc.created_at)}>
            {formatTime(doc.created_at)}
          </time>
        </td>
        <td>{doc.used_in_runs === 0 ? 'Not used yet' : `Used in ${plural(doc.used_in_runs, 'run')}`}</td>
        <td className="doc-actions">
          <Link className="button-link small with-icon" to={`/console?mode=M2&document=${doc.id}`}>
            Draft a backlog from this
            <Icon name="arrow" size={14} />
          </Link>
          <button type="button" className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? 'Hide' : 'Open'}
          </button>
          <button type="button" className="link" onClick={() => setRenaming(true)}>
            Rename
          </button>
          <button type="button" className="link danger" onClick={() => setConfirming(true)}>
            Delete
          </button>
        </td>
      </tr>
      {confirming && (
        <tr>
          <td colSpan={6}>
            <div className="confirm" role="alertdialog" aria-label={`Delete ${doc.title}`}>
              <span>
                Delete <strong>{doc.title}</strong>? Its text is removed for good.
                {doc.used_in_runs > 0 && ' Runs made from it keep their own copy of what they used.'}
              </span>
              <button type="button" className="primary small" disabled={busy} onClick={() => void run(() => api.delete(`/api/documents/${doc.id}`))}>
                {busy ? 'Deleting...' : 'Yes, delete it'}
              </button>
              <button type="button" className="small" onClick={() => setConfirming(false)}>
                Cancel
              </button>
            </div>
          </td>
        </tr>
      )}
      {problem && (
        <tr>
          <td colSpan={6}>
            <p className="error" role="alert">
              {problem}
            </p>
          </td>
        </tr>
      )}
      {open && (
        <tr>
          <td colSpan={6}>
            <Opened id={doc.id} />
          </td>
        </tr>
      )}
    </>
  )
}

/** The Library's Sources tab: the notes and requirements saved to draft from more than once. */
export default function SourcesTab() {
  const { data, error, loading, reload } = useFetch<DocumentSummary[]>('/api/documents')
  const [adding, setAdding] = useState(false)

  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <ErrorState title="Could not load your documents" message={error?.message} onRetry={reload} />

  return (
    <>
      <div className="toolbar">
        <p className="meta" style={{ margin: 0 }}>
          Text you keep here can be drafted from again. Deleting a document removes its text.
        </p>
        {!adding && (
          <button type="button" onClick={() => setAdding(true)}>
            Add a document
          </button>
        )}
      </div>
      {adding && (
        <AddForm
          onSaved={() => {
            setAdding(false)
            reload()
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      {data.length === 0 ? (
        <EmptyState>No saved documents yet. Add meeting notes here, or choose Save as document when you draft a backlog.</EmptyState>
      ) : (
        <div className="card">
          <table className="data-table actions-end">
            <thead>
              <tr>
                <th>Title</th>
                <th>Kind</th>
                <th>Size</th>
                <th>Saved</th>
                <th>Use</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((doc) => (
                <Row key={doc.id} doc={doc} reload={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
