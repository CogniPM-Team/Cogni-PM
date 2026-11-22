import { Link } from 'react-router-dom'
import { duration, plural, TASK_NAMES } from '../lib/format'
import { StatusPill } from './Pills'
import type { Snapshot } from './RunProgress'

/** The newest task at a glance, as a slim strip above the run: where it stands and what is waiting on you. */
export default function TaskInspector({ snapshot }: { snapshot: Snapshot | null }) {
  if (!snapshot) return null

  const drafts = snapshot.detail?.drafts ?? []
  const created = drafts.filter((d) => d.status === 'applied').length
  const waiting = snapshot.status === 'awaiting_review' ? drafts.filter((d) => d.status === 'proposed').length : 0
  const run = snapshot.detail?.run

  const facts: [string, string | number][] = [
    ['Work so far', plural(snapshot.stepCount, 'step')],
    ['Drafted', drafts.length],
    ['Waiting for you', waiting],
    ['Created in Jira', created],
  ]
  if (run?.input_tokens != null) facts.push(['Model use', `${run.input_tokens} in, ${run.output_tokens ?? 0} out`])
  if (snapshot.detail?.seconds_to_decision != null) facts.push(['Time to decide', duration(snapshot.detail.seconds_to_decision)])

  return (
    <aside className="card inspector" aria-label="Task inspector">
      <div className="inspector-head">
        <h3>Latest task</h3>
        <span className="meta">{TASK_NAMES[snapshot.task] ?? snapshot.task}</span>
        <StatusPill status={snapshot.status} />
        {waiting > 0 && (
          <Link className="button-link small" to={`/approvals/${snapshot.runId}`}>
            Review {plural(waiting, 'draft')}
          </Link>
        )}
      </div>
      <dl>
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  )
}
