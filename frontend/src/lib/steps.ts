import type { Step } from '../api/types'

export interface TraceLine {
  id: number
  text: string
  state: 'done' | 'running' | 'failed' | 'retry'
}

type Detail = Record<string, unknown> | null

const str = (detail: Detail, key: string) => (detail && typeof detail[key] === 'string' ? (detail[key] as string) : '')
const num = (detail: Detail, key: string) => (detail && typeof detail[key] === 'number' ? (detail[key] as number) : 0)

function line(step: Step): string {
  const d = step.detail as Detail
  const tool = step.tool ?? ''
  switch (`${step.phase}:${step.state}`) {
    case 'analysing:start':
      return 'Starting the run'
    case 'analysing:end':
      if (tool === 'get_issue') return `Reading ${str(d, 'key') || 'the story'}`
      if (tool === 'search_issues') return `Looked at ${num(d, 'existing')} existing backlog items to avoid duplicates`
      return 'Reading your input'
    case 'generating:start':
      return num(d, 'attempt') > 1 ? 'Drafting again, with what was wrong' : 'Drafting with the model'
    case 'generating:retry':
      return `The model is busy (${num(d, 'code')}); trying again in ${num(d, 'wait_seconds')} s`
    case 'generating:end':
      return str(d, 'schema_error')
        ? 'The model reply was not in the expected shape'
        : `Drafted ${num(d, 'drafts')} ${num(d, 'drafts') === 1 ? 'item' : 'items'}`
    case 'verifying:start':
      return 'Checking each quote against your input'
    case 'verifying:end': {
      const problems = Array.isArray(d?.problems) ? d.problems.length : 0
      return problems
        ? `Kept ${num(d, 'kept')}; left out ${problems} that could not be traced to your input`
        : `All ${num(d, 'kept')} traced to your input`
    }
    case 'staging:start':
      return tool === 'finish_run' ? 'Finishing up' : `Saving draft: ${str(d, 'summary')}`
    case 'staging:end':
      return tool === 'finish_run' ? 'Ready for your review' : `Saved: ${str(d, 'summary')}`
    case 'staging:error':
      return `Refused "${str(d, 'summary')}": ${str(d, 'reason')}`
    default:
      return step.state === 'error' ? `Stopped: ${str(d, 'reason') || 'something went wrong'}` : step.phase
  }
}

/**
 * The steps of a run as short sentences. A step has a start and an end row; only the end, error and retry rows
 * are worth a line, plus the latest start when nothing has finished it yet (that is the thing happening now).
 */
export function traceLines(steps: Step[]): TraceLine[] {
  const lines: TraceLine[] = []
  steps.forEach((step, index) => {
    if (step.state === 'start') {
      const last = index === steps.length - 1
      if (last) lines.push({ id: step.id, text: line(step), state: 'running' })
      return
    }
    lines.push({
      id: step.id,
      text: line(step),
      state: step.state === 'error' ? 'failed' : step.state === 'retry' ? 'retry' : 'done',
    })
  })
  return lines
}
