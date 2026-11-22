import { useState } from 'react'
import { apiUrl } from '../api/client'
import type { Insights as InsightsData } from '../api/types'
import { useFetch } from '../api/useFetch'
import Icon from '../components/Icon'
import { EmptyState, ErrorState, PageHeader, StatCard } from '../components/PageParts'
import { duration, plural } from '../lib/format'
import { insightsParams, type InsightsQuery, REPORT_PARTS, share, TOO_FEW } from '../lib/insights'

const TASKS: { id: InsightsQuery['task']; label: string }[] = [
  { id: '', label: 'All tasks' },
  { id: 'p1', label: 'Draft backlog' },
  { id: 'p2', label: 'Break down a story' },
]

/** One bar split into parts, with the counts spelled out beneath it: the colours help, the numbers say it. */
function StackedBar({ parts }: { parts: { id: string; label: string; value: number }[] }) {
  const total = parts.reduce((sum, p) => sum + p.value, 0)
  return (
    <>
      <div className="stack-bar" role="img" aria-label={parts.map((p) => `${p.label}: ${p.value}`).join(', ')}>
        {parts.map((p) => p.value > 0 && <span key={p.id} className={`seg seg-${p.id}`} style={{ width: `${(100 * p.value) / total}%` }} />)}
      </div>
      <ul className="legend">
        {parts.map((p) => (
          <li key={p.id}>
            <span className={`swatch seg-${p.id}`} aria-hidden="true" />
            <span>{p.label}</span>
            <strong>{p.value}</strong>
            <span className="meta">{share(p.value, total).percent}</span>
          </li>
        ))}
      </ul>
    </>
  )
}

function Results({ n }: { n: InsightsData }) {
  const approval = share(n.runs_approved, n.runs_decided)
  const rejection = share(n.runs_rejected, n.runs_decided)
  const edits = share(n.drafts_edited, n.drafts_reviewed)
  const untouched = share(n.approved_untouched, n.runs_approved)
  const reruns = share(n.reruns, n.runs_started)
  const decided = n.runs_decided > 0
  const mostRefused = Math.max(1, ...n.refusals.map((r) => r.count))

  return (
    <>
      <p className="insights-group">
        {plural(n.runs_started, 'run')} started: {n.runs_decided} decided, {n.runs_open} still open.
        {decided && n.runs_decided < TOO_FEW && <span className="tag overdue"> Too few to read yet</span>}
      </p>

      {decided ? (
        <>
          <div className="stat-grid">
            <StatCard label="Approval rate" value={approval.percent} hint={`${approval.text} decided runs`} source="Runs approved ÷ runs decided (runs.status). A run is approved if at least one draft was created." />
            <StatCard label="Rejection rate" value={rejection.percent} hint={`${rejection.text} decided runs`} source="Runs rejected ÷ runs decided (runs.status). Includes Regenerate." />
            <StatCard label="Edit rate" value={edits.percent} hint={`${edits.text} drafts changed`} source="Reviewed drafts whose text differs from the agent's original ÷ reviewed drafts (staged_changes.edited_payload)." />
            <StatCard label="Approved untouched" value={untouched.percent} hint={untouched.text ? `${untouched.text} approved runs` : 'No approved runs'} source="Approved runs where every draft was created and none edited ÷ approved runs." />
          </div>

          <div className="insights-grid">
            <section className="card" aria-labelledby="ins-drafts">
              <h2 id="ins-drafts">What happened to each draft</h2>
              <p className="meta">{plural(n.drafts_reviewed, 'draft')} reviewed in the decided runs.</p>
              <StackedBar parts={REPORT_PARTS(n)} />
            </section>

            <section className="card" aria-labelledby="ins-time">
              <h2 id="ins-time">Time to decide</h2>
              {n.decision_seconds_median === null ? (
                <p className="meta">No decided run has a time yet.</p>
              ) : (
                <div className="time-pair" title="From the moment the drafts were reviewable to the approval or rejection (runs.ready_at to runs.decided_at).">
                  <div>
                    <span className="stat-value">{duration(n.decision_seconds_median)}</span>
                    <span className="stat-label">Typical (median)</span>
                  </div>
                  <div>
                    <span className="stat-value">{duration(n.decision_seconds_p90 ?? 0)}</span>
                    <span className="stat-label">Slowest 1 in 10</span>
                  </div>
                </div>
              )}
              <p className="meta">Clock time across {plural(n.decisions_timed, 'run')}. It includes time spent away.</p>
            </section>
          </div>
        </>
      ) : (
        <EmptyState>
          No decisions yet. {n.runs_open > 0 ? `${plural(n.runs_open, 'run')} ${n.runs_open === 1 ? 'is' : 'are'} still open.` : 'Approve or reject a run and the numbers start here.'}
        </EmptyState>
      )}

      <div className="insights-grid">
        <section className="card" aria-labelledby="ins-rules">
          <h2 id="ins-rules">Safety rules that refused a draft</h2>
          {n.refusals.length === 0 ? (
            <p className="meta">No draft has been refused in these runs.</p>
          ) : (
            <ul className="rule-bars">
              {n.refusals.map((r) => (
                <li key={r.rule}>
                  <span className="rule-name">{r.rule.replace(/_/g, ' ')}</span>
                  <span className="track" aria-hidden="true">
                    <span className="fill" style={{ width: `${(100 * r.count) / mostRefused}%` }} />
                  </span>
                  <strong>{r.count}</strong>
                </li>
              ))}
            </ul>
          )}
          <p className="meta">Counts attempts: one draft can be refused when it is proposed and again when it is approved.</p>
        </section>

        <section className="card" aria-labelledby="ins-usage">
          <h2 id="ins-usage">AI usage and reruns</h2>
          <div className="time-pair">
            <div>
              <span className="stat-value">{n.tokens_average === null ? '–' : Math.round(n.tokens_average).toLocaleString()}</span>
              <span className="stat-label">Tokens per run</span>
            </div>
            <div>
              <span className="stat-value">{n.tokens_total.toLocaleString()}</span>
              <span className="stat-label">Tokens in total</span>
            </div>
            <div>
              <span className="stat-value">{reruns.percent}</span>
              <span className="stat-label">Runs that were reruns</span>
            </div>
          </div>
          <p className="meta">Tokens are input plus output across {plural(n.tokens_runs, 'run')} that report them. {reruns.text && `${reruns.text} runs replaced an earlier one.`}</p>
        </section>
      </div>
    </>
  )
}

export default function Insights() {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [task, setTask] = useState<InsightsQuery['task']>('')
  const query = { from, to, task }
  const qs = insightsParams(query)
  const { data, error, loading, reload } = useFetch<InsightsData>(`/api/insights${qs ? `?${qs}` : ''}`)
  const narrowed = from !== '' || to !== '' || task !== ''

  return (
    <>
      <PageHeader description="Is a person really reviewing what the AI drafts, and is it useful? Every number is about the runs started in the range, and you can download the lines behind them." />
      <div className="toolbar">
        <div className="filters">
          <label>
            From <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label>
            To <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label>
            Task{' '}
            <select value={task} onChange={(e) => setTask(e.target.value as InsightsQuery['task'])}>
              {TASKS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          {narrowed && (
            <button
              type="button"
              className="small"
              onClick={() => {
                setFrom('')
                setTo('')
                setTask('')
              }}
            >
              Clear
            </button>
          )}
        </div>
        <a className="button-link small with-icon" href={apiUrl(`/api/insights/export.csv${qs ? `?${qs}` : ''}`)} download>
          Download the data
          <Icon name="download" size={14} />
        </a>
      </div>

      {loading && <p className="muted">Loading...</p>}
      {error && <ErrorState title="Could not load the insights" message={error.message} onRetry={reload} />}
      {data && data.runs_started === 0 && <EmptyState>{narrowed ? 'No runs were started in this range.' : 'No runs yet. Start a task in the Agent console and its numbers appear here.'}</EmptyState>}
      {data && data.runs_started > 0 && <Results n={data} />}
    </>
  )
}
