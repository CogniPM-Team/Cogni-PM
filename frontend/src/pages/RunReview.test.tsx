import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { draft, RESET, runDetail, NOTES } from '../test/fixtures'
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
    expect(screen.getAllByText('The notes ask for this directly.')).toHaveLength(2)
    expect(screen.getByText('Check this assumption')).toBeInTheDocument() // the second draft states one
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
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Approve/ })).not.toBeInTheDocument()
    expect(screen.getByText('Time to decide')).toBeInTheDocument()
  })
})
