import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { ApproveResult, RerunResult, RunDetail } from '../api/types'
import { useFetch } from '../api/useFetch'
import DraftCard from '../components/DraftCard'
import { ModePill, StatusPill } from '../components/Pills'
import SourceText from '../components/SourceText'
import StepTrace from '../components/StepTrace'
import { useRunEvents } from '../hooks/useRunEvents'
import { ago, duration, formatTime, plural, TASK_NAMES } from '../lib/format'

export default function RunReview() {
  const { id = '' } = useParams()
  const { data, error, loading, reload } = useFetch<RunDetail>(`/api/runs/${id}`)

  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <p className="error">Could not load this run: {error?.message}</p>
  return <ReviewBody key={data.run.id} detail={data} reload={reload} />
}

/** A run still working: show its steps, and reload the page once it is done. */
function LiveRun({ runId, onDone }: { runId: string; onDone: () => void }) {
  const { steps, status } = useRunEvents(runId)
  useEffect(() => {
    if (status) onDone()
  }, [status, onDone])
  return (
    <div className="card">
      <h3>The agent is working</h3>
      <StepTrace steps={steps} />
    </div>
  )
}

function ReviewBody({ detail, reload }: { detail: RunDetail; reload: () => void }) {
  const navigate = useNavigate()
  const { run, drafts } = detail
  const [ticked, setTicked] = useState<Set<string>>(new Set())
  const [active, setActive] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [form, setForm] = useState<'reject' | 'rerun' | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<ApiError | Error | null>(null)

  const pending = drafts.filter((d) => d.status === 'proposed' || d.status === 'failed')
  const created = drafts.filter((d) => d.created_issue_key)
  const apiProblem = problem instanceof ApiError ? problem.problem : undefined

  function toggle(draftId: string) {
    setConfirming(false)
    setTicked((previous) => {
      const next = new Set(previous)
      if (!next.delete(draftId)) next.add(draftId)
      return next
    })
  }

  async function act<T>(work: () => Promise<T>, then?: (result: T) => void) {
    setBusy(true)
    setProblem(null)
    try {
      const result = await work()
      setTicked(new Set())
      setConfirming(false)
      setForm(null)
      setNote('')
      if (then) then(result)
      else reload()
    } catch (e) {
      setProblem(e as Error)
      reload() // the run may have changed even though the request failed (for example, partly created)
    } finally {
      setBusy(false)
    }
  }

  const approve = () =>
    act(() => api.post<ApproveResult>(`/api/runs/${run.id}/approve`, { change_ids: [...ticked] }))
  const reject = () => act(() => api.post(`/api/runs/${run.id}/reject`, { comment: note }))
  const rerun = () =>
    act(
      () => api.post<RerunResult>(`/api/runs/${run.id}/rerun`, { note }),
      (result) => navigate(`/approvals/${result.run_id}`),
    )

  return (
    <>
      <div className={`card mode-${run.mode}`}>
        <div className="queue-top">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <ModePill mode={run.mode} />
            <StatusPill status={run.status} />
          </div>
          <Link to="/approvals">Back to Approvals</Link>
        </div>
        <h3>{TASK_NAMES[run.task_type] ?? run.task_type}</h3>
        <p style={{ margin: '4px 0 12px' }}>{detail.status_note}</p>
        <dl className="run-meta">
          <dt>Asked to work on</dt>
          <dd>
            {detail.parent_story ? (
              <a href={detail.parent_story.url} target="_blank" rel="noopener noreferrer">
                {detail.parent_story.key} {detail.parent_story.summary}
              </a>
            ) : (
              run.scope
            )}
          </dd>
          <dt>Drafted by</dt>
          <dd>{run.agent}</dd>
          {run.ready_at && (
            <>
              <dt>Ready for review</dt>
              <dd>
                {formatTime(run.ready_at)} ({ago(run.ready_at)})
              </dd>
            </>
          )}
          {detail.instructions && (
            <>
              <dt>Instructions</dt>
              <dd>{detail.instructions}</dd>
            </>
          )}
          {run.rerun_of && (
            <>
              <dt>Replaces</dt>
              <dd>
                <Link to={`/approvals/${run.rerun_of}`}>an earlier attempt</Link>
              </dd>
            </>
          )}
          {run.comment && (
            <>
              <dt>Note</dt>
              <dd>{run.comment}</dd>
            </>
          )}
          {detail.seconds_to_decision != null && (
            <>
              <dt>Time to decide</dt>
              <dd>{duration(detail.seconds_to_decision)}</dd>
            </>
          )}
        </dl>
      </div>

      {run.status === 'running' && <LiveRun runId={run.id} onDone={reload} />}

      {created.length > 0 && (
        <div className="notice good" role="status">
          <div>
            <strong>Created in Jira:</strong>
            <ul className="created">
              {created.map((d) => (
                <li key={d.id}>
                  <a href={d.issue_url ?? undefined} target="_blank" rel="noopener noreferrer" className="mono">
                    {d.created_issue_key}
                  </a>{' '}
                  {(d.effective as { summary?: string }).summary}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {problem && (
        <div className="error" role="alert">
          {problem.message}
          {apiProblem && (
            <ul>
              <li>Created: {apiProblem.created.map((c) => c.issue_key).join(', ') || 'nothing'}</li>
              <li>Not created: {plural(apiProblem.not_created.length, 'draft')}</li>
              <li>Approve again to create the rest. Nothing is created twice.</li>
            </ul>
          )}
        </div>
      )}

      {drafts.length === 0 && run.status !== 'running' && <p className="empty">This run produced no drafts.</p>}

      <div className="review">
        <div>
          {drafts.map((draft) => (
            <DraftCard
              key={draft.id}
              draft={draft}
              ticked={ticked.has(draft.id)}
              canTick={detail.can_decide && pending.some((p) => p.id === draft.id)}
              canEdit={detail.editable && draft.status === 'proposed'}
              onTick={() => toggle(draft.id)}
              onActivate={setActive}
              onSaved={reload}
            />
          ))}

          {detail.can_decide && (
            <div className="decision-bar">
              <span>
                <strong>{ticked.size}</strong> of {pending.length} ticked
              </span>
              <span className="spacer" />
              <button type="button" className="reject" disabled={busy} onClick={() => setForm(form === 'reject' ? null : 'reject')}>
                Reject
              </button>
              <button type="button" disabled={busy} onClick={() => setForm(form === 'rerun' ? null : 'rerun')}>
                Regenerate
              </button>
              <button
                type="button"
                className="primary"
                disabled={busy || ticked.size === 0}
                onClick={() => setConfirming(true)}
                title={ticked.size === 0 ? 'Tick the drafts you want created' : undefined}
              >
                {ticked.size === 0 ? 'Approve and create' : `Approve and create ${plural(ticked.size, 'issue')}`}
              </button>

              {confirming && (
                <div className="confirm" role="alertdialog" aria-label="Confirm approval">
                  <span>
                    This creates <strong>{plural(ticked.size, 'issue')}</strong> in Jira.
                    {pending.length > ticked.size && ` The other ${pending.length - ticked.size} will be left out, not created.`}
                  </span>
                  <button type="button" className="primary small" disabled={busy} onClick={() => void approve()}>
                    {busy ? 'Creating...' : 'Yes, create them'}
                  </button>
                  <button type="button" className="small" disabled={busy} onClick={() => setConfirming(false)}>
                    Cancel
                  </button>
                </div>
              )}

              {form && (
                <form
                  className="confirm"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void (form === 'reject' ? reject() : rerun())
                  }}
                >
                  <label className="field" style={{ flex: 1, margin: 0 }}>
                    <span>
                      {form === 'reject'
                        ? 'Why are you rejecting this? (kept as feedback)'
                        : 'What should the agent do differently?'}
                    </span>
                    <textarea value={note} onChange={(e) => setNote(e.target.value)} style={{ minHeight: '3rem' }} />
                  </label>
                  <button type="submit" className="primary small" disabled={busy || (form === 'rerun' && !note.trim())}>
                    {form === 'reject' ? 'Reject this run' : 'Try again'}
                  </button>
                </form>
              )}
            </div>
          )}
        </div>

        <aside className="card source-pane" aria-label="Original input">
          <h3>{run.task_type === 'p2' ? 'The story' : 'Your original input'}</h3>
          <p className="meta">Quotes the agent cited are highlighted. Hover a draft to see which.</p>
          {detail.input_text ? (
            <SourceText text={detail.input_text} drafts={drafts} activeDraft={active} />
          ) : (
            <p className="empty">The original input was not kept for this run.</p>
          )}
        </aside>
      </div>
    </>
  )
}
