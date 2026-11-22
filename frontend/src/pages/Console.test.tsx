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
    expect(calls.filter((c) => c.method === 'POST')[1].body).toEqual({ message: 'And open ones?', session_id: 's1' })
  })

  it('shows the answer with its formatting, and a spinner while the Co-Pilot is working', async () => {
    let finish: (value: Response) => void = () => {}
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => (finish = resolve))))
    const user = userEvent.setup()
    renderConsole()

    await user.type(screen.getByLabelText('Your question'), 'how many tasks?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByRole('status')).toHaveTextContent('The Co-Pilot is looking at Jira')
    expect(screen.getByRole('button', { name: 'Working...' })).toBeDisabled()

    finish(
      jsonResponse({
        session_id: 's1',
        answer: 'There are **0** issues of type **Task**.\n* **Stories:** 12\n* **Epic:** 1',
        tool_calls: [],
      }),
    )

    expect(await screen.findByText('0', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Stories:', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument() // no raw asterisks left on screen
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

  it('opens on the task named in the address, so Home can link straight to "Break down a story"', async () => {
    mockApi({ 'GET /api/stories': [{ key: 'MCP-4', summary: 'Add OAuth login flow', status: 'To Do', url: 'u' }] })
    render(
      <MemoryRouter initialEntries={['/console?mode=M2&task=p2']}>
        <AgentConsole />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: /Break down a story/ })).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByRole('radio', { name: /MCP-4/ })).toBeInTheDocument()
  })
  const SAVED = { id: 'd1', title: 'Sprint notes', kind: 'notes', filename: null, char_count: 20, created_at: '2026-11-20T08:00:00Z', updated_at: '2026-11-20T08:00:00Z', used_in_runs: 0 }

  it('fills the form from a document chosen in the library, and sends which one it came from', async () => {
    const calls = mockApi({
      'GET /api/documents': [SAVED],
      'GET /api/documents/d1': { ...SAVED, text: 'Payroll moves to Q3.' },
      'POST /api/runs': jsonResponse({ run_id: 'run-9' }, 202),
      'GET /api/runs/run-9': runDetail('run-9', { drafts: [] }),
    })
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))
    await user.selectOptions(await screen.findByLabelText('Choose from your library'), 'd1')
    expect(await screen.findByDisplayValue('Payroll moves to Q3.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start the task' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ task: 'p1', input_text: 'Payroll moves to Q3.', document_id: 'd1' }),
    )
  })

  it('opens on the document named in the address, from the Library button', async () => {
    mockApi({ 'GET /api/documents': [SAVED], 'GET /api/documents/d1': { ...SAVED, text: 'Payroll moves to Q3.' } })
    render(
      <MemoryRouter initialEntries={['/console?mode=M2&document=d1']}>
        <AgentConsole />
      </MemoryRouter>,
    )

    expect(await screen.findByDisplayValue('Payroll moves to Q3.')).toBeInTheDocument()
    expect(screen.getByLabelText('Choose from your library')).toHaveValue('d1')
  })

  it('saves pasted text as a document, and then links the run to it', async () => {
    const calls = mockApi({
      'GET /api/documents': [],
      'POST /api/documents': { ...SAVED, text: 'Payroll moves to Q3.' },
      'POST /api/runs': jsonResponse({ run_id: 'run-9' }, 202),
      'GET /api/runs/run-9': runDetail('run-9', { drafts: [] }),
    })
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))
    expect(screen.queryByRole('button', { name: 'Save as document' })).not.toBeInTheDocument() // nothing to save yet
    await user.type(screen.getByRole('textbox', { name: /Requirements or meeting notes/ }), 'Payroll moves to Q3.')
    await user.click(screen.getByRole('button', { name: 'Save as document' }))
    await user.type(screen.getByLabelText('Document title'), 'Sprint notes')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Saved to your library as Sprint notes.')).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/api/documents' && c.method === 'POST')?.body).toEqual({ title: 'Sprint notes', text: 'Payroll moves to Q3.' })

    await user.click(screen.getByRole('button', { name: 'Start the task' }))
    await waitFor(() => expect(calls.find((c) => c.path === '/api/runs' && c.method === 'POST')?.body).toMatchObject({ document_id: 'd1' }))
  })

  it('forgets the link to a document when its text is cleared', async () => {
    const calls = mockApi({
      'GET /api/documents': [SAVED],
      'GET /api/documents/d1': { ...SAVED, text: 'Q3' },
      'POST /api/runs': jsonResponse({ run_id: 'run-9' }, 202),
      'GET /api/runs/run-9': runDetail('run-9', { drafts: [] }),
    })
    const user = userEvent.setup()
    renderConsole()

    await user.click(screen.getByRole('button', { name: /Super-Pilot/ }))
    await user.selectOptions(await screen.findByLabelText('Choose from your library'), 'd1')
    const notes = screen.getByRole('textbox', { name: /Requirements or meeting notes/ })
    await user.clear(notes)
    await user.type(notes, 'Something else entirely')
    await user.click(screen.getByRole('button', { name: 'Start the task' }))

    await waitFor(() => expect(calls.find((c) => c.path === '/api/runs' && c.method === 'POST')?.body).toMatchObject({ document_id: null }))
  })
})
