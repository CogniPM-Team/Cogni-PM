import { Link } from 'react-router-dom'
import { duration, MODE_NAMES, plural, TASK_NAMES } from '../lib/format'
import { ModePill, StatusPill } from './Pills'
import type { Snapshot } from './RunProgress'

/** The newest run at a glance: where it stands, what it has done, and what is waiting on you. */
export default function TaskInspector({ snapshot }: { snapshot: Snapshot | null }) {
  if (!snapshot) {
    return (
      <aside className="card inspector" aria-label="Task inspector">
        <h3>Task inspector</h3>
        <p className="muted">Start a task and its progress appears here.</p>
      </aside>
    )
  }
  const drafts = snapshot.detail?.drafts ?? []
  const created = drafts.filter((d) => d.status === 'applied').length
  const waiting = snapshot.status === 'awaiting_review' ? drafts.filter((d) => d.status === 'proposed').length : 0
  const run = snapshot.detail?.run

  return (
    <aside className="card inspector" aria-label="Task inspector">
      <h3>Task inspector</h3>
      <p className="meta">{TASK_NAMES[snapshot.task] ?? snapshot.task}</p>
      <dl>
        <dt>Status</dt>
        <dd>
          <StatusPill status={snapshot.status} />
        </dd>
        <dt>Mode</dt>
        <dd>{run ? <ModePill mode={run.mode} /> : MODE_NAMES.M2}</dd>
        <dt>Work so far</dt>
        <dd>{plural(snapshot.stepCount, 'step')} done</dd>
        <dt>Drafted</dt>
        <dd>{drafts.length}</dd>
        <dt>Waiting for you</dt>
        <dd>{waiting}</dd>
        <dt>Created in Jira</dt>
        <dd>{created}</dd>
        {run?.input_tokens != null && (
          <>
            <dt>Model use</dt>
            <dd>
              {run.input_tokens} in, {run.output_tokens ?? 0} out
            </dd>
          </>
        )}
        {snapshot.detail?.seconds_to_decision != null && (
          <>
            <dt>Time to decide</dt>
            <dd>{duration(snapshot.detail.seconds_to_decision)}</dd>
          </>
        )}
      </dl>
      {waiting > 0 && (
        <div className="row-actions">
          <Link className="button-link" to={`/approvals/${snapshot.runId}`}>
            Review {plural(waiting, 'draft')}
          </Link>
        </div>
      )}
    </aside>
  )
}
