import type { AuditFilter } from '../api/types'

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
