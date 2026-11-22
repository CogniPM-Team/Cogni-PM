import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Insights as InsightsData } from '../api/types'
import { mockApi } from '../test/mockApi'
import Insights from './Insights'

// The worked example from docs/phases.md: five runs, four decided, twelve reviewed drafts.
const WORKED: InsightsData = {
  runs_started: 5,
  runs_decided: 4,
  runs_open: 1,
  runs_ended_early: 0,
  runs_approved: 2,
  runs_rejected: 2,
  drafts_reviewed: 12,
  drafts_created_as_written: 4,
  drafts_created_after_edit: 1,
  drafts_left_out: 7,
  drafts_edited: 2,
  decisions_timed: 4,
  decision_seconds_median: 300,
  decision_seconds_p90: 600,
  reruns: 1,
  refusals: [
    { rule: 'no_duplicate', count: 2 },
    { rule: 'valid_parent', count: 1 },
  ],
  refusals_total: 3,
  tokens_total: 4000,
  tokens_runs: 5,
  tokens_average: 800,
  approved_untouched: 1,
}

const show = () =>
  render(
    <MemoryRouter>
      <Insights />
    </MemoryRouter>,
  )

const requested = () => (fetch as unknown as { mock: { calls: [string][] } }).mock.calls.map(([url]) => url)
const lastInsights = () => requested().filter((u) => u.startsWith('/api/insights') && !u.includes('export')).at(-1)!
const card = (label: string) => screen.getByText(label).closest('.stat-card') as HTMLElement

describe('Insights', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('gives the answers the definitions give for the worked example', async () => {
    mockApi({ 'GET /api/insights': WORKED })

    show()

    await screen.findByText('Approval rate')
    expect(card('Approval rate')).toHaveTextContent('50%')
    expect(card('Approval rate')).toHaveTextContent('2 of 4 decided runs')
    expect(card('Rejection rate')).toHaveTextContent('50%')
    expect(card('Edit rate')).toHaveTextContent('17%')
    expect(card('Edit rate')).toHaveTextContent('2 of 12 drafts changed')
    expect(card('Approved untouched')).toHaveTextContent('1 of 2 approved runs')
    expect(screen.getByText('5 runs started: 4 decided, 1 still open.')).toBeInTheDocument()
  })

  it('splits the drafts into the three states, which add up to the reviewed drafts', async () => {
    mockApi({ 'GET /api/insights': WORKED })

    show()

    const section = (await screen.findByRole('heading', { name: 'What happened to each draft' })).closest('section')!
    const rows = within(section).getAllByRole('listitem').map((li) => li.textContent)
    expect(rows).toEqual([
      expect.stringContaining('Created as the agent wrote it'),
      expect.stringContaining('Created after you edited it'),
      expect.stringContaining('Left out'),
    ])
    expect(rows[0]).toContain('4')
    expect(rows[1]).toContain('1')
    expect(rows[2]).toContain('7')
    expect(within(section).getByRole('img')).toHaveAccessibleName(
      'Created as the agent wrote it: 4, Created after you edited it: 1, Left out: 7',
    )
    expect(section).toHaveTextContent('12 drafts reviewed')
  })

  it('shows the typical and slowest decision times, and says they are clock time', async () => {
    mockApi({ 'GET /api/insights': WORKED })

    show()

    const section = (await screen.findByRole('heading', { name: 'Time to decide' })).closest('section')!
    expect(within(section).getByText('5 min')).toBeInTheDocument()
    expect(within(section).getByText('10 min')).toBeInTheDocument()
    expect(section).toHaveTextContent('Clock time across 4 runs')
  })

  it('lists the safety rules that refused a draft, and the AI usage and reruns', async () => {
    mockApi({ 'GET /api/insights': WORKED })

    show()

    const rules = (await screen.findByRole('heading', { name: 'Safety rules that refused a draft' })).closest('section')!
    expect(within(rules).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['no duplicate2', 'valid parent1'])
    const usage = screen.getByRole('heading', { name: 'AI usage and reruns' }).closest('section')!
    expect(usage).toHaveTextContent('800')
    expect(usage).toHaveTextContent('4,000')
    expect(usage).toHaveTextContent('20%') // 1 of 5 runs was a rerun
  })

  it('tells you each number is too few to read until there are five decided runs', async () => {
    mockApi({ 'GET /api/insights': WORKED })
    const { unmount } = show()
    expect(await screen.findByText('Too few to read yet')).toBeInTheDocument()
    unmount()

    mockApi({ 'GET /api/insights': { ...WORKED, runs_decided: 5, runs_approved: 3, runs_open: 0 } })
    show()
    await screen.findByText('Approval rate')
    expect(screen.queryByText('Too few to read yet')).not.toBeInTheDocument()
  })

  it('says where a number comes from when you hover it', async () => {
    mockApi({ 'GET /api/insights': WORKED })

    show()

    await screen.findByText('Approval rate')
    expect(card('Approval rate')).toHaveAttribute('title', expect.stringContaining('Runs approved ÷ runs decided'))
  })

  it('says "No decisions yet" instead of showing 0%, and still shows what does not need a decision', async () => {
    mockApi({
      'GET /api/insights': { ...WORKED, runs_decided: 0, runs_approved: 0, runs_rejected: 0, runs_open: 5, drafts_reviewed: 0, drafts_edited: 0, approved_untouched: 0, decision_seconds_median: null, decision_seconds_p90: null },
    })

    show()

    expect(await screen.findByText(/No decisions yet\. 5 runs are still open\./)).toBeInTheDocument()
    expect(screen.queryByText('Approval rate')).not.toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI usage and reruns' })).toBeInTheDocument()
  })

  it('shows an empty page, not zeros, when there are no runs', async () => {
    mockApi({
      'GET /api/insights': { ...WORKED, runs_started: 0, runs_decided: 0, runs_open: 0, runs_approved: 0, runs_rejected: 0, refusals: [], tokens_runs: 0, tokens_total: 0, tokens_average: null },
    })

    show()

    expect(await screen.findByText(/No runs yet/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'AI usage and reruns' })).not.toBeInTheDocument()
  })

  it('asks the server for the chosen task and days, and clears them', async () => {
    mockApi({ 'GET /api/insights': WORKED })
    const user = userEvent.setup()
    show()
    await screen.findByText('Approval rate')

    await user.selectOptions(screen.getByLabelText('Task'), 'p2')
    expect(lastInsights()).toContain('task=p2')
    await user.type(screen.getByLabelText('From'), '2026-11-18')
    const params = new URLSearchParams(lastInsights().split('?')[1])
    expect(new Date(params.get('from')!).getTime()).toBe(new Date(2026, 10, 18).getTime())

    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(lastInsights()).toBe('/api/insights')
  })

  it('offers the data behind the numbers, with the same filters as the page', async () => {
    mockApi({ 'GET /api/insights': WORKED })
    const user = userEvent.setup()
    show()
    await screen.findByText('Approval rate')
    await user.selectOptions(screen.getByLabelText('Task'), 'p1')

    const href = screen.getByRole('link', { name: 'Download the data' }).getAttribute('href')!

    expect(href).toBe('/api/insights/export.csv?task=p1')
  })

  it('shows an error with Try again when the numbers cannot be loaded', async () => {
    mockApi({})

    show()

    expect(await screen.findByText('Could not load the insights')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('says how many of the open runs a person stopped or cancelled, and says nothing when none were', async () => {
    mockApi({ 'GET /api/insights': { ...WORKED, runs_open: 3, runs_ended_early: 2 } })
    const { unmount } = show()
    expect(await screen.findByText(/5 runs started: 4 decided, 3 still open \(2 of them stopped or cancelled\)\./)).toBeInTheDocument()
    unmount()

    mockApi({ 'GET /api/insights': WORKED })
    show()
    expect(await screen.findByText('5 runs started: 4 decided, 1 still open.')).toBeInTheDocument()
  })
})
