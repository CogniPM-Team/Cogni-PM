import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { draft, RESET, runDetail, step } from '../test/fixtures'
import { FakeEventSource, jsonResponse, mockApi } from '../test/mockApi'
import AgentConsole from './AgentConsole'

function renderConsole() {
  return render(
    <MemoryRouter>
      <AgentConsole />
    </MemoryRouter>,
  )
}

describe('Agent console', () => {
  beforeEach(() => vi.stubGlobal('EventSource', FakeEventSource))
  afterEach(() => vi.unstubAllGlobals())

  it('offers the three modes, with Auto-Pilot shown but not yet available', () => {
    renderConsole()

    expect(screen.getByRole('button', { name: /Co-Pilot/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Super-Pilot/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Auto-Pilot/ })).toBeDisabled()
  })

  it('answers a question in the Co-Pilot and remembers the conversation', async () => {
    const calls = mockApi({
      'POST /api/chat': { session_id: 's1', answer: 'The project has 14 issues.', tool_calls: ['search_issues({})'] },
    })
    const user = userEvent.setup()
    renderConsole()

    await user.type(screen.getByLabelText('Your question'), 'How many issues?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(/The project has 14 issues/)).toBeInTheDocument()
    expect(screen.getByText('Read Jira 1 time')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Your question'), 'And open ones?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(2))
    expect(calls[1].body).toEqual({ message: 'And open ones?', session_id: 's1' })
  })

  it('will not start a task without input, and says plainly that nothing reaches Jira until approval', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))

    expect(screen.getByText(/nothing is created in Jira/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start the task' })).toBeDisabled()
    await user.type(screen.getByLabelText('Requirements or meeting notes'), 'Customers want password reset.')
    expect(screen.getByRole('button', { name: 'Start the task' })).toBeEnabled()
  })

  it('starts a draft run, follows its steps live, then offers the review once drafts are ready', async () => {
    const calls = mockApi({
      'POST /api/runs': jsonResponse({ run_id: 'run-9' }, 202),
      'GET /api/runs/run-9': runDetail('run-9', { drafts: [draft('d1', 'Password reset', RESET)] }),
    })
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))
    await user.type(screen.getByLabelText('Requirements or meeting notes'), 'Customers want password reset.')
    await user.click(screen.getByRole('button', { name: 'Start the task' }))

    expect(await screen.findByRole('article', { name: 'Draft backlog run' })).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ task: 'p1', input_text: 'Customers want password reset.' })
    expect(FakeEventSource.last.url).toBe('/api/runs/run-9/events')

    FakeEventSource.last.emit('step', step(1, 'analysing', 'start'))
    FakeEventSource.last.emit('step', step(2, 'generating', 'start', { detail: { attempt: 1 } }))
    expect(await screen.findByText(/Drafting with the model/)).toBeInTheDocument()

    FakeEventSource.last.emit('end', { status: 'awaiting_review' })

    const run = screen.getByRole('article', { name: 'Draft backlog run' })
    expect(await within(run).findByText(/1 draft ready. Nothing has been created in Jira yet./)).toBeInTheDocument()
    expect(within(run).getByRole('link', { name: 'Review and approve' })).toHaveAttribute('href', '/approvals/run-9')
    expect(screen.getByLabelText('Task inspector')).toHaveTextContent('Waiting for you')
  })

  it('shows why a run failed instead of leaving the page waiting', async () => {
    mockApi({
      'POST /api/runs': jsonResponse({ run_id: 'run-9' }, 202),
      'GET /api/runs/run-9': runDetail('run-9', {
        drafts: [],
        run: { ...runDetail().run, status: 'failed', comment: 'ClientError: 402 credits depleted' },
      }),
    })
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))
    await user.type(screen.getByLabelText('Requirements or meeting notes'), 'Notes')
    await user.click(screen.getByRole('button', { name: 'Start the task' }))
    await screen.findByRole('article', { name: 'Draft backlog run' })
    FakeEventSource.last.emit('end', { status: 'failed' })

    expect(await screen.findByText(/This run did not finish: ClientError: 402 credits depleted/)).toBeInTheDocument()
  })

  it('lists open stories to break down and sends the chosen one', async () => {
    const calls = mockApi({
      'GET /api/stories': [{ key: 'MCP-4', summary: 'Add OAuth login flow', status: 'To Do', url: 'u' }],
      'POST /api/runs': jsonResponse({ run_id: 'run-9' }, 202),
      'GET /api/runs/run-9': runDetail('run-9', { drafts: [] }),
    })
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))
    await user.click(screen.getByRole('button', { name: /Break down a story/ }))
    expect(screen.getByRole('button', { name: 'Start the task' })).toBeDisabled()
    await user.click(await screen.findByRole('radio', { name: /MCP-4/ }))
    await user.click(screen.getByRole('button', { name: 'Start the task' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ task: 'p2', story_key: 'MCP-4' }))
  })
})
