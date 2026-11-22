import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AuditFilter, AuditPage, AuditRow } from '../api/types'
import { useFetch } from '../api/useFetch'
import { auditToCsv } from '../lib/csv'
import { actionLabel, actorLabel, describeDetail, formatTime, MODE_NAMES } from '../lib/format'

const FILTERS: { id: AuditFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'changed_jira', label: 'Changed Jira' },
  { id: 'needs_you', label: 'Needs you' },
  { id: 'rejected', label: 'Rejected or refused' },
  { id: 'advice_only', label: 'Advice only' },
]

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
}

function Row({ row, open, onToggle }: { row: AuditRow; open: boolean; onToggle: () => void }) {
  const hasMore = Boolean(row.detail || row.before || row.after)
  return (
    <>
      <tr>
        <td>{formatTime(row.ts)}</td>
        <td>{actorLabel(row.actor)}</td>
        <td>{actionLabel(row.action)}</td>
        <td>{row.mode ? (MODE_NAMES[row.mode] ?? row.mode) : ''}</td>
        <td className={`outcome-${row.outcome}`}>{row.outcome}</td>
        <td>
          {hasMore && (
            <button type="button" className="link" aria-expanded={open} onClick={onToggle}>
              {open ? 'Hide' : 'Details'}
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="activity-detail">
          <td colSpan={6}>
            {row.detail && (
              <p style={{ margin: 0 }}>
                {(describeDetail(row.action, row.detail) ?? [row.detail]).map((part, index) =>
                  typeof part === 'string' ? (
                    part
                  ) : (
                    <span key={index} className="tag mono" title={part.title}>
                      {part.pill}
                    </span>
                  ),
                )}
              </p>
            )}
            {row.before && <pre>Before: {JSON.stringify(row.before, null, 2)}</pre>}
            {row.after && <pre>After: {JSON.stringify(row.after, null, 2)}</pre>}
          </td>
        </tr>
      )}
    </>
  )
}

export default function Activity() {
  const [filter, setFilter] = useState<AuditFilter>('all')
  const [grouped, setGrouped] = useState(false)
  const [open, setOpen] = useState<Set<number>>(new Set())
  const { data, error, loading } = useFetch<AuditPage>(`/api/audit?filter=${filter}&limit=500`)

  const rows = data?.rows ?? []
  const byRun = new Map<string, AuditRow[]>()
  if (grouped) for (const row of rows) byRun.set(row.run_id ?? '', [...(byRun.get(row.run_id ?? '') ?? []), row])

  const toggle = (id: number) =>
    setOpen((previous) => {
      const next = new Set(previous)
      if (!next.delete(id)) next.add(id)
      return next
    })
  const renderRow = (row: AuditRow) => <Row key={row.id} row={row} open={open.has(row.id)} onToggle={() => toggle(row.id)} />

  return (
    <>
      <p className="page-subtitle">
        Every step an agent took and every decision you made, newest first. Entries cannot be changed or deleted.
      </p>
      <div className="tabs" role="tablist" aria-label="Filter">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" role="tab" aria-selected={filter === f.id} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <label>
          <input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} /> Group by run
        </label>
        <button
          type="button"
          className="small"
          disabled={rows.length === 0}
          onClick={() => download(`cognipm-activity-${filter}.csv`, auditToCsv(rows))}
        >
          Export CSV
        </button>
      </div>

      {loading && <p className="muted">Loading...</p>}
      {error && <p className="error">Could not load the activity log: {error.message}</p>}
      {data && rows.length === 0 && <p className="empty">Nothing matches this filter yet.</p>}
      {rows.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Mode</th>
                <th>Outcome</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {grouped
                ? [...byRun].map(([runId, runRows]) => (
                    <Fragment key={runId || 'none'}>
                      <tr>
                        <th colSpan={6} style={{ textTransform: 'none', letterSpacing: 0 }}>
                          {runId ? (
                            <>
                              Run <Link to={`/approvals/${runId}`}>{runId.slice(0, 8)}</Link>
                            </>
                          ) : (
                            'Not part of a run'
                          )}
                        </th>
                      </tr>
                      {runRows.map(renderRow)}
                    </Fragment>
                  ))
                : rows.map(renderRow)}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
