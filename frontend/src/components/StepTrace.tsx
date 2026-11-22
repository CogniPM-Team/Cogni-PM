import type { Step } from '../api/types'
import { traceLines } from '../lib/steps'
import Spinner from './Spinner'

const STATE_WORDS = { done: 'done', running: 'in progress', failed: 'failed', retry: 'retrying' }

/** What a run is doing, one plain sentence per step, live while the run is working. */
export default function StepTrace({ steps }: { steps: Step[] }) {
  const lines = traceLines(steps)
  if (lines.length === 0) return <p className="muted">Starting...</p>
  return (
    <ol className="trace" aria-label="Steps so far">
      {lines.map((line) => (
        <li key={line.id} className={line.state}>
          {line.state === 'running' ? <Spinner /> : <span className="dot" aria-hidden="true" />}
          <span>
            {line.text}
            <span className="sr-only"> ({STATE_WORDS[line.state]})</span>
          </span>
        </li>
      ))}
    </ol>
  )
}
