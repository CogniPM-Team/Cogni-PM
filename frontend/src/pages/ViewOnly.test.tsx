import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import SourcesTab from '../components/SourcesTab'
import TaskStarter from '../components/TaskStarter'
import { type Auth, AuthContext } from '../lib/auth'
import { mockApi } from '../test/mockApi'
import Settings from './Settings'

// A developer can look at everything but change nothing. The server refuses every change; these tests check that the
// page does not even offer what would be refused, while a PM is offered all of it.
const as = (role: 'pm' | 'developer'): Auth => ({
  user: { id: 'u1', email: 'x@example.com', display_name: 'Sam', role, disabled: false },
  canChange: role === 'pm',
  signOut: async () => {},
})

const show = (role: 'pm' | 'developer', ui: React.ReactElement) =>
  render(
    <AuthContext.Provider value={as(role)}>
      <MemoryRouter>{ui}</MemoryRouter>
    </AuthContext.Provider>,
  )

const DOC = { id: 'd1', title: 'Notes', kind: 'notes', filename: null, char_count: 10, created_at: '2026-11-20T08:00:00Z', updated_at: '2026-11-20T08:00:00Z', used_in_runs: 0 }
const SETTINGS = {
  version: '0.1.0', jira_host: 'x.atlassian.net', jira_project: 'MCP', story_points_field_set: true, ai_model: 'm', ai_key_set: true,
  max_items_per_run: 20, guardrails: [], sent_to_model: [],
}

describe('what a developer is offered', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('cannot start a task, and is told why', async () => {
    mockApi({ 'GET /api/documents': [] })
    const user = userEvent.setup()
    show('developer', <TaskStarter onStarted={() => {}} />)
    await user.type(screen.getByRole('textbox', { name: /Requirements or meeting notes/ }), 'some notes')

    const start = screen.getByRole('button', { name: 'Start the task' })
    expect(start).toBeDisabled()
    expect(start).toHaveAttribute('title', 'Only a PM can start a task')
  })

  it('a PM can start the same task', async () => {
    mockApi({ 'GET /api/documents': [] })
    const user = userEvent.setup()
    show('pm', <TaskStarter onStarted={() => {}} />)
    await user.type(screen.getByRole('textbox', { name: /Requirements or meeting notes/ }), 'some notes')

    expect(screen.getByRole('button', { name: 'Start the task' })).toBeEnabled()
  })

  it('cannot run the connection tests or erase stored data from Settings', async () => {
    mockApi({ 'GET /api/settings': SETTINGS, 'GET /api/modes': [] })
    show('developer', <Settings />)

    await screen.findByRole('heading', { name: 'Connections' })
    for (const test of screen.getAllByRole('button', { name: 'Test' })) expect(test).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Delete all saved documents' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Erase the saved input of past runs' })).toBeDisabled()
  })

  it('can read saved documents but is not offered a way to add, rename or delete them', async () => {
    mockApi({ 'GET /api/documents': [DOC] })
    show('developer', <SourcesTab />)

    expect(await screen.findByText('Notes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add a document' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rename' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('a PM is offered all of it', async () => {
    mockApi({ 'GET /api/documents': [DOC] })
    show('pm', <SourcesTab />)

    expect(await screen.findByRole('button', { name: 'Add a document' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rename' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })
})
