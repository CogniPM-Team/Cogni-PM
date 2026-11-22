import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { RunList, RunSummary } from '../api/types'
import { useFetch } from '../api/useFetch'
import ArrowLink from '../components/ArrowLink'
import { EmptyState, ErrorState, PageHeader, Tabs } from '../components/PageParts'
import { ModePill, StatusPill } from '../components/Pills'
import RunCard from '../components/RunCard'
import { ago, formatTime, STATUS_LABELS, TASK_NAMES } from '../lib/format'
import { tabPanelProps } from '../lib/tabs'

type View = 'waiting' | 'history'

function History({ runs }: { runs: RunSummary[] }) {
  const [status, setStatus] = useState('all')
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  // Only offer outcomes that exist, so no choice leads to an empty list.
  const statuses = [...new Set(runs.map((r) => r.status))]
  const needle = search.trim().toLowerCase()
  const shown = runs.filter(
    (r) =>
      (status === 'all' || r.status === status) &&
      (needle === '' || `${r.scope} ${TASK_NAMES[r.task_type] ?? r.task_type}`.toLowerCase().includes(needle)),
  )

  if (runs.length === 0) return <EmptyState>No earlier runs yet.</EmptyState>

  return (
    <>
      <div className="toolbar">
        <label>
          Outcome{' '}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">All</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s] ?? s}
              </option>
            ))}
          </select>
        </label>
        <input
          type="search"
          aria-label="Search by task or source"
          placeholder="Search by task or source"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {shown.length === 0 ? (
        <EmptyState>No runs match.</EmptyState>
      ) : (
        <div className="card">
          <table className="data-table actions-end">
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
              {shown.map((run) => (
                <tr
                  key={run.id}
                  className="row-click"
                  onClick={(event) => {
                    // the whole row opens the run, except when the press was on the link itself
                    if (!(event.target as HTMLElement).closest('a, button')) navigate(`/approvals/${run.id}`)
                  }}
                >
                  <td>
                    <time dateTime={run.created_at} title={ago(run.created_at)}>
                      {formatTime(run.created_at)}
                    </time>
                  </td>
                  <td className="key">
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
                    <ArrowLink to={`/approvals/${run.id}`}>Open</ArrowLink>
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

export default function Approvals() {
  const { data, error, loading, reload } = useFetch<RunList>('/api/runs')
  const [view, setView] = useState<View>('waiting')

  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <ErrorState title="Could not load your runs" message={error?.message} onRetry={reload} />

  return (
    <>
      <PageHeader description="Nothing the agents draft reaches Jira until you approve it here. Runs that have waited longest come first." />
      <Tabs
        label="Runs"
        prefix="approvals"
        value={view}
        onChange={(id) => setView(id as View)}
        tabs={[
          { id: 'waiting', label: 'Waiting', count: data.awaiting_review_count },
          { id: 'history', label: 'History' },
        ]}
      />
      <div {...tabPanelProps(view, 'approvals')}>
        {view === 'waiting' ? (
          data.waiting.length === 0 ? (
            <EmptyState>
              Nothing is waiting. Start a task in the <Link to="/console">Agent console</Link>.
            </EmptyState>
          ) : (
            <div className="queue">
              {data.waiting.map((run) => (
                <RunCard key={run.id} run={run} />
              ))}
            </div>
          )
        ) : (
          <History runs={data.past} />
        )}
      </div>
    </>
  )
}
