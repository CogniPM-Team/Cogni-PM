import { Link } from 'react-router-dom'
import type { RunSummary } from '../api/types'
import { ago, plural, TASK_NAMES, waitingOverADay } from '../lib/format'
import Icon from './Icon'
import { ModePill } from './Pills'

/**
 * A run that needs a decision, as a card you can press anywhere. Each fact has its own icon (where it came from, how
 * many drafts, how long it has waited) so the card reads at a glance. Narrow on Home; `wide` lays the same parts out
 * in one row for the Approvals inbox, where there is room and a list is quicker to scan than a grid.
 */
export default function RunCard({ run, retry = false, wide = false }: { run: RunSummary; retry?: boolean; wide?: boolean }) {
  const story = run.task_type === 'p2'
  const asking = run.status === 'waiting_for_information'
  const overdue = run.ready_at !== null && waitingOverADay(run.ready_at)
  return (
    <article className={`run-card clickable mode-${run.mode}${wide ? ' wide' : ''}`}>
      <div className="run-card-top">
        <ModePill mode={run.mode} />
        {overdue && (
          <span className="tag overdue with-icon-tag">
            <Icon name="clock" size={12} />
            Waiting over a day
          </span>
        )}
      </div>
      <div className="run-card-title">
        <span className="task-badge" aria-hidden="true">
          <Icon name={story ? 'branch' : 'list'} size={18} />
        </span>
        <h3>{TASK_NAMES[run.task_type] ?? run.task_type}</h3>
      </div>
      <ul className="facts">
        <li>
          <Icon name={story ? 'bookmark' : 'file'} size={16} />
          <span>{run.scope}</span>
        </li>
        {asking ? (
          <li className="late">
            <Icon name="info" size={16} />
            <span>The agent has a question</span>
          </li>
        ) : (
          <li>
            <Icon name="layers" size={16} />
            <span>{plural(run.draft_count, 'draft')}</span>
          </li>
        )}
        {run.ready_at && (
          <li className={overdue ? 'late' : undefined}>
            <Icon name="clock" size={16} />
            <span>Waiting {ago(run.ready_at)}</span>
          </li>
        )}
        {retry && (
          <li className="warn">
            <Icon name="alert" size={16} />
            <span>Did not finish creating everything</span>
          </li>
        )}
      </ul>
      <Link className="button-link small with-icon stretch" to={`/approvals/${run.id}`}>
        {retry ? 'Open to retry' : asking ? 'Answer' : 'Review'}
        <Icon name="arrow" size={14} />
      </Link>
    </article>
  )
}
