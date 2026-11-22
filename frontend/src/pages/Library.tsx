import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { Artifact, ArtifactList } from '../api/types'
import { useFetch } from '../api/useFetch'
import { EmptyState, ErrorState, PageHeader, Tabs } from '../components/PageParts'
import SourcesTab from '../components/SourcesTab'
import { actorLabel, ago, formatTime } from '../lib/format'
import { tabPanelProps } from '../lib/tabs'

const MISSING = 'Not found in Jira'
const UNKNOWN = 'Unknown'

/** The status to show and filter on: Jira's own, or a plain reason why we have none. */
function statusOf(item: Artifact): string {
  if (item.jira_state === 'found') return item.jira_status ?? UNKNOWN
  return item.jira_state === 'missing' ? MISSING : UNKNOWN
}

const unique = (values: string[]) => [...new Set(values)].sort()

function CreatedIssues() {
  const { data, error, loading, reload } = useFetch<ArtifactList>('/api/artifacts')
  const [status, setStatus] = useState('')
  const [type, setType] = useState('')
  const [run, setRun] = useState('')

  if (loading) return <p className="muted">Loading...</p>
  if (error || !data) return <ErrorState title="Could not load the library" message={error?.message} onRetry={reload} />

  const items = data.items
  const shown = items.filter(
    (i) => (!status || statusOf(i) === status) && (!type || i.issue_type === type) && (!run || i.run_id === run),
  )
  const filtering = status !== '' || type !== '' || run !== ''

  return (
    <>
      {!data.jira_reachable && (
        <p className="notice warning" role="status">
          Jira could not be reached, so current statuses are unknown. Your own record below is still complete.
        </p>
      )}

      {items.length === 0 ? (
        <EmptyState>
          Nothing has been created yet. Approve a draft in <Link to="/approvals">Approvals</Link> and it appears here.
        </EmptyState>
      ) : (
        <>
          <div className="toolbar">
            <div className="filters">
              <label>
                Status{' '}
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">All</option>
                  {unique(items.map(statusOf)).map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                Type{' '}
                <select value={type} onChange={(e) => setType(e.target.value)}>
                  <option value="">All</option>
                  {unique(items.map((i) => i.issue_type)).map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label>
                Run{' '}
                <select value={run} onChange={(e) => setRun(e.target.value)}>
                  <option value="">All</option>
                  {unique(items.map((i) => i.run_id)).map((r) => (
                    <option key={r} value={r}>
                      {r.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              {filtering && (
                <button
                  type="button"
                  className="small"
                  onClick={() => {
                    setStatus('')
                    setType('')
                    setRun('')
                  }}
                >
                  Clear
                </button>
              )}
            </div>
            <span className="meta">
              {shown.length === items.length ? `${items.length} created` : `${shown.length} of ${items.length}`}
            </span>
          </div>

          {shown.length === 0 ? (
            <EmptyState>No issues match these filters.</EmptyState>
          ) : (
            <div className="card">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Type</th>
                    <th>Status in Jira</th>
                    <th>Created</th>
                    <th>Approved by</th>
                    <th>Run</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((item) => (
                    <tr key={item.issue_key}>
                      <td className="key">
                        <a href={item.url} target="_blank" rel="noopener noreferrer" className="id-chip">
                          {item.issue_key}
                        </a>
                        <div>{item.title}</div>
                      </td>
                      <td>{item.issue_type}</td>
                      <td>
                        <span
                          className={`tag${item.jira_state === 'found' ? '' : ' overdue'}`}
                          title={
                            item.jira_state === 'missing'
                              ? 'Jira no longer lists this issue: it may have been deleted or its label removed.'
                              : item.jira_state === 'unknown'
                                ? 'Jira could not tell us.'
                                : undefined
                          }
                        >
                          {statusOf(item)}
                        </span>
                      </td>
                      <td>
                        {item.created_at && (
                          <time dateTime={item.created_at} title={ago(item.created_at)}>
                            {formatTime(item.created_at)}
                          </time>
                        )}
                      </td>
                      <td>{item.approved_by ? actorLabel(item.approved_by) : ''}</td>
                      <td>
                        <Link className="id-chip" to={`/approvals/${item.run_id}`}>
                          {item.run_id.slice(0, 8)}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  )
}

type LibraryTab = 'created' | 'sources'

export default function Library() {
  // The tab is in the address (?tab=sources), so it survives a refresh and Settings or Home can link straight to it.
  const [params, setParams] = useSearchParams()
  const tab: LibraryTab = params.get('tab') === 'sources' ? 'sources' : 'created'

  return (
    <>
      <PageHeader
        description={
          tab === 'sources'
            ? 'The notes and requirements you saved to draft from.'
            : 'Every issue CogniPM has created in Jira, with its status in Jira right now.'
        }
      />
      <Tabs
        label="Library"
        prefix="library"
        value={tab}
        onChange={(id) => setParams(id === 'sources' ? { tab: 'sources' } : {}, { replace: true })}
        tabs={[
          { id: 'created', label: 'Created issues' },
          { id: 'sources', label: 'Sources' },
        ]}
      />
      <div {...tabPanelProps(tab, 'library')}>{tab === 'sources' ? <SourcesTab /> : <CreatedIssues />}</div>
    </>
  )
}
