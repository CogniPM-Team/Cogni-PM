import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import type { RunDetail } from '../api/types'
import { useFetch } from '../api/useFetch'
import { useRunEvents } from '../hooks/useRunEvents'
import { notifyRunsChanged } from '../lib/chatEvents'
import { plural, TASK_NAMES } from '../lib/format'
import { StatusPill } from './Pills'
import StepTrace from './StepTrace'

export interface Snapshot {
  runId: string
  task: string
  status: string
  stepCount: number
  detail: RunDetail | null
}

interface Props {
  runId: string
  task: string
  /** Only the newest run feeds the task inspector. */
  latest: boolean
  onSnapshot: (snapshot: Snapshot) => void
}

/** One run in the console: its steps as they happen, then a summary of what it drafted and a link to review it. */
export default function RunProgress({ runId, task, latest, onSnapshot }: Props) {
  const { steps, status } = useRunEvents(runId)
  const { data: detail } = useFetch<RunDetail>(status ? `/api/runs/${runId}` : null)
  const shown = detail?.run.status ?? status ?? 'running'

  useEffect(() => {
    notifyRunsChanged() // the task list shows where this run stands
  }, [shown])

  useEffect(() => {
    if (latest) onSnapshot({ runId, task, status: shown, stepCount: steps.length, detail: detail ?? null })
  }, [latest, onSnapshot, runId, task, shown, steps.length, detail])

  return (
    <article className="card run-item mode-M2" aria-label={`${TASK_NAMES[task] ?? task} run`}>
      <div className="run-item-head">
        <h3>{TASK_NAMES[task] ?? task}</h3>
        <StatusPill status={shown} />
      </div>
      <StepTrace steps={steps} />

      {detail && detail.run.status === 'failed' && (
        <p className="error">This run did not finish: {detail.run.comment ?? 'an unexpected error'}</p>
      )}
      {detail && detail.drafts.length > 0 && (
        <div className="proposal">
          <strong>
            {plural(detail.drafts.length, 'draft')} ready. Nothing has been created in Jira yet.
          </strong>
          <ul>
            {detail.drafts.map((draft) => (
              <li key={draft.id}>{(draft.effective as { summary?: string }).summary}</li>
            ))}
          </ul>
          <div className="row-actions">
            <Link className="button-link" to={`/approvals/${runId}`}>
              Review and approve
            </Link>
          </div>
        </div>
      )}
    </article>
  )
}
