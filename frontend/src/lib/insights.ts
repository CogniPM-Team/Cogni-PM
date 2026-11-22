import type { Insights } from '../api/types'
import { localDay } from './audit'

export interface InsightsQuery {
  from: string
  to: string
  task: '' | 'p1' | 'p2'
}

/**
 * The query shared by the page and the download, so a file always matches what is on screen. The two days are the
 * viewer's own days, sent as exact times; "to" is the end of that day (the API's end is exclusive).
 */
export function insightsParams({ from, to, task }: InsightsQuery): string {
  const params = new URLSearchParams()
  if (from) params.set('from', localDay(from))
  if (to) params.set('to', localDay(to, 1))
  if (task) params.set('task', task)
  return params.toString()
}

/** "3 of 12": the count with what it is out of. With nothing to divide by there is no percentage to show. */
export function share(part: number, whole: number): { text: string; percent: string } {
  if (whole === 0) return { text: '', percent: '–' }
  return { text: `${part} of ${whole}`, percent: `${Math.round((100 * part) / whole)}%` }
}

/** Below this many decided runs the rates are too few to read, and the page says so. */
export const TOO_FEW = 5

export const REPORT_PARTS = (n: Insights) => [
  { id: 'written', label: 'Created as the agent wrote it', value: n.drafts_created_as_written },
  { id: 'edited', label: 'Created after you edited it', value: n.drafts_created_after_edit },
  { id: 'left-out', label: 'Left out', value: n.drafts_left_out },
]
