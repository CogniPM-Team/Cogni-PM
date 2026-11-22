import { render, screen, waitFor, within } from '@testing-library/react'
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

    expect(await screen.findByRole('tab', { name: /Waiting/ })).toHaveTextContent('1') // the count rides on the tab
    expect(screen.getByRole('tab', { name: /Waiting/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/3 drafts/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review' })).toHaveAttribute('href', '/approvals/r-wait')
    expect(screen.queryByText('Approved')).not.toBeInTheDocument() // earlier runs are on the other tab

    await userEvent.click(screen.getByRole('tab', { name: 'History' }))

    expect(within(screen.getByRole('table')).getByText('Approved')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/approvals/r-done')
    expect(screen.queryByRole('link', { name: 'Review' })).not.toBeInTheDocument()
  })

  it('flags a run that has waited more than a day, and only that one', async () => {
    const old = new Date(Date.now() - 30 * 3600 * 1000).toISOString()
    const fresh = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    mockApi({
      'GET /api/runs': {
        waiting: [runSummary('old', { ready_at: old, scope: 'Old notes' }), runSummary('new', { ready_at: fresh, scope: 'New notes' })],
        past: [],
        awaiting_review_count: 2,
      },
    })

    render(
      <MemoryRouter>
        <Approvals />
      </MemoryRouter>,
    )

    const flagged = await screen.findAllByText('Waiting over a day')
    expect(flagged).toHaveLength(1)
    expect(flagged[0].closest('article')).toHaveTextContent('Old notes')
  })

  it('filters history by outcome and searches it by source, offering only outcomes that exist', async () => {
    mockApi({
      'GET /api/runs': {
        waiting: [],
        past: [
          runSummary('a', { status: 'applied', scope: 'Sprint notes' }),
          runSummary('b', { status: 'rejected', scope: 'Retro notes' }),
          runSummary('c', { status: 'applied', scope: 'MCP-4', task_type: 'p2' }),
        ],
        awaiting_review_count: 0,
      },
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Approvals />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('tab', { name: 'History' }))
    expect(screen.getAllByRole('link', { name: 'Open' })).toHaveLength(3)
    expect(screen.getByRole('option', { name: 'Approved' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Failed' })).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Outcome'), 'rejected')
    expect(screen.getAllByRole('link', { name: 'Open' })).toHaveLength(1)
    expect(screen.getByText('Retro notes')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Outcome'), 'all')
    await user.type(screen.getByRole('searchbox'), 'mcp-4')
    expect(screen.getAllByRole('link', { name: 'Open' })).toHaveLength(1)

    await user.clear(screen.getByRole('searchbox'))
    await user.type(screen.getByRole('searchbox'), 'zzz')
    expect(screen.getByText('No runs match.')).toBeInTheDocument()
  })

  it('says there is no history yet when there is none', async () => {
    mockApi({ 'GET /api/runs': { waiting: [], past: [], awaiting_review_count: 0 } })
    render(
      <MemoryRouter>
        <Approvals />
      </MemoryRouter>,
    )

    await userEvent.click(await screen.findByRole('tab', { name: 'History' }))

    expect(screen.getByText('No earlier runs yet.')).toBeInTheDocument()
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
