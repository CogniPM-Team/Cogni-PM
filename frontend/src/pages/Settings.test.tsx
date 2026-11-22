import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { jsonResponse, mockApi } from '../test/mockApi'
import Settings from './Settings'

const SETTINGS = {
  version: '0.1.0',
  jira_host: 'x.atlassian.net',
  jira_project: 'MCP',
  story_points_field_set: true,
  ai_model: 'gemini-3.6-flash',
  ai_key_set: true,
  max_items_per_run: 20,
  guardrails: [
    { name: 'required_fields', description: 'A draft needs a title.' },
    { name: 'max_items_per_run', description: 'Cap how many issues one run may stage.' },
  ],
  sent_to_model: ['Draft a backlog: the text you paste.', 'Your Jira API token and email address are never sent to the model.'],
}

const MODES = [
  { id: 'M1', name: 'Co-Pilot', tools: ['search_issues', 'get_issue'], can_stage_drafts: false, can_commit: false, tool_help: { search_issues: 'Search Jira issues by JQL.', get_issue: 'Read one issue.' } },
  { id: 'M2', name: 'Super-Pilot', tools: ['start_run'], can_stage_drafts: true, can_commit: false, tool_help: { start_run: 'Start a run.' } },
  { id: 'M3', name: 'Auto-Pilot', tools: ['commit_changes'], can_stage_drafts: true, can_commit: true, tool_help: { commit_changes: 'Create issues.' } },
]

function renderSettings() {
  return render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>,
  )
}

function api(over: Record<string, unknown> = {}) {
  return mockApi({ 'GET /api/settings': SETTINGS, 'GET /api/modes': MODES, ...over })
}

describe('Settings', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows every section: connections, modes, rules and limits, privacy, about', async () => {
    api()

    renderSettings()

    for (const name of ['Connections', 'What each mode can do', 'Rules and limits', 'Data and privacy', 'About']) {
      expect(await screen.findByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
    expect(screen.getByText('Site x.atlassian.net')).toBeInTheDocument()
    expect(screen.getByText('Model gemini-3.6-flash')).toBeInTheDocument()
    expect(screen.getByText('Key is set')).toBeInTheDocument()
    expect(screen.getByText(/version/)).toHaveTextContent('0.1.0')
  })

  it('lists what each mode can do, taken from the API, with Auto-Pilot marked not available', async () => {
    api()

    renderSettings()

    const modes = (await screen.findByRole('heading', { name: 'What each mode can do' })).closest('section')!
    expect(await within(modes).findByText('Only reads Jira. It cannot draft or create anything.')).toBeInTheDocument()
    expect(within(modes).getByText(/A person approves every one/)).toBeInTheDocument()
    expect(within(modes).getByText('Can create issues in Jira by itself.')).toBeInTheDocument()
    expect(within(modes).getByText('search_issues')).toBeInTheDocument()
    expect(within(modes).getByText('Not available yet')).toBeInTheDocument()
  })

  it('lists the rules and the limit on issues per run', async () => {
    api()

    renderSettings()

    const rules = (await screen.findByRole('heading', { name: 'Rules and limits' })).closest('section')!
    expect(within(rules).getByText('20 issues')).toBeInTheDocument()
    expect(within(rules).getByText(/these 2 rules/)).toBeInTheDocument()
    expect(within(rules).getByText('required fields')).toBeInTheDocument()
    expect(within(rules).getByText('A draft needs a title.')).toBeInTheDocument()
  })

  it('tells the person what is sent to the model', async () => {
    api()

    renderSettings()

    expect(await screen.findByText(/never sent to the model/)).toBeInTheDocument()
  })

  it('shows success when the Jira test passes', async () => {
    const calls = api({
      'POST /api/settings/test-jira': { ok: true, detail: 'Signed in as Ada. Project MCP is reachable.', problem: null },
    })
    const user = userEvent.setup()
    renderSettings()

    const jira = (await screen.findByRole('heading', { name: 'Jira' })).closest('.connection') as HTMLElement
    await user.click(within(jira).getByRole('button', { name: 'Test' }))

    expect(await within(jira).findByRole('status')).toHaveTextContent('Signed in as Ada')
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/api/settings/test-jira'])
  })

  it('shows the reason when the model test fails, such as no credit', async () => {
    api({
      'POST /api/settings/test-model': {
        ok: false,
        detail: null,
        problem: 'The model refused the request (429): the account is out of credit.',
      },
    })
    const user = userEvent.setup()
    renderSettings()

    const model = (await screen.findByRole('heading', { name: 'AI model' })).closest('.connection') as HTMLElement
    expect(within(model).getByText(/uses a few tokens/)).toBeInTheDocument() // said before the button is pressed
    await user.click(within(model).getByRole('button', { name: 'Test' }))

    expect(await within(model).findByRole('alert')).toHaveTextContent('out of credit')
  })

  it('says so when the test itself cannot run, and lets the person try again', async () => {
    api({ 'POST /api/settings/test-jira': jsonResponse({ detail: 'server fell over' }, 500) })
    const user = userEvent.setup()
    renderSettings()

    const jira = (await screen.findByRole('heading', { name: 'Jira' })).closest('.connection') as HTMLElement
    await user.click(within(jira).getByRole('button', { name: 'Test' }))

    expect(await within(jira).findByRole('alert')).toHaveTextContent('Could not run the test: server fell over')
    expect(within(jira).getByRole('button', { name: 'Test' })).toBeEnabled()
  })

  it('shows an error with Try again when the settings cannot be loaded', async () => {
    mockApi({}) // every call answers 404

    renderSettings()

    expect(await screen.findByText('Could not load the settings')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
  it('asks before deleting saved documents, then says how many were deleted', async () => {
    const calls = api({ 'DELETE /api/documents': { deleted: 3 } })
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Delete all saved documents' }))
    const ask = screen.getByRole('alertdialog')
    expect(ask).toHaveTextContent('Runs keep their own copy')
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)

    await user.click(within(ask).getByRole('button', { name: 'Yes, delete' }))

    expect(await screen.findByText('Deleted 3 documents.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(1)
  })

  it('warns what erasing past inputs costs, and can be cancelled', async () => {
    const calls = api({ 'POST /api/settings/clear-run-inputs': { deleted: 1 } })
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Erase the saved input of past runs' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('activity log stay')
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Erase the saved input of past runs' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Yes, delete' }))

    expect(await screen.findByText('Erased the saved input of 1 run.')).toBeInTheDocument()
  })

  it('shows the reason when erasing fails', async () => {
    api({ 'DELETE /api/documents': jsonResponse({ detail: 'database is busy' }, 500) })
    const user = userEvent.setup()
    renderSettings()

    await user.click(await screen.findByRole('button', { name: 'Delete all saved documents' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Yes, delete' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('database is busy')
  })
})
