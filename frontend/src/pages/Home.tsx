import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { AuditPage, ChatSessionList, Project, RunList } from '../api/types'
import { useFetch } from '../api/useFetch'
import ArrowLink from '../components/ArrowLink'
import Icon from '../components/Icon'
import { EmptyState, ErrorState, PageHeader } from '../components/PageParts'
import RunCard from '../components/RunCard'
import { actionLabel, actorLabel, ago, formatTime } from '../lib/format'

const HIDE_KEY = 'cognipm.home.checklist.hidden'

function readHidden(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) === '1'
  } catch {
    return false // storage can be blocked; the checklist then just stays visible
  }
}

function NeedsYou() {
  const runs = useFetch<RunList>('/api/runs')

  return (
    <section aria-labelledby="home-needs">
      <div className="section-head">
        <h2 id="home-needs">Needs you</h2>
        {runs.data && (
          <span className="tab-count" aria-hidden="true">
            {runs.data.waiting.length + runs.data.past.filter((r) => r.status === 'failed' && r.draft_count > 0).length}
          </span>
        )}
      </div>
      {runs.loading && <p className="muted">Loading...</p>}
      {runs.error && <ErrorState title="Could not load your runs" message={runs.error.message} onRetry={runs.reload} />}
      {runs.data &&
        (() => {
          // A failed run that still has drafts can be approved again to create the rest, so it needs you too.
          const retry = runs.data.past.filter((r) => r.status === 'failed' && r.draft_count > 0)
          return runs.data.waiting.length + retry.length === 0 ? (
            <EmptyState>Nothing is waiting.</EmptyState>
          ) : (
            <div className="queue">
              {runs.data.waiting.map((run) => (
                <RunCard key={run.id} run={run} />
              ))}
              {retry.map((run) => (
                <RunCard key={run.id} run={run} retry />
              ))}
            </div>
          )
        })()}
    </section>
  )
}

function StartSomething() {
  return (
    <section aria-labelledby="home-start">
      <h2 id="home-start">Start something</h2>
      <div className="home-start">
        <Link to="/console?mode=M2">
          <span className="task-badge" aria-hidden="true">
            <Icon name="list" size={18} />
          </span>
          <span>
            <strong>Draft a backlog</strong>
            <small>Turn notes or requirements into stories</small>
          </span>
          <Icon name="arrow" size={16} />
        </Link>
        <Link to="/console?mode=M2&task=p2">
          <span className="task-badge" aria-hidden="true">
            <Icon name="branch" size={18} />
          </span>
          <span>
            <strong>Break down a story</strong>
            <small>Split a story into sub-tasks</small>
          </span>
          <Icon name="arrow" size={16} />
        </Link>
        <Link to="/console">
          <span className="task-badge" aria-hidden="true">
            <Icon name="console" size={18} />
          </span>
          <span>
            <strong>Ask the Co-Pilot</strong>
            <small>Ask a question about the project</small>
          </span>
          <Icon name="arrow" size={16} />
        </Link>
      </div>
    </section>
  )
}

function Recently() {
  const audit = useFetch<AuditPage>('/api/audit?filter=all&limit=5')

  return (
    <section aria-labelledby="home-recent">
      <h2 id="home-recent">Recently</h2>
      {audit.loading && <p className="muted">Loading...</p>}
      {audit.error && <ErrorState title="Could not load recent activity" message={audit.error.message} onRetry={audit.reload} />}
      {audit.data &&
        (audit.data.rows.length === 0 ? (
          <EmptyState>Nothing has happened yet.</EmptyState>
        ) : (
          <>
            <ul className="home-list">
              {audit.data.rows.map((row) => (
                <li key={row.id} className={`home-row${row.run_id ? ' clickable' : ''}`}>
                  <div>
                    <div>
                      {row.run_id ? (
                        <Link className="stretch" to={`/approvals/${row.run_id}`}>
                          {actionLabel(row.action)}
                        </Link>
                      ) : (
                        actionLabel(row.action)
                      )}
                    </div>
                    <div className="meta">{actorLabel(row.actor)}</div>
                  </div>
                  <time className="meta when" dateTime={row.ts} title={formatTime(row.ts)}>
                    <Icon name="clock" size={14} />
                    {ago(row.ts)}
                  </time>
                </li>
              ))}
            </ul>
            <p className="more">
              <ArrowLink to="/activity">See the whole activity log</ArrowLink>
            </p>
          </>
        ))}
    </section>
  )
}

/** First-run steps, worked out from what already exists, so nothing is stored but whether you hid it. */
function Checklist() {
  const project = useFetch<Project>('/api/project')
  const chats = useFetch<ChatSessionList>('/api/chat/sessions')
  const runs = useFetch<RunList>('/api/runs')
  const changed = useFetch<AuditPage>('/api/audit?filter=changed_jira&limit=1')
  const [hidden, setHidden] = useState(readHidden)

  // Wait until all four answers are in, so the list does not flicker from "undone" to "done".
  if (hidden || project.loading || chats.loading || runs.loading || changed.loading) return null

  const steps = [
    { label: 'Connect Jira', done: Boolean(project.data) },
    { label: 'Ask the Co-Pilot a question', done: (chats.data?.sessions.length ?? 0) > 0, to: '/console' },
    {
      label: 'Run a first draft',
      done: (runs.data ? runs.data.waiting.length + runs.data.past.length : 0) > 0,
      to: '/console?mode=M2',
    },
    { label: 'Approve a draft into Jira', done: (changed.data?.rows.length ?? 0) > 0, to: '/approvals' },
  ]
  if (steps.every((s) => s.done)) return null

  function hide() {
    try {
      localStorage.setItem(HIDE_KEY, '1')
    } catch {
      // not remembered across visits, but it still hides for now
    }
    setHidden(true)
  }

  return (
    <section className="card checklist" aria-labelledby="home-start-here">
      <div className="checklist-head">
        <h2 id="home-start-here">Getting started</h2>
        <button type="button" className="link" onClick={hide}>
          Hide
        </button>
      </div>
      <ul>
        {steps.map((step) => (
          <li key={step.label} className={step.done ? 'done' : undefined}>
            <span className="check" aria-hidden="true">
              {step.done ? '✓' : ''}
            </span>
            {step.done || !step.to ? step.label : <Link to={step.to}>{step.label}</Link>}
            {step.done && <span className="sr-only"> (done)</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function Home() {
  return (
    <>
      <PageHeader description="What needs you, and where to go next." />
      <div className="home-grid">
        <div className="home-main">
          <NeedsYou />
          <Recently />
        </div>
        <div className="home-side">
          <Checklist />
          <StartSomething />
        </div>
      </div>
    </>
  )
}
