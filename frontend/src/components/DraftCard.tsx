import { useState } from 'react'
import { api } from '../api/client'
import type { ChangeEdit, Draft } from '../api/types'
import { STATUS_LABELS } from '../lib/format'
import Icon from './Icon'

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

const LONG = 260 // characters; beyond this the description is cut to a few lines with a way to read it all

/** A few lines of the description, with the rest one press away, so a long draft does not bury the ones after it. */
function Description({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > LONG
  return (
    <div className="draft-desc">
      <p className={long && !open ? 'clamped' : undefined}>{text}</p>
      {long && (
        <button type="button" className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}

export default function DraftCard({ draft, ticked, canTick, canEdit, onTick, onActivate, onSaved }: Props) {
  const [editing, setEditing] = useState(false)
  const [evidence, setEvidence] = useState<'why' | 'assumption' | 'quotes' | null>(null)
  const effective = draft.effective as Payload
  const original = draft.payload as Payload
  const edited = draft.edited_payload !== null
  const hasAssumption = draft.assumptions.trim().toUpperCase() !== 'NA'
  const done = draft.status === 'applied' || draft.status === 'rejected'
  const lostQuotes = draft.sources.filter((q) => q.start === null).length

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
            {effective.description && <Description text={effective.description} />}

            {effective.acceptance_criteria && effective.acceptance_criteria.length > 0 && (
              <section className="draft-part" aria-label="Acceptance criteria">
                <h4>Done when</h4>
                <ul className="criteria">
                  {effective.acceptance_criteria.map((c) => (
                    <li key={c}>
                      <Icon name="check" size={14} />
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {effective.labels && effective.labels.length > 0 && (
              <ul className="draft-labels" aria-label="Labels">
                {effective.labels.map((l) => (
                  <li key={l} className="tag">
                    {l}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {/* The reasons, the agent's guess and the quotes sit one press away, one at a time, so a run of drafts reads as a
            list of things to decide. A draft that states an assumption has an amber tab, so it is never missed. */}
        {draft.error && <p className="error">Jira refused this one: {draft.error}</p>}

        {!editing && (
          <div className="draft-foot">
            <div className="evidence" role="group" aria-label="Evidence">
              <button
                type="button"
                className="evidence-tab"
                aria-expanded={evidence === 'why'}
                aria-controls={`${draft.id}-evidence`}
                aria-label="Why the agent drafted this"
                title="Why the agent drafted this"
                onClick={() => setEvidence(evidence === 'why' ? null : 'why')}
              >
                Why
                <Icon name="info" size={14} />
              </button>
              {hasAssumption && (
                <button
                  type="button"
                  className="evidence-tab warn"
                  aria-expanded={evidence === 'assumption'}
                  aria-controls={`${draft.id}-evidence`}
                  aria-label="Check this assumption"
                  title="The agent guessed something here. Check this assumption"
                  onClick={() => setEvidence(evidence === 'assumption' ? null : 'assumption')}
                >
                  Assumption
                  <Icon name="alert" size={14} />
                </button>
              )}
              <button
                type="button"
                className={`evidence-tab${lostQuotes > 0 ? ' warn' : ''}`}
                aria-expanded={evidence === 'quotes'}
                aria-controls={`${draft.id}-evidence`}
                onClick={() => setEvidence(evidence === 'quotes' ? null : 'quotes')}
              >
                From your input
                <span className="tab-count">{draft.sources.length}</span>
                {lostQuotes > 0 && <span className="sr-only"> ({lostQuotes} not found in the saved input)</span>}
              </button>
            </div>
            {canEdit && (
              <button type="button" className="small" onClick={() => setEditing(true)}>
                Edit before approving
              </button>
            )}
          </div>
        )}

        {evidence && !editing && (
          <div className="evidence-panel" id={`${draft.id}-evidence`}>
            {evidence === 'why' ? (
              <p>{draft.reasoning}</p>
            ) : evidence === 'assumption' ? (
              <p className="assumption-text">{draft.assumptions}</p>
            ) : (
              draft.sources.map((source) => (
                <p key={source.quote} className={`quote${source.start === null ? ' lost' : ''}`}>
                  “{source.quote}”
                  {source.start === null && <span className="muted"> (not found in the saved input)</span>}
                </p>
              ))
            )}
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
