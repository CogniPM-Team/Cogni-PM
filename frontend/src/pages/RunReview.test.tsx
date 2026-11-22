import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { draft, RESET, runDetail, NOTES, step } from '../test/fixtures'
import { jsonResponse, mockApi } from '../test/mockApi'
import RunReview from './RunReview'

function renderReview() {
  return render(
    <MemoryRouter initialEntries={['/approvals/run-1']}>
      <Routes>
        <Route path="/approvals/:id" element={<RunReview />} />
        <Route path="/approvals/:id/other" element={<p>elsewhere</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RunReview', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows every draft with its reasoning and quotes, and nothing is ticked to begin with', async () => {
    mockApi({ 'GET /api/runs/run-1': runDetail() })

    renderReview()

    expect(await screen.findByRole('heading', { name: 'Password reset' })).toBeInTheDocument()
    expect(screen.queryByText('The notes ask for this directly.')).not.toBeInTheDocument() // the reasons wait to be opened
    await userEvent.click(screen.getAllByRole('button', { name: 'Why the agent drafted this' })[0])
    expect(screen.getByText('The notes ask for this directly.')).toBeInTheDocument()
    // only the second draft states an assumption, and its amber tab is how the reviewer finds it
    const flagged = screen.getAllByRole('button', { name: 'Check this assumption' })
    expect(flagged).toHaveLength(1)
    await userEvent.click(flagged[0])
    expect(screen.getByText('Logs are kept for 90 days')).toBeInTheDocument()
    expect(screen.getAllByRole('checkbox').every((box) => !(box as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByRole('button', { name: 'Approve and create' })).toBeDisabled() // no approve-all shortcut
  })

  it('highlights each cited quote inside the original input', async () => {
    mockApi({ 'GET /api/runs/run-1': runDetail() })

    renderReview()

    const pane = await screen.findByLabelText('Original input')
    const marks = within(pane).getAllByText((_, element) => element?.tagName === 'MARK')
    expect(marks.map((m) => m.textContent)).toEqual([RESET, 'Admins need an audit trail.'])
    expect(pane).toHaveTextContent(NOTES)
  })

  it('approves only the drafts that were ticked, after one explicit confirmation', async () => {
    const detail = runDetail()
    const calls = mockApi({
      'GET /api/runs/run-1': detail,
      'POST /api/runs/run-1/approve': { run_id: 'run-1', status: 'applied', created: [], dropped: ['d2'] },
    })
    const user = userEvent.setup()
    renderReview()

    await user.click(await screen.findByRole('checkbox', { name: 'Create "Password reset" in Jira' }))
    await user.click(screen.getByRole('button', { name: 'Approve and create 1 issue' }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false) // nothing is sent before the confirmation
    expect(screen.getByRole('alertdialog')).toHaveTextContent('The other 1 will be left out, not created.')
    await user.click(screen.getByRole('button', { name: 'Yes, create them' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ change_ids: ['d1'] }))
  })

  it('says exactly what was and was not created when Jira failed part-way', async () => {
    const problem = {
      message: 'stopped at draft d2: Jira returned 400',
      created: [{ change_id: 'd1', issue_key: 'MCP-15', url: 'u', recovered: false }],
      not_created: ['d2'],
    }
    mockApi({
      'GET /api/runs/run-1': runDetail(),
      'POST /api/runs/run-1/approve': jsonResponse({ detail: problem }, 502),
    })
    const user = userEvent.setup()
    renderReview()

    await user.click((await screen.findAllByRole('checkbox'))[0])
    await user.click(screen.getByRole('button', { name: /Approve and create/ }))
    await user.click(screen.getByRole('button', { name: 'Yes, create them' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('stopped at draft d2: Jira returned 400')
    expect(alert).toHaveTextContent('Created: MCP-15')
    expect(alert).toHaveTextContent('Not created: 1 draft')
    expect(alert).toHaveTextContent('Nothing is created twice')
  })

  it('lets the PM edit a draft, and shows the agent original beside the change', async () => {
    const edited = draft('d1', 'Reset by email', RESET, {
      edited_payload: { summary: 'Reset by email' },
      payload: { summary: 'Password reset', issue_type: 'Story', description: 'x', acceptance_criteria: ['It works as described'], labels: [] },
    })
    const calls = mockApi({
      'GET /api/runs/run-1': runDetail(),
      'PATCH /api/changes/d1': edited,
    })
    const user = userEvent.setup()
    renderReview()

    await user.click((await screen.findAllByRole('button', { name: 'Edit before approving' }))[0])
    const title = screen.getByLabelText('Title')
    await user.clear(title)
    await user.type(title, 'Reset by email')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({ summary: 'Reset by email' }))
  })

  it('needs a note before it asks the agent to try again, and keeps a rejection note as feedback', async () => {
    const calls = mockApi({
      'GET /api/runs/run-1': runDetail(),
      'POST /api/runs/run-1/reject': { run_id: 'run-1', status: 'rejected' },
    })
    const user = userEvent.setup()
    renderReview()

    await user.click(await screen.findByRole('button', { name: 'Regenerate' }))
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Reject' }))
    await user.type(screen.getByRole('textbox'), 'Too vague')
    await user.click(screen.getByRole('button', { name: 'Reject this run' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ comment: 'Too vague' }))
  })

  it('is read-only once a run is decided, and links the created issues into Jira', async () => {
    mockApi({
      'GET /api/runs/run-1': runDetail('run-1', {
        can_decide: false,
        editable: false,
        status_note: 'Approved. The issues were created in Jira; this run is closed.',
        seconds_to_decision: 95,
        drafts: [
          draft('d1', 'Password reset', RESET, { status: 'applied', created_issue_key: 'MCP-15', issue_url: 'https://x/browse/MCP-15' }),
          draft('d2', 'Login audit', NOTES, { status: 'rejected' }),
        ],
        run: { ...runDetail().run, status: 'applied' },
      }),
    })

    renderReview()

    expect(await screen.findByText('Created in Jira:')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'MCP-15' })[0]).toHaveAttribute('href', 'https://x/browse/MCP-15')
    const all = screen.getByRole('link', { name: 'Open all created issues in Jira' })
    expect(all.getAttribute('href')).toMatch(/^https:\/\/x\/issues\/\?jql=key%20in%20\(MCP-15\)/)
    expect(screen.getByRole('link', { name: 'Start another task' })).toHaveAttribute('href', '/console?mode=M2')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Approve/ })).not.toBeInTheDocument()
    expect(screen.getByText('Time to decide')).toBeInTheDocument()
  })
  it('splits the run into Drafts, Steps and History tabs, and keeps what you ticked when you switch', async () => {
    mockApi({
      'GET /api/runs/run-1': runDetail('run-1', {
        steps: [step(1, 'analysing', 'start'), step(2, 'generating', 'start', { detail: { attempt: 1 } })],
      }),
      'GET /api/audit': {
        filter: 'all',
        rows: [
          { id: 2, ts: '2026-11-20T08:02:00Z', run_id: 'run-1', actor: 'human:reviewer', mode: 'M2', action: 'approve', outcome: 'applied', detail: '2 issue(s) created', before: null, after: null },
          { id: 1, ts: '2026-11-20T08:00:00Z', run_id: 'run-1', actor: 'orchestrator:gemini', mode: 'M2', action: 'start_run', outcome: 'ok', detail: null, before: null, after: null },
        ],
      },
    })
    const user = userEvent.setup()
    renderReview()

    await user.click((await screen.findAllByRole('checkbox'))[0])
    await user.click(screen.getByRole('tab', { name: 'Steps' }))
    expect(await screen.findByRole('list', { name: 'Steps so far' })).toHaveTextContent('Drafting with the model')
    expect(screen.getByText(/593 tokens in and 373 out/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Password reset' })).not.toBeInTheDocument() // hidden from view, but not gone (see the tick below)

    await user.click(screen.getByRole('tab', { name: 'History' }))
    expect(await screen.findByText('2 issue(s) created')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Drafts/ }))
    expect((await screen.findAllByRole('checkbox'))[0]).toBeChecked()
  })

  it('shows an empty History when nothing was recorded', async () => {
    mockApi({ 'GET /api/runs/run-1': runDetail(), 'GET /api/audit': { filter: 'all', rows: [] } })
    const user = userEvent.setup()
    renderReview()

    await user.click(await screen.findByRole('tab', { name: 'History' }))

    expect(await screen.findByText('Nothing has been recorded for this run yet.')).toBeInTheDocument()
  })

  it('goes back to where you came from, or to Approvals when opened directly', async () => {
    mockApi({ 'GET /api/runs/run-1': runDetail() })
    const user = userEvent.setup()
    const { unmount } = render(
      <MemoryRouter initialEntries={['/home', '/approvals/run-1']} initialIndex={1}>
        <Routes>
          <Route path="/home" element={<p>the home page</p>} />
          <Route path="/approvals" element={<p>the approvals page</p>} />
          <Route path="/approvals/:id" element={<RunReview />} />
        </Routes>
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('link', { name: 'Back' }))
    expect(screen.getByText('the home page')).toBeInTheDocument()
    unmount()

    render(
      <MemoryRouter initialEntries={['/approvals/run-1']}>
        <Routes>
          <Route path="/approvals" element={<p>the approvals page</p>} />
          <Route path="/approvals/:id" element={<RunReview />} />
        </Routes>
      </MemoryRouter>,
    )
    await user.click(await screen.findByRole('link', { name: 'Back' }))
    expect(screen.getByText('the approvals page')).toBeInTheDocument()
  })
})
