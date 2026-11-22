import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  beforeEach(() => localStorage.clear())
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
  const quiet = () =>
    mockApi({ 'GET /api/runs': { waiting: [], past: [], awaiting_review_count: 0 }, 'GET /api/project': PROJECT })

  it('draws an icon beside every page, hidden from screen readers so the label is read once', async () => {
    quiet()

    renderAt('/home')

    const links = [...within(await screen.findByRole('navigation', { name: 'Main' })).getAllByRole('link')]
    links.push(...within(screen.getByRole('navigation', { name: 'System' })).getAllByRole('link'))
    expect(links).toHaveLength(6)
    for (const link of links) expect(link.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
  })

  it('collapses to icons only and expands again, keeping every page reachable by its name', async () => {
    quiet()
    const user = userEvent.setup()
    const { container } = renderAt('/home')
    const toggle = await screen.findByRole('button', { name: 'Collapse' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(container.querySelector('.app')).not.toHaveClass('collapsed')

    await user.click(toggle)

    expect(container.querySelector('.app')).toHaveClass('collapsed')
    const expand = screen.getByRole('button', { name: 'Expand the sidebar' })
    expect(expand).toHaveAttribute('aria-expanded', 'false')
    // the labels are still there for assistive technology, and a tooltip names each page for everyone else
    expect(screen.getByRole('link', { name: 'Approvals' })).toHaveAttribute('title', 'Approvals')
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument()

    await user.click(expand)

    expect(container.querySelector('.app')).not.toHaveClass('collapsed')
    expect(screen.getByRole('link', { name: 'Approvals' })).not.toHaveAttribute('title')
  })

  it('remembers the choice for next time, and starts collapsed when it was left that way', async () => {
    quiet()
    const user = userEvent.setup()
    const first = renderAt('/home')
    await user.click(await screen.findByRole('button', { name: 'Collapse' }))
    expect(localStorage.getItem('cognipm.sidebar.collapsed')).toBe('1')
    first.unmount()

    const second = renderAt('/home')

    expect(await screen.findByRole('button', { name: 'Expand the sidebar' })).toBeInTheDocument()
    expect(second.container.querySelector('.app')).toHaveClass('collapsed')
  })

  it('still works when the browser will not store the choice', async () => {
    quiet()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const user = userEvent.setup()
    const { container } = renderAt('/home')

    await user.click(await screen.findByRole('button', { name: 'Collapse' }))

    expect(container.querySelector('.app')).toHaveClass('collapsed')
    vi.restoreAllMocks()
  })

  it('keeps the waiting count on Approvals when collapsed', async () => {
    mockApi({
      'GET /api/runs': { waiting: [runSummary('r1')], past: [], awaiting_review_count: 2 },
      'GET /api/project': PROJECT,
    })
    const user = userEvent.setup()
    renderAt('/home')

    await user.click(await screen.findByRole('button', { name: 'Collapse' }))

    expect(await screen.findByLabelText('2 waiting for you')).toBeInTheDocument()
  })

  it('links the breadcrumb back to the parent page when you are inside a run', async () => {
    quiet()

    renderAt('/approvals/run-1')

    const crumb = (await screen.findByText(/MCP/, { selector: '.crumb' })) as HTMLElement
    expect(within(crumb).getByRole('link', { name: 'Approvals' })).toHaveAttribute('href', '/approvals')
    expect(crumb).toHaveTextContent('MCP › Approvals › Review')
    expect(screen.getByRole('heading', { level: 1, name: 'Review a run' })).toBeInTheDocument()
  })
})
