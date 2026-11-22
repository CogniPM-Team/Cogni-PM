import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { runSummary } from '../test/fixtures'
import RunCard from './RunCard'

const show = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('RunCard', () => {
  it('lays out where the run came from, how many drafts and how long it has waited, each as its own fact', () => {
    const ready = new Date(Date.now() - 20 * 60 * 1000).toISOString()
    show(<RunCard run={runSummary('r1', { scope: 'story MCP-20', task_type: 'p2', draft_count: 3, ready_at: ready })} />)

    const facts = within(screen.getByRole('list'))
    expect(facts.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['story MCP-20', '3 drafts', 'Waiting 20 min ago'])
    expect(screen.getByRole('heading', { name: 'Break down a story' })).toBeInTheDocument()
  })

  it('opens the run from one link, which the whole card is pressed through', () => {
    show(<RunCard run={runSummary('r1')} />)

    const link = screen.getByRole('link', { name: 'Review' })
    expect(link).toHaveAttribute('href', '/approvals/r1')
    expect(link).toHaveClass('stretch') // its ::after covers the card, so pressing anywhere on it follows this link
    expect(screen.getByRole('article')).toHaveClass('clickable')
  })

  it('flags a run that has waited more than a day', () => {
    show(<RunCard run={runSummary('r1', { ready_at: new Date(Date.now() - 30 * 3600 * 1000).toISOString() })} />)

    expect(screen.getByText('Waiting over a day')).toBeInTheDocument()
  })

  it('says a failed run did not finish, and offers to retry it', () => {
    show(<RunCard run={runSummary('r1', { status: 'failed' })} retry />)

    expect(screen.getByText('Did not finish creating everything')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open to retry' })).toHaveAttribute('href', '/approvals/r1')
  })

  it('leaves out the waiting time when the run is not ready for review yet', () => {
    show(<RunCard run={runSummary('r1', { ready_at: null })} />)

    expect(screen.queryByText(/^Waiting/)).not.toBeInTheDocument()
  })
})
