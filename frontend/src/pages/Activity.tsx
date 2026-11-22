import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiUrl } from '../api/client'
import type { AuditFilter, AuditPage, AuditRow } from '../api/types'
import { useFetch } from '../api/useFetch'
import Icon from '../components/Icon'
import { EmptyState, ErrorState, PageHeader, Tabs } from '../components/PageParts'
import { auditParams } from '../lib/audit'
import { actionLabel, actorLabel, ago, describeDetail, formatTime, MODE_NAMES } from '../lib/format'
import { tabPanelProps } from '../lib/tabs'

const FILTERS: { id: AuditFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'changed_jira', label: 'Changed Jira' },
  { id: 'needs_you', label: 'Needs you' },
  { id: 'rejected', label: 'Rejected or refused' },
  { id: 'advice_only', label: 'Advice only' },
]

const LIMIT = 500 // the most the API returns for the list; the export has no limit
const COLUMNS = 7

function Row({ row, open, onToggle }: { row: AuditRow; open: boolean; onToggle: () => void }) {
  const hasMore = Boolean(row.detail || row.before || row.after)
  return (
    <>
      <tr
        className={hasMore ? 'row-click' : undefined}
        onClick={(event) => {
          if (hasMore && !(event.target as HTMLElement).closest('a, button')) onToggle()
        }}
      >
        <td>
          <time dateTime={row.ts} title={ago(row.ts)}>
            {formatTime(row.ts)}
          </time>
        </td>
        <td>{actorLabel(row.actor)}</td>
        <td>{actionLabel(row.action)}</td>
        <td>{row.mode ? (MODE_NAMES[row.mode] ?? row.mode) : ''}</td>
        <td>
          {row.run_id && (
            <Link className="chip" to={`/approvals/${row.run_id}`}>
              {row.run_id.slice(0, 8)}
            </Link>
          )}
        </td>
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
          <td colSpan={COLUMNS}>
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
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('') // the search as sent: it follows what is typed after a short pause
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => setQ(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const query = { filter, q, from, to }
  const narrowed = q.trim() !== '' || from !== '' || to !== ''
  const { data, error, loading, reload } = useFetch<AuditPage>(`/api/audit?${auditParams(query, { limit: String(LIMIT) })}`)

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

  function clear() {
    setSearch('')
    setQ('')
    setFrom('')
    setTo('')
  }

  return (
    <>
      <PageHeader description="Every step an agent took and every decision you made, newest first. Entries cannot be changed or deleted." />
      <Tabs
        label="Filter"
        tabs={FILTERS.map((f) => ({ id: f.id, label: f.label }))}
        value={filter}
        onChange={(id) => setFilter(id as AuditFilter)}
      />
      <div {...tabPanelProps(filter)}>
        <div className="toolbar">
          <div className="filters">
            <input
              type="search"
              aria-label="Search the log"
              placeholder="Search the log"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label>
              From <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label>
              To <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
            </label>
            {(narrowed || search !== '') && (
              <button type="button" className="small" onClick={clear}>
                Clear
              </button>
            )}
            <label>
              <input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} /> Group by run
            </label>
          </div>
          <a className="button-link small with-icon" href={apiUrl(`/api/audit/export.csv?${auditParams(query)}`)} download>
            Export everything
            <Icon name="download" size={14} />
          </a>
        </div>
        {loading && <p className="muted">Loading...</p>}
        {error && <ErrorState title="Could not load the activity log" message={error.message} onRetry={reload} />}
        {data && rows.length === 0 && (
          <EmptyState>{narrowed ? 'Nothing matches your search and dates.' : 'Nothing matches this filter yet.'}</EmptyState>
        )}
        {rows.length >= LIMIT && (
          <p className="meta">Showing the newest {LIMIT}. Export everything downloads all of the matching entries.</p>
        )}
        {rows.length > 0 && (
          <div className="card">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>What</th>
                  <th>Mode</th>
                  <th>Run</th>
                  <th>Outcome</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {grouped
                  ? [...byRun].map(([runId, runRows]) => (
                      <Fragment key={runId || 'none'}>
                        <tr>
                          <th colSpan={COLUMNS} style={{ textTransform: 'none', letterSpacing: 0 }}>
                            {runId ? (
                              <>
                                Run{' '}
                                <Link className="chip" to={`/approvals/${runId}`}>
                                  {runId.slice(0, 8)}
                                </Link>
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
      </div>
    </>
  )
}
