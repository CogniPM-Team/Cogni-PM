import type { AuditFilter, AuditRow } from '../api/types'

export interface AuditQuery {
  filter: AuditFilter
  q: string
  /** A day, as a date input gives it: "2026-11-18". */
  from: string
  to: string
}

/** The start of a day (or the day after it) in the viewer's own time zone, as the instant the API compares with. */
function localDay(day: string, plusDays = 0): string {
  const date = new Date(`${day}T00:00:00`)
  date.setDate(date.getDate() + plusDays)
  return date.toISOString()
}

/**
 * The query string shared by the list and the export, so what you see is what you download. "To" is the end of that
 * day: the API's end is exclusive, so it is sent as the start of the next day.
 */
export function auditParams({ filter, q, from, to }: AuditQuery, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ filter, ...extra })
  if (q.trim()) params.set('q', q.trim())
  if (from) params.set('from', localDay(from))
  if (to) params.set('to', localDay(to, 1))
  return params.toString()
}

/** One line of the activity log: a whole run with its entries, or a single entry that belongs to no run. */
export interface LogItem {
  /** Stable across reloads: the run's id, or "entry-<id>". */
  key: string
  runId: string | null
  /** Newest first, as the API sends them. */
  rows: AuditRow[]
}

/**
 * Group entries by run, keeping the order of the newest entry in each group (so the run with the latest activity is
 * first). An entry with no run stands alone: a chat answer, a deleted document.
 */
export function groupByRun(rows: AuditRow[]): LogItem[] {
  const items: LogItem[] = []
  const runs = new Map<string, LogItem>()
  for (const row of rows) {
    if (!row.run_id) {
      items.push({ key: `entry-${row.id}`, runId: null, rows: [row] })
      continue
    }
    let item = runs.get(row.run_id)
    if (!item) {
      item = { key: row.run_id, runId: row.run_id, rows: [] }
      runs.set(row.run_id, item)
      items.push(item)
    }
    item.rows.push(row)
  }
  return items
}

/** What a run was for, read from what its agent did. The log does not store the task, so this is the best we can say. */
export function runTitle(rows: AuditRow[]): string {
  const actions = new Set(rows.map((r) => r.action))
  if (actions.has('propose_backlog_item')) return 'Draft backlog'
  if (actions.has('propose_task_breakdown')) return 'Break down a story'
  return 'Run'
}
