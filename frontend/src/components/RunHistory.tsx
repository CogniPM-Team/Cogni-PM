import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import type { RunList } from '../api/types'
import { useFetch } from '../api/useFetch'
import { RUNS_CHANGED } from '../lib/chatEvents'
import { ago, plural, TASK_NAMES } from '../lib/format'
import { StatusPill } from './Pills'

const SHOWN = 30

/**
 * Super-Pilot's history, the counterpart of the Co-Pilot's chat list: recent tasks with where each stands, the
 * ones waiting for you first. Opening one takes you to its review.
 */
export default function RunHistory() {
  const { data, error, reload } = useFetch<RunList>('/api/runs')

  useEffect(() => {
    window.addEventListener(RUNS_CHANGED, reload)
    return () => window.removeEventListener(RUNS_CHANGED, reload)
  }, [reload])

  const runs = data ? [...data.waiting, ...data.past].slice(0, SHOWN) : []

  return (
    <section className="chats" aria-label="Tasks">
      <h2 className="chats-title">Tasks</h2>
      {error && <p className="error">Could not load your tasks: {error.message}</p>}
      {data && runs.length === 0 && <p className="small-note muted">No tasks yet. Start one and it appears here.</p>}
      <ul className="chat-list">
        {runs.map((run) => (
          <li key={run.id} className="chat-row run-row">
            <Link to={`/approvals/${run.id}`}>
              <span className="run-title">{TASK_NAMES[run.task_type] ?? run.task_type}</span>
              <span className="run-sub">
                {run.scope} · {plural(run.draft_count, 'draft')} · {ago(run.created_at)}
              </span>
            </Link>
            <StatusPill status={run.status} />
          </li>
        ))}
      </ul>
    </section>
  )
}
