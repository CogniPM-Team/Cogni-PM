import { Link } from 'react-router-dom'
import type { RunList, RunSummary } from '../api/types'
import { useFetch } from '../api/useFetch'
import { ModePill, StatusPill } from '../components/Pills'
import { ago, formatTime, plural, TASK_NAMES } from '../lib/format'

function QueueCard({ run }: { run: RunSummary }) {
  return (
    <article className={`queue-card mode-${run.mode}`}>
      <div className="queue-top">
        <ModePill mode={run.mode} />
      </div>
      <div className="queue-title">{TASK_NAMES[run.task_type] ?? run.task_type}</div>
      <div className="meta">{run.scope}</div>
      <div className="meta">
        {plural(run.draft_count, 'draft')}
        {run.ready_at && ` · waiting ${ago(run.ready_at)}`}
      </div>
      <div className="row-actions">
        <Link className="button-link" to={`/approvals/${run.id}`}>
          Review
        </Link>
      </div>
    </article>
  )
}

export default function Approvals() {
  const { data, error, loading } = useFetch<RunList>('/api/runs')

  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <p className="error">Could not load runs: {error?.message}</p>

  return (
    <>
      <p className="page-subtitle">
        Nothing the agents draft reaches Jira until you approve it here. Runs that have waited longest come first.
      </p>
      <h2 style={{ marginTop: 0 }}>{data.awaiting_review_count} waiting for you</h2>
      {data.waiting.length === 0 ? (
        <p className="empty">
          Nothing is waiting. Start a task in the <Link to="/console">Agent console</Link>.
        </p>
      ) : (
        <div className="queue">
          {data.waiting.map((run) => (
            <QueueCard key={run.id} run={run} />
          ))}
        </div>
      )}

      <h2>Earlier runs</h2>
      {data.past.length === 0 ? (
        <p className="empty">No earlier runs yet.</p>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Started</th>
                <th>Task</th>
                <th>Mode</th>
                <th>Drafts</th>
                <th>Outcome</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.past.map((run) => (
                <tr key={run.id}>
                  <td>{formatTime(run.created_at)}</td>
                  <td>
                    {TASK_NAMES[run.task_type] ?? run.task_type}
                    <div className="meta">{run.scope}</div>
                  </td>
                  <td>
                    <ModePill mode={run.mode} />
                  </td>
                  <td>{run.draft_count}</td>
                  <td>
                    <StatusPill status={run.status} />
                  </td>
                  <td>
                    <Link to={`/approvals/${run.id}`}>Open</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
