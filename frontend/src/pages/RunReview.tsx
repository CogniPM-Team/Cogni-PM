import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { ApproveResult, AuditPage, RerunResult, RunDetail } from '../api/types'
import { useFetch } from '../api/useFetch'
import ArrowLink from '../components/ArrowLink'
import DraftCard from '../components/DraftCard'
import { EmptyState, ErrorState, Tabs } from '../components/PageParts'
import { ModePill, StatusPill } from '../components/Pills'
import SourceText from '../components/SourceText'
import StepTrace from '../components/StepTrace'
import { useRunEvents } from '../hooks/useRunEvents'
import { useActorLabel } from '../lib/auth'
import { actionLabel, actorLabel, ago, duration, formatTime, plural, TASK_NAMES } from '../lib/format'
import { tabPanelProps } from '../lib/tabs'

type RunTab = 'drafts' | 'steps' | 'history'

/** One link to every issue this run created, as a Jira search. */
function allIssuesUrl(links: { key: string; url: string }[]): string | null {
  if (links.length === 0) return null
  return `${new URL(links[0].url).origin}/issues/?jql=${encodeURIComponent(`key in (${links.map((l) => l.key).join(', ')}) ORDER BY key`)}`
}

/** Everything the activity log recorded about this run, oldest first. Fetched only when the tab is opened. */
function RunActivity({ runId }: { runId: string }) {
  const label = useActorLabel()
  const { data, error, loading, reload } = useFetch<AuditPage>(`/api/audit?run_id=${runId}&limit=500`)
  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <ErrorState title="Could not load this run's history" message={error?.message} onRetry={reload} />
  if (data.rows.length === 0) return <EmptyState>Nothing has been recorded for this run yet.</EmptyState>
  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>What</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {[...data.rows].reverse().map((row) => (
            <tr key={row.id}>
              <td>
                <time dateTime={row.ts} title={ago(row.ts)}>
                  {formatTime(row.ts)}
                </time>
              </td>
              <td>{label(row.actor, row.actor_name)}</td>
              <td>
                {actionLabel(row.action)}
                {row.detail && <div className="meta">{row.detail}</div>}
              </td>
              <td className={`outcome-${row.outcome}`}>{row.outcome}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function RunReview() {
  const { id = '' } = useParams()
  const { data, error, loading, reload } = useFetch<RunDetail>(`/api/runs/${id}`)

  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <ErrorState title="Could not load this run" message={error?.message} onRetry={reload} />
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
  const location = useLocation()
  const [tab, setTab] = useState<RunTab>('drafts')
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
  const allIssues = allIssuesUrl(
    created.flatMap((d) => (d.issue_url && d.created_issue_key ? [{ key: d.created_issue_key, url: d.issue_url }] : [])),
  )
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
        <div className="run-head">
          <h3>{TASK_NAMES[run.task_type] ?? run.task_type}</h3>
          <ModePill mode={run.mode} />
          <StatusPill status={run.status} />
          {/* Back goes to wherever you came from (Home, Approvals, the activity log). Opened directly, there is no
              "before", so it falls back to Approvals. */}
          <span className="run-back">
            <ArrowLink
              back
              to="/approvals"
              onClick={(event) => {
                if (location.key === 'default') return
                event.preventDefault()
                navigate(-1)
              }}
            >
              Back
            </ArrowLink>
          </span>
        </div>
        <p className="run-note">{detail.status_note}</p>
        <dl className="run-meta">
          <div>
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
          </div>
          <div>
          <dt>Drafted by</dt>
          <dd>{actorLabel(run.agent)}</dd>
          </div>
          {run.ready_at && (
            <div>
              <dt>Ready for review</dt>
              <dd>
                {formatTime(run.ready_at)} ({ago(run.ready_at)})
              </dd>
            </div>
          )}
          {detail.instructions && (
            <div>
              <dt>Instructions</dt>
              <dd>{detail.instructions}</dd>
            </div>
          )}
          {run.rerun_of && (
            <div>
              <dt>Replaces</dt>
              <dd>
                <Link to={`/approvals/${run.rerun_of}`}>an earlier attempt</Link>
              </dd>
            </div>
          )}
          {run.comment && (
            <div>
              <dt>Note</dt>
              <dd>{run.comment}</dd>
            </div>
          )}
          {detail.seconds_to_decision != null && (
            <div>
              <dt>Time to decide</dt>
              <dd>{duration(detail.seconds_to_decision)}</dd>
            </div>
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
            <div className="notice-actions">
              {allIssues && (
                <a href={allIssues} target="_blank" rel="noopener noreferrer">
                  Open all created issues in Jira
                </a>
              )}
              <Link to="/console?mode=M2">Start another task</Link>
            </div>
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

      <Tabs
        label="Run"
        prefix="run"
        value={tab}
        onChange={(id) => setTab(id as RunTab)}
        tabs={[
          { id: 'drafts', label: 'Drafts', count: drafts.length },
          { id: 'steps', label: 'Steps' },
          { id: 'history', label: 'History' },
        ]}
      />

      {tab === 'steps' && (
        <div {...tabPanelProps('steps', 'run')} className="card run-tab">
          <StepTrace steps={detail.steps} />
          <p className="meta">
            {run.input_tokens != null && run.output_tokens != null
              ? `${run.model ?? 'The model'} used ${run.input_tokens.toLocaleString()} tokens in and ${run.output_tokens.toLocaleString()} out.`
              : 'No model usage was recorded for this run.'}
          </p>
        </div>
      )}
      {tab === 'history' && (
        <div {...tabPanelProps('history', 'run')} className="run-tab">
          <RunActivity runId={run.id} />
        </div>
      )}

      {/* Hidden, not removed, when another tab is open: ticks and half-typed edits are still there when you return. */}
      <div {...tabPanelProps('drafts', 'run')} hidden={tab !== 'drafts'} className="run-tab">
      {drafts.length === 0 && run.status !== 'running' && <EmptyState>This run produced no drafts.</EmptyState>}

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
            <EmptyState>The original input was not kept for this run.</EmptyState>
          )}
        </aside>
      </div>
      </div>
    </>
  )
}
