import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { AuditRow } from '../api/types'
import { runSummary } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import Activity from './Activity'
import Approvals from './Approvals'

describe('Approvals', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('puts runs waiting for you first and lists earlier ones with their outcome', async () => {
    mockApi({
      'GET /api/runs': {
        waiting: [runSummary('r-wait', { draft_count: 3 })],
        past: [runSummary('r-done', { status: 'applied', draft_count: 2 })],
        awaiting_review_count: 1,
      },
    })

    render(
      <MemoryRouter>
        <Approvals />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: '1 waiting for you' })).toBeInTheDocument()
    expect(screen.getByText(/3 drafts/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review' })).toHaveAttribute('href', '/approvals/r-wait')
    expect(screen.getByText('Approved')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/approvals/r-done')
  })

  it('points at the console when nothing is waiting', async () => {
    mockApi({ 'GET /api/runs': { waiting: [], past: [], awaiting_review_count: 0 } })

    render(
      <MemoryRouter>
        <Approvals />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/Nothing is waiting/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Agent console' })).toHaveAttribute('href', '/console')
  })
})

const row = (id: number, over: Partial<AuditRow> = {}): AuditRow => ({
  id,
  ts: '2026-11-20T08:00:00Z',
  run_id: 'run-1',
  actor: 'human:reviewer',
  mode: 'M2',
  action: 'approve',
  outcome: 'applied',
  detail: '2 issue(s) created',
  before: null,
  after: null,
  ...over,
})

describe('Activity log', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows who did what in plain words, and reveals the detail on request', async () => {
    mockApi({
      'GET /api/audit': {
        filter: 'all',
        rows: [row(2, { action: 'edit_draft', outcome: 'edited', detail: 'changed summary', before: { summary: 'old' }, after: { summary: 'new' } }), row(1)],
      },
    })
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <Activity />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Edited a draft')).toBeInTheDocument()
    expect(screen.getAllByText('You')).toHaveLength(2)
    expect(screen.queryByText(/changed summary/)).not.toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Details' })[0])
    expect(screen.getByText('changed summary')).toBeInTheDocument()
    expect(screen.getByText(/Before:/)).toBeInTheDocument()
  })

  it('asks the server for the chosen filter and offers a CSV of what is on screen', async () => {
    const calls = mockApi({
      'GET /api/audit': { filter: 'changed_jira', rows: [row(1, { action: 'create_issue', outcome: 'created' })] },
    })
    const create = vi.fn(() => 'blob:csv')
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: vi.fn() })
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <Activity />
      </MemoryRouter>,
    )
    await user.click(await screen.findByRole('tab', { name: 'Changed Jira' }))
    await screen.findByText('Created a Jira issue')
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))

    expect(calls.some((c) => c.path === '/api/audit')).toBe(true)
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
  })
})
