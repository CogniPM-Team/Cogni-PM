import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { runSummary } from '../test/fixtures'
import { jsonResponse, mockApi } from '../test/mockApi'
import Home from './Home'

const PROJECT = { key: 'MCP', jira_url: 'https://x.atlassian.net/browse/MCP', jira_host: 'x.atlassian.net' }
const NO_RUNS = { waiting: [], past: [], awaiting_review_count: 0 }
const NO_CHATS = { folders: [], sessions: [] }
const ONE_CHAT = {
  folders: [],
  sessions: [{ id: 'c1', title: 'Hi', folder_id: null, message_count: 2, created_at: '2026-11-20T08:00:00Z', updated_at: '2026-11-20T08:00:00Z' }],
}
const ROW = {
  id: 1,
  ts: '2026-11-22T10:15:00Z',
  actor: 'orchestrator:gemini-3.6-flash',
  action: 'run_started',
  mode: 'M2',
  outcome: 'ok',
  detail: null,
  before: null,
  after: null,
  run_id: 'run-9',
}

function Where() {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/home']}>
      <Routes>
        <Route path="/home" element={<Home />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

function api(over: Record<string, unknown> = {}) {
  return mockApi({
    'GET /api/runs': NO_RUNS,
    'GET /api/project': PROJECT,
    'GET /api/chat/sessions': NO_CHATS,
    'GET /api/audit': { filter: 'all', rows: [] },
    ...over,
  })
}

describe('Home', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('shows the runs waiting for you, oldest first as the API sends them, each with a Review link', async () => {
    api({
      'GET /api/runs': {
        waiting: [runSummary('r1', { scope: 'Meeting notes' }), runSummary('r2', { task_type: 'p2', scope: 'MCP-4' })],
        past: [],
        awaiting_review_count: 2,
      },
    })

    renderHome()

    const section = (await screen.findByRole('heading', { name: 'Needs you' })).closest('section')!
    const links = await within(section).findAllByRole('link', { name: 'Review' })
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/approvals/r1', '/approvals/r2'])
    expect(within(section).getByText('Meeting notes')).toBeInTheDocument()
    expect(within(section).getByText('Break down a story')).toBeInTheDocument()
  })

  it('offers to retry a failed run that still has drafts, and ignores finished ones', async () => {
    api({
      'GET /api/runs': {
        waiting: [],
        past: [
          runSummary('bad', { status: 'failed', draft_count: 3 }),
          runSummary('empty', { status: 'failed', draft_count: 0 }),
          runSummary('done', { status: 'applied' }),
        ],
        awaiting_review_count: 0,
      },
    })

    renderHome()

    const link = await screen.findByRole('link', { name: 'Open to retry' })
    expect(link).toHaveAttribute('href', '/approvals/bad')
    expect(screen.getAllByRole('link', { name: /Review|Open to retry/ })).toHaveLength(1)
  })

  it('says nothing is waiting when it is not', async () => {
    api()

    renderHome()

    expect(await screen.findByText('Nothing is waiting.')).toBeInTheDocument()
  })

  it('opens the console in the right place from each Start button', async () => {
    api()
    const user = userEvent.setup()
    renderHome()

    await user.click(await screen.findByRole('link', { name: /Draft a backlog/ }))
    expect(screen.getByTestId('where')).toHaveTextContent('/console?mode=M2')
  })

  it.each([
    ['Break down a story', '/console?mode=M2&task=p2'],
    ['Ask the Co-Pilot', '/console'],
  ])('%s goes to %s', async (name, target) => {
    api()
    const user = userEvent.setup()
    renderHome()

    await user.click(await screen.findByRole('link', { name: new RegExp(name) }))
    expect(screen.getByTestId('where').textContent).toBe(target)
  })

  it('lists the last few actions in plain words, linking to the run, with the exact time on hover', async () => {
    api({ 'GET /api/audit': { filter: 'all', rows: [ROW, { ...ROW, id: 2, run_id: null, action: 'chat_answered' }] } })

    renderHome()

    const section = (await screen.findByRole('heading', { name: 'Recently' })).closest('section')!
    const rows = await within(section).findAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', '/approvals/run-9')
    expect(within(rows[1]).queryByRole('link')).not.toBeInTheDocument()
    expect(rows[0].querySelector('time')).toHaveAttribute('title', expect.stringMatching(/2026/))
    expect(within(section).getByRole('link', { name: 'See the whole activity log' })).toHaveAttribute('href', '/activity')
  })

  it('ticks the checklist from what already exists', async () => {
    api({ 'GET /api/chat/sessions': ONE_CHAT, 'GET /api/runs': { ...NO_RUNS, waiting: [runSummary('r1')] } })

    renderHome()

    const list = (await screen.findByRole('heading', { name: 'Getting started' })).closest('section')!
    const done = (label: string) => within(list).getByText(label).closest('li')!.className === 'done'
    expect(done('Connect Jira')).toBe(true)
    expect(done('Ask the Co-Pilot a question')).toBe(true)
    expect(done('Run a first draft')).toBe(true)
    expect(within(list).getByRole('link', { name: 'Approve a draft into Jira' })).toHaveAttribute('href', '/approvals')
  })

  it('shows a brand-new user the whole checklist with a link for each next step', async () => {
    api({ 'GET /api/project': jsonResponse({ detail: 'down' }, 503) })

    renderHome()

    const list = (await screen.findByRole('heading', { name: 'Getting started' })).closest('section')!
    expect(within(list).getAllByRole('listitem')).toHaveLength(4)
    expect(within(list).getAllByRole('link')).toHaveLength(3) // Jira has no link: it is set up in .env
  })

  it('drops the checklist once everything is done', async () => {
    api({
      'GET /api/chat/sessions': ONE_CHAT,
      'GET /api/runs': { ...NO_RUNS, waiting: [runSummary('r1')] },
      'GET /api/audit': { filter: 'all', rows: [ROW] },
    })

    renderHome()

    await screen.findByRole('link', { name: 'Review' }) // the page has loaded
    expect(screen.queryByRole('heading', { name: 'Getting started' })).not.toBeInTheDocument()
  })

  it('remembers Hide in the browser', async () => {
    api()
    const user = userEvent.setup()
    const { unmount } = renderHome()

    await user.click(await screen.findByRole('button', { name: 'Hide' }))
    expect(screen.queryByRole('heading', { name: 'Getting started' })).not.toBeInTheDocument()

    unmount()
    renderHome()
    await screen.findByText('Nothing is waiting.')
    expect(screen.queryByRole('heading', { name: 'Getting started' })).not.toBeInTheDocument()
  })

  it('shows an error with Try again when the API is down, instead of a blank page', async () => {
    mockApi({}) // every call answers 404

    renderHome()

    expect(await screen.findByText('Could not load your runs')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Try again' }).length).toBeGreaterThan(0)
  })
})
