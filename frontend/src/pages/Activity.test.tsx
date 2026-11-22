import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { AuditRow } from '../api/types'
import { mockApi } from '../test/mockApi'
import Activity from './Activity'

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

// Newest first, as the API sends them: a run's four entries, then a chat answer that belongs to no run.
const RUN = [
  row(5, { action: 'approve', outcome: 'applied', detail: '2 issue(s) created' }),
  row(4, { action: 'edit_draft', outcome: 'edited', detail: 'changed summary', before: { summary: 'old' }, after: { summary: 'new' } }),
  row(3, { action: 'propose_backlog_item', outcome: 'staged', actor: 'orchestrator:gemini', detail: null }),
  row(2, { action: 'start_run', outcome: 'ok', actor: 'orchestrator:gemini', detail: null }),
]
const CHAT = row(1, { run_id: null, mode: 'M1', action: 'chat_turn', outcome: 'answered', actor: 'orchestrator:gemini:chat', detail: 'session abc; 2 read(s)' })

const show = () =>
  render(
    <MemoryRouter>
      <Activity />
    </MemoryRouter>,
  )

const requested = () => (fetch as unknown as { mock: { calls: [string][] } }).mock.calls.map(([url]) => url)
const lastAudit = () => requested().filter((u) => u.startsWith('/api/audit?')).at(-1)!

describe('Activity log', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows each run as one line, and an entry with no run as a line of its own', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: [...RUN, CHAT] } })

    show()

    expect(await screen.findByRole('button', { name: /Draft backlog/ })).toHaveTextContent('4 entries')
    expect(screen.getByText('Latest: Approved')).toBeInTheDocument()
    expect(screen.getByText('Answered a question')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Group by run/ })).not.toBeInTheDocument() // grouping is how it is shown
    expect(screen.queryByText('Edited a draft')).not.toBeInTheDocument() // the steps are inside, until opened
  })

  it('opens a run to show its entries in the order they happened, and closes it again', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: RUN } })
    const user = userEvent.setup()
    show()

    const toggle = await screen.findByRole('button', { name: /Draft backlog/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const steps = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(steps.map((r) => within(r).getAllByRole('cell')[2].textContent)).toEqual([
      'Started a run',
      'Drafted a backlog item',
      'Edited a draft',
      'Approved',
    ]) // oldest first, so it reads as the story of the run

    await user.click(toggle)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('opens the run when its row is pressed anywhere, but not when the run link is', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: RUN } })
    const user = userEvent.setup()
    show()
    const toggle = await screen.findByRole('button', { name: /Draft backlog/ })

    await user.click(screen.getByText('Latest: Approved'))
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    const chip = screen.getByRole('link', { name: 'run-1' })
    expect(chip).toHaveClass('chip')
    expect(chip).toHaveAttribute('href', '/approvals/run-1')
    await user.click(chip)
    expect(toggle).toHaveAttribute('aria-expanded', 'true') // the link followed its address, it did not toggle the row
  })

  it('reveals the detail of a step inside a run on request', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: RUN } })
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: /Draft backlog/ }))
    expect(screen.queryByText('changed summary')).not.toBeInTheDocument()

    const edit = screen.getByText('Edited a draft').closest('tr')!
    await user.click(within(edit).getByRole('button', { name: 'Details' }))

    expect(screen.getByText('changed summary')).toBeInTheDocument()
    expect(screen.getByText(/Before:/)).toBeInTheDocument()
    expect(screen.getAllByText('You').length).toBeGreaterThan(0)
  })

  it('opens a stand-alone entry to show its note, and gives it no run link', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: [CHAT] } })
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: /Answered a question/ }))

    expect(screen.getByText(/2 read/)).toBeInTheDocument() // the note, with the session shown as a tag
    expect(document.querySelector('a.chip')).toBeNull() // no run, so no run link
  })

  it('shows an entry that has nothing more to say as a plain line with nothing to open', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: [{ ...CHAT, detail: null }] } })

    show()

    expect(await screen.findByText('Answered a question')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Answered a question/ })).not.toBeInTheDocument()
  })

  it('points out a run whose latest entry is a refusal, and only then', async () => {
    mockApi({
      'GET /api/audit': {
        filter: 'all',
        rows: [row(9, { run_id: 'bad', action: 'guardrail:no_duplicate', outcome: 'refused' }), ...RUN],
      },
    })

    show()

    const latest = await screen.findByText('Latest: Refused by no duplicate')
    expect(latest).toHaveClass('outcome-refused')
    expect(screen.getByText('Latest: Approved')).not.toHaveClass('outcome-refused')
  })

  it('asks the server for the chosen filter', async () => {
    mockApi({ 'GET /api/audit': { filter: 'changed_jira', rows: [row(1, { action: 'create_issue', outcome: 'created' })] } })
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('tab', { name: 'Changed Jira' }))
    await screen.findByText('Latest: Created a Jira issue')

    expect(lastAudit()).toContain('filter=changed_jira')
  })

  it('searches after a pause in typing and narrows by date, in the viewer own time zone', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: RUN } })
    const user = userEvent.setup()
    show()
    await screen.findByText('Latest: Approved')

    await user.type(screen.getByRole('searchbox'), 'invoices')
    await waitFor(() => expect(lastAudit()).toContain('q=invoices'))

    await user.type(screen.getByLabelText('From'), '2026-11-18')
    const params = new URLSearchParams(lastAudit().split('?')[1])
    expect(new Date(params.get('from')!).getTime()).toBe(new Date(2026, 10, 18).getTime())
    expect(params.get('limit')).toBe('500')
  })

  it('clears the search and the dates in one click, and says so when nothing matches them', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: [] } })
    const user = userEvent.setup()
    show()
    await screen.findByText('Nothing matches this filter yet.')
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument()

    await user.type(screen.getByRole('searchbox'), 'zzz')
    expect(await screen.findByText('Nothing matches your search and dates.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByRole('searchbox')).toHaveValue('')
    expect(await screen.findByText('Nothing matches this filter yet.')).toBeInTheDocument()
    expect(lastAudit()).not.toContain('q=')
  })

  it('exports everything that matches, through the server, with the same filters as the list', async () => {
    mockApi({ 'GET /api/audit': { filter: 'rejected', rows: RUN } })
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('tab', { name: 'Rejected or refused' }))
    await user.type(screen.getByRole('searchbox'), 'invoices')
    await waitFor(() => expect(lastAudit()).toContain('q=invoices'))

    const href = screen.getByRole('link', { name: 'Export everything' }).getAttribute('href')!

    expect(href.startsWith('/api/audit/export.csv?')).toBe(true)
    expect(href).toContain('filter=rejected')
    expect(href).toContain('q=invoices')
    expect(href).not.toContain('limit') // the export has no 500-row cap
  })

  it('tells you when the list is cut off, so the export is the way to get the rest', async () => {
    mockApi({ 'GET /api/audit': { filter: 'all', rows: Array.from({ length: 500 }, (_, n) => row(n + 1, { run_id: null })) } })

    show()

    expect(await screen.findByText(/Showing the newest 500/)).toBeInTheDocument()
  })

  it('shows an error with Try again when the log cannot be loaded', async () => {
    mockApi({})

    show()

    expect(await screen.findByText('Could not load the activity log')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
