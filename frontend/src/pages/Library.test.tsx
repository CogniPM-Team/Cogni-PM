import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Artifact } from '../api/types'
import { mockApi } from '../test/mockApi'
import Library from './Library'

const item = (key: string, over: Partial<Artifact> = {}): Artifact => ({
  issue_key: key,
  url: `https://x.atlassian.net/browse/${key}`,
  title: `Title of ${key}`,
  issue_type: 'Story',
  run_id: 'aaaaaaaa-1111',
  approved_by: 'human:reviewer',
  created_at: '2026-11-20T08:00:00Z',
  jira_state: 'found',
  jira_status: 'To Do',
  ...over,
})

const ITEMS = [
  item('MCP-1'),
  item('MCP-2', { jira_status: 'Done', issue_type: 'Task', run_id: 'bbbbbbbb-2222' }),
  item('MCP-3', { jira_state: 'missing', jira_status: null }),
]

function renderLibrary() {
  return render(
    <MemoryRouter>
      <Library />
    </MemoryRouter>,
  )
}

const keysShown = () => within(screen.getByRole('table')).getAllByRole('link', { name: /^MCP-/ }).map((l) => l.textContent)

describe('Library', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists what was created with its live Jira status, and links to Jira and to the run', async () => {
    mockApi({ 'GET /api/artifacts': { items: ITEMS, jira_reachable: true } })

    renderLibrary()

    expect(await screen.findByRole('link', { name: 'MCP-1' })).toHaveAttribute('href', 'https://x.atlassian.net/browse/MCP-1')
    expect(screen.getByText('Title of MCP-1')).toBeInTheDocument()
    const table = within(screen.getByRole('table')) // the same words are also filter choices above it
    expect(table.getByText('To Do')).toBeInTheDocument()
    expect(table.getByText('Done')).toBeInTheDocument()
    expect(screen.getAllByText('You')).toHaveLength(3)
    expect(screen.getAllByRole('link', { name: 'aaaaaaaa' })[0]).toHaveAttribute('href', '/approvals/aaaaaaaa-1111')
  })

  it('says plainly when Jira no longer has an issue we created', async () => {
    mockApi({ 'GET /api/artifacts': { items: ITEMS, jira_reachable: true } })

    renderLibrary()

    const gone = within(await screen.findByRole('table')).getByText('Not found in Jira')
    expect(gone).toHaveAttribute('title', expect.stringMatching(/deleted/))
    expect(gone.closest('tr')).toHaveTextContent('MCP-3')
  })

  it('still lists everything, with a notice, when Jira cannot be reached', async () => {
    mockApi({
      'GET /api/artifacts': {
        items: ITEMS.map((i) => ({ ...i, jira_state: 'unknown', jira_status: null })),
        jira_reachable: false,
      },
    })

    renderLibrary()

    expect(await screen.findByRole('status')).toHaveTextContent('Jira could not be reached')
    expect(keysShown()).toEqual(['MCP-1', 'MCP-2', 'MCP-3'])
    expect(screen.getAllByText('Unknown').length).toBeGreaterThanOrEqual(3)
  })

  it('filters by status, type and run, offers only values that exist, and clears', async () => {
    mockApi({ 'GET /api/artifacts': { items: ITEMS, jira_reachable: true } })
    const user = userEvent.setup()
    renderLibrary()
    await screen.findByRole('table')

    await user.selectOptions(screen.getByLabelText('Status'), 'Done')
    expect(keysShown()).toEqual(['MCP-2'])
    expect(screen.getByText('1 of 3')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await user.selectOptions(screen.getByLabelText('Type'), 'Task')
    expect(keysShown()).toEqual(['MCP-2'])

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await user.selectOptions(screen.getByLabelText('Run'), 'aaaaaaaa')
    expect(keysShown()).toEqual(['MCP-1', 'MCP-3'])

    expect(screen.queryByRole('option', { name: 'In Progress' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Status'), 'Done')
    expect(screen.getByText('No issues match these filters.')).toBeInTheDocument()
  })

  it('points at Approvals when nothing has been created', async () => {
    mockApi({ 'GET /api/artifacts': { items: [], jira_reachable: true } })

    renderLibrary()

    expect(await screen.findByText(/Nothing has been created yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Approvals' })).toHaveAttribute('href', '/approvals')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows an error with Try again when the library cannot be loaded', async () => {
    mockApi({})

    renderLibrary()

    expect(await screen.findByText('Could not load the library')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
