import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RUNS_CHANGED } from '../lib/chatEvents'
import { runSummary } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import RunHistory from './RunHistory'

function renderHistory() {
  return render(
    <MemoryRouter>
      <RunHistory />
    </MemoryRouter>,
  )
}

describe('RunHistory (the Super-Pilot task list)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists recent tasks with where each stands, the ones waiting for you first, each opening its review', async () => {
    mockApi({
      'GET /api/runs': {
        waiting: [runSummary('r-wait', { draft_count: 3, scope: 'planning call notes' })],
        past: [runSummary('r-done', { status: 'applied', task_type: 'p2', scope: 'story MCP-8', draft_count: 2 })],
        awaiting_review_count: 1,
      },
    })

    renderHistory()

    const links = await screen.findAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/approvals/r-wait', '/approvals/r-done'])
    expect(links[0]).toHaveTextContent('Draft backlog')
    expect(links[0]).toHaveTextContent('planning call notes · 3 drafts')
    expect(links[1]).toHaveTextContent('Break down a story')
    expect(screen.getByText('Waiting for you')).toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })

  it('invites you to start a task when there are none, and reloads when a task starts or finishes', async () => {
    let reloads = 0
    mockApi({
      'GET /api/runs': () => {
        reloads += 1
        return reloads === 1
          ? { waiting: [], past: [], awaiting_review_count: 0 }
          : { waiting: [runSummary('r1')], past: [], awaiting_review_count: 1 }
      },
    })

    renderHistory()
    expect(await screen.findByText(/No tasks yet/)).toBeInTheDocument()

    act(() => void window.dispatchEvent(new Event(RUNS_CHANGED)))

    expect(await screen.findByRole('link', { name: /Draft backlog/ })).toHaveAttribute('href', '/approvals/r1')
    expect(screen.queryByText(/No tasks yet/)).not.toBeInTheDocument()
  })
})
