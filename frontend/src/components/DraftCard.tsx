import { useState } from 'react'
import { api } from '../api/client'
import type { ChangeEdit, Draft } from '../api/types'
import { STATUS_LABELS } from '../lib/format'

interface Props {
  draft: Draft
  ticked: boolean
  /** The PM may still choose this draft for approval. */
  canTick: boolean
  canEdit: boolean
  onTick: () => void
  /** Hovering or focusing a draft highlights the quotes it cites in the original input. */
  onActivate: (id: string | null) => void
  onSaved: (draft: Draft) => void
}

type Payload = {
  summary?: string
  description?: string
  acceptance_criteria?: string[]
  labels?: string[]
  issue_type?: string
}

export default function DraftCard({ draft, ticked, canTick, canEdit, onTick, onActivate, onSaved }: Props) {
  const [editing, setEditing] = useState(false)
  const effective = draft.effective as Payload
  const original = draft.payload as Payload
  const edited = draft.edited_payload !== null
  const hasAssumption = draft.assumptions.trim().toUpperCase() !== 'NA'
  const done = draft.status === 'applied' || draft.status === 'rejected'

  return (
    <article
      className={`draft${ticked ? ' ticked' : ''}${done ? ' done' : ''}`}
      onMouseEnter={() => onActivate(draft.id)}
      onMouseLeave={() => onActivate(null)}
      onFocus={() => onActivate(draft.id)}
      onBlur={() => onActivate(null)}
    >
      <div className="draft-head">
        {canTick && (
          <input
            type="checkbox"
            checked={ticked}
            onChange={onTick}
            aria-label={`Create "${effective.summary}" in Jira`}
          />
        )}
        <div>
          <h3 className="draft-title">{effective.summary}</h3>
          <div className="draft-sub">
            <span className="tag">{draft.kind === 'subtask' ? 'Sub-task' : (effective.issue_type ?? 'Story')}</span>
            {edited && <span className="tag">Edited by you</span>}
            {draft.status !== 'proposed' && <span className={`status status-${draft.status}`}>{STATUS_LABELS[draft.status]}</span>}
            {draft.created_issue_key && (
              <a href={draft.issue_url ?? undefined} target="_blank" rel="noopener noreferrer" className="mono">
                {draft.created_issue_key}
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="draft-body">
        {edited && original.summary !== effective.summary && (
          <p className="edited-from">
            The agent wrote: <del>{original.summary}</del>
          </p>
        )}

        {editing ? (
          <EditForm
            draft={draft}
            onCancel={() => setEditing(false)}
            onSaved={(updated) => {
              setEditing(false)
              onSaved(updated)
            }}
          />
        ) : (
          <>
            {effective.description && <p>{effective.description}</p>}
            {effective.acceptance_criteria && effective.acceptance_criteria.length > 0 && (
              <>
                <h4>Acceptance criteria</h4>
                <ul>
                  {effective.acceptance_criteria.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </>
            )}
            {effective.labels && effective.labels.length > 0 && (
              <>
                <h4>Labels</h4>
                <p>{effective.labels.join(', ')}</p>
              </>
            )}
          </>
        )}

        <h4>Why the agent drafted this</h4>
        <p>{draft.reasoning}</p>

        <h4>{hasAssumption ? 'Check this assumption' : 'Assumptions'}</h4>
        <p className={`assumption${hasAssumption ? '' : ' none'}`}>{hasAssumption ? draft.assumptions : 'None stated.'}</p>

        <h4>Quoted from your input</h4>
        {draft.sources.map((source) => (
          <p key={source.quote} className={`quote${source.start === null ? ' lost' : ''}`}>
            “{source.quote}”
            {source.start === null && <span className="muted"> (not found in the saved input)</span>}
          </p>
        ))}

        {draft.error && <p className="error">Jira refused this one: {draft.error}</p>}

        {canEdit && !editing && (
          <div className="row-actions">
            <button type="button" className="small" onClick={() => setEditing(true)}>
              Edit before approving
            </button>
          </div>
        )}
      </div>
    </article>
  )
}

function EditForm({ draft, onCancel, onSaved }: { draft: Draft; onCancel: () => void; onSaved: (d: Draft) => void }) {
  const current = draft.effective as Payload
  const isStory = draft.kind !== 'subtask'
  const [summary, setSummary] = useState(current.summary ?? '')
  const [description, setDescription] = useState(current.description ?? '')
  const [criteria, setCriteria] = useState((current.acceptance_criteria ?? []).join('\n'))
  const [labels, setLabels] = useState((current.labels ?? []).join(', '))
  const [issueType, setIssueType] = useState(current.issue_type ?? 'Story')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function save() {
    const body: ChangeEdit = {
      summary,
      description,
      labels: labels.split(',').map((l) => l.trim()).filter(Boolean),
    }
    if (isStory) {
      body.acceptance_criteria = criteria.split('\n').map((c) => c.trim()).filter(Boolean)
      body.issue_type = issueType as ChangeEdit['issue_type']
    }
    setSaving(true)
    setError(null)
    try {
      onSaved(await api.patch<Draft>(`/api/changes/${draft.id}`, body))
    } catch (e) {
      setError((e as Error).message)
      setSaving(false)
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void save()
      }}
    >
      <label className="field">
        <span>Title</span>
        <input type="text" value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={255} required />
      </label>
      <label className="field">
        <span>Description</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {isStory && (
        <>
          <label className="field">
            <span>Acceptance criteria (one per line)</span>
            <textarea value={criteria} onChange={(e) => setCriteria(e.target.value)} />
          </label>
          <label className="field">
            <span>Issue type</span>
            <select value={issueType} onChange={(e) => setIssueType(e.target.value)}>
              <option>Story</option>
              <option>Task</option>
              <option>Bug</option>
            </select>
          </label>
        </>
      )}
      <label className="field">
        <span>Labels (comma separated)</span>
        <input type="text" value={labels} onChange={(e) => setLabels(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="row-actions">
        <button type="submit" className="primary small" disabled={saving || !summary.trim()}>
          {saving ? 'Saving...' : 'Save changes'}
        </button>
        <button type="button" className="small" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  )
}
