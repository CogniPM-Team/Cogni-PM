import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { runSummary } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import Layout from './Layout'

const PROJECT = { key: 'MCP', jira_url: 'https://x.atlassian.net/browse/MCP', jira_host: 'x.atlassian.net' }

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<p>page content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('Layout', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('builds the sidebar from the nav config: sections and enabled pages only', async () => {
    mockApi({
      'GET /api/runs': { waiting: [], past: [], awaiting_review_count: 0 },
      'GET /api/project': PROJECT,
    })

    renderAt('/console')

    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(within(nav).getAllByRole('link').map((l) => l.textContent)).toEqual([
      'Home',
      'Agent console',
      'Approvals',
      'Library',
      'Activity log',
    ])
    expect(within(nav).getByRole('group', { name: 'work' })).toBeInTheDocument()
    expect(within(nav).getByRole('group', { name: 'record' })).toBeInTheDocument()
    // Settings sits apart, at the bottom of the sidebar
    expect(within(screen.getByRole('navigation', { name: 'System' })).getAllByRole('link').map((l) => l.textContent)).toEqual(['Settings'])
  })

  it('shows how many runs wait for you, on Approvals only', async () => {
    mockApi({
      'GET /api/runs': { waiting: [runSummary('r1')], past: [], awaiting_review_count: 3 },
      'GET /api/project': PROJECT,
    })

    renderAt('/approvals')

    const badge = await screen.findByLabelText('3 waiting for you')
    expect(badge.closest('a')).toHaveTextContent('Approvals')
    expect(screen.getAllByLabelText(/waiting for you/)).toHaveLength(1)
  })

  it('takes the page title and the Jira project from the config and the API', async () => {
    mockApi({
      'GET /api/runs': { waiting: [], past: [], awaiting_review_count: 0 },
      'GET /api/project': PROJECT,
    })

    renderAt('/activity')

    expect(await screen.findByRole('heading', { level: 1, name: 'Activity log' })).toBeInTheDocument()
    expect(await screen.findByText(/Jira · MCP/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in Jira' })).toHaveAttribute('href', PROJECT.jira_url)
    expect(screen.getByText('page content')).toBeInTheDocument()
  })

  it('marks the current page in the sidebar, and still works when the API is down', async () => {
    mockApi({}) // every call answers 404

    renderAt('/approvals')

    const current = await screen.findByRole('link', { name: 'Approvals' })
    expect(current).toHaveClass('active')
    expect(screen.getByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument()
    expect(screen.getByText(/Jira · not connected/)).toBeInTheDocument()
  })
})
