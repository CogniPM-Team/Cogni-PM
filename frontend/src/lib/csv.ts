import type { AuditRow } from '../api/types'

const COLUMNS: [string, (row: AuditRow) => unknown][] = [
  ['time', (r) => r.ts],
  ['run', (r) => r.run_id],
  ['actor', (r) => r.actor],
  ['mode', (r) => r.mode],
  ['action', (r) => r.action],
  ['outcome', (r) => r.outcome],
  ['detail', (r) => r.detail],
  ['before', (r) => (r.before ? JSON.stringify(r.before) : '')],
  ['after', (r) => (r.after ? JSON.stringify(r.after) : '')],
]

/**
 * One cell. Quotes are doubled, and a cell that a spreadsheet would read as a formula is defused with a leading
 * apostrophe: the detail text can contain words an agent or a document supplied.
 */
export function cell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value)
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function auditToCsv(rows: AuditRow[]): string {
  const header = COLUMNS.map(([name]) => name).join(',')
  const body = rows.map((row) => COLUMNS.map(([, pick]) => cell(pick(row))).join(','))
  return [header, ...body].join('\n') + '\n'
}
