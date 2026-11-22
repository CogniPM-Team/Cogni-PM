import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiUrl } from '../api/client'
import type { AuditFilter, AuditPage, AuditRow } from '../api/types'
import { useFetch } from '../api/useFetch'
import Icon from '../components/Icon'
import { EmptyState, ErrorState, PageHeader, Tabs } from '../components/PageParts'
import { auditParams, groupByRun, type LogItem, runTitle } from '../lib/audit'
import { actionLabel, actorLabel, ago, describeDetail, formatTime, MODE_NAMES, plural } from '../lib/format'
import { tabPanelProps } from '../lib/tabs'

const FILTERS: { id: AuditFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'changed_jira', label: 'Changed Jira' },
  { id: 'needs_you', label: 'Needs you' },
  { id: 'rejected', label: 'Rejected or refused' },
  { id: 'advice_only', label: 'Advice only' },
]

const LIMIT = 500 // the most the API returns for the list; the export has no limit

const hasMore = (row: AuditRow) => Boolean(row.detail || row.before || row.after)

/** What an entry recorded in more detail: the note, and for an edit what it changed from and to. */
function Detail({ row }: { row: AuditRow }) {
  return (
    <>
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
    </>
  )
}

/** One step inside a run. */
function StepRow({ row, open, onToggle }: { row: AuditRow; open: boolean; onToggle: () => void }) {
  const more = hasMore(row)
  return (
    <>
      <tr
        className={more ? 'row-click' : undefined}
        onClick={(event) => {
          if (more && !(event.target as HTMLElement).closest('a, button')) onToggle()
        }}
      >
        <td>
          <time dateTime={row.ts} title={ago(row.ts)}>
            {formatTime(row.ts)}
          </time>
        </td>
        <td>{actorLabel(row.actor)}</td>
        <td className="key">{actionLabel(row.action)}</td>
        <td className={`outcome-${row.outcome}`}>{row.outcome}</td>
        <td>
          {more && (
            <button type="button" className="link" aria-expanded={open} onClick={onToggle}>
              {open ? 'Hide' : 'Details'}
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="activity-detail">
          <td colSpan={5}>
            <Detail row={row} />
          </td>
        </tr>
      )}
    </>
  )
}

/**
 * One line of the log. A run is one line with its entries as the details; open it to read them in order. An entry that
 * belongs to no run (a chat answer, a deleted document) is a line of its own.
 */
function LogLine({
  item,
  open,
  onToggle,
  openSteps,
  onToggleStep,
}: {
  item: LogItem
  open: boolean
  onToggle: () => void
  openSteps: Set<number>
  onToggleStep: (id: number) => void
}) {
  const newest = item.rows[0]
  const isRun = item.runId !== null
  const expandable = isRun || hasMore(newest)
  const title = isRun ? runTitle(item.rows) : actionLabel(newest.action)
  const mode = newest.mode ? (MODE_NAMES[newest.mode] ?? newest.mode) : ''
  const exception = newest.outcome === 'refused' || newest.outcome === 'failed'

  return (
    <div className={`log-item${open ? ' open' : ''}`}>
      <div
        className={`log-line${expandable ? '' : ' static'}`}
        onClick={(event) => {
          if (expandable && !(event.target as HTMLElement).closest('a, button')) onToggle()
        }}
      >
        {expandable ? (
          <button type="button" className="log-toggle" aria-expanded={open} onClick={onToggle}>
            <Icon name="chevron" size={16} />
            <span className="log-title">{title}</span>
            {isRun && <span className="meta">{plural(item.rows.length, 'entry', 'entries')}</span>}
          </button>
        ) : (
          <div className="log-toggle">
            <span className="log-title">{title}</span>
          </div>
        )}
        <span className="log-run">
          {item.runId && (
            <Link className="id-chip" to={`/approvals/${item.runId}`}>
              {item.runId.slice(0, 8)}
            </Link>
          )}
        </span>
        <span className="log-mode">{mode}</span>
        <span className={`log-latest${exception ? ` outcome-${newest.outcome}` : ''}`}>
          {isRun ? `Latest: ${actionLabel(newest.action)}` : actorLabel(newest.actor)}
        </span>
        <time className="log-when" dateTime={newest.ts} title={formatTime(newest.ts)}>
          {ago(newest.ts)}
        </time>
      </div>

      {open &&
        (isRun ? (
          <div className="log-body">
            <table className="data-table actions-end">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>What</th>
                  <th>Outcome</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {[...item.rows].reverse().map((row) => (
                  <StepRow key={row.id} row={row} open={openSteps.has(row.id)} onToggle={() => onToggleStep(row.id)} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="log-body">
            <Detail row={newest} />
          </div>
        ))}
    </div>
  )
}

export default function Activity() {
  const [filter, setFilter] = useState<AuditFilter>('all')
  const [openItems, setOpenItems] = useState<Set<string>>(new Set())
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set())
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
  const items = groupByRun(rows)

  const flip = <T,>(setter: React.Dispatch<React.SetStateAction<Set<T>>>, value: T) =>
    setter((previous) => {
      const next = new Set(previous)
      if (!next.delete(value)) next.add(value)
      return next
    })

  function clear() {
    setSearch('')
    setQ('')
    setFrom('')
    setTo('')
  }

  return (
    <>
      <PageHeader description="Each run is one line, with everything that happened in it inside. Entries cannot be changed or deleted." />
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
        {items.length > 0 && (
          <div className="card log-list">
            <div className="log-line log-heads" aria-hidden="true">
              <span>Run or entry</span>
              <span>Run</span>
              <span>Mode</span>
              <span>Latest</span>
              <span>When</span>
            </div>
            {items.map((item) => (
              <LogLine
                key={item.key}
                item={item}
                open={openItems.has(item.key)}
                onToggle={() => flip(setOpenItems, item.key)}
                openSteps={openSteps}
                onToggleStep={(id) => flip(setOpenSteps, id)}
              />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
