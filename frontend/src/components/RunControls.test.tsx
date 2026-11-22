import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { RunDetail } from '../api/types'
import { runDetail, runSummary } from '../test/fixtures'
import { jsonResponse, mockApi } from '../test/mockApi'
import RunControls from './RunControls'

const detail = (status: string, over: Partial<RunDetail> = {}): RunDetail =>
  runDetail('r1', { run: runSummary('r1', { status }), can_control: true, ...over })

const show = (d: RunDetail, onChanged = vi.fn()) => {
  render(<RunControls detail={d} onChanged={onChanged} />)
  return onChanged
}

const posted = (calls: { method: string; path: string }[]) => calls.filter((c) => c.method === 'POST').map((c) => c.path)

describe('RunControls', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lets a PM pause a running run, and says what is pending until it takes effect', async () => {
    const calls = mockApi({ 'POST /api/runs/r1/pause': { run_id: 'r1', status: 'running', control: 'pause' } })
    const user = userEvent.setup()
    const changed = show(detail('running'))

    expect(screen.getByRole('status')).toHaveTextContent('The agent is working.')
    await user.click(screen.getByRole('button', { name: 'Pause' }))

    expect(posted(calls)).toEqual(['/api/runs/r1/pause'])
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('says the pause is on its way, and offers to take it back', async () => {
    const calls = mockApi({ 'POST /api/runs/r1/resume': { run_id: 'r1', status: 'running', control: null } })
    const user = userEvent.setup()
    show(detail('running', { control: 'pause' }))

    expect(screen.getByRole('status')).toHaveTextContent('Pausing after the current step')
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep going' }))

    expect(posted(calls)).toEqual(['/api/runs/r1/resume'])
  })

  it('shows a paused run as paused, with Resume instead of Pause', async () => {
    const calls = mockApi({ 'POST /api/runs/r1/resume': { run_id: 'r1', status: 'paused', control: null } })
    const user = userEvent.setup()
    show(detail('paused', { control: 'pause' }))

    expect(screen.getByRole('status')).toHaveTextContent('Paused. Nothing happens until you resume it.')
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Resume' }))

    expect(posted(calls)).toEqual(['/api/runs/r1/resume'])
  })

  it('asks before stopping, and says what stopping does and does not do', async () => {
    const calls = mockApi({ 'POST /api/runs/r1/stop': { run_id: 'r1', status: 'running', control: 'stop' } })
    const user = userEvent.setup()
    show(detail('running'))

    await user.click(screen.getByRole('button', { name: 'Stop' }))
    const ask = screen.getByRole('alertdialog', { name: 'Confirm stop' })
    expect(ask).toHaveTextContent('Anything already staged stays')
    expect(ask).toHaveTextContent('Nothing is created in Jira')
    expect(posted(calls)).toEqual([]) // nothing is sent until it is confirmed

    await user.click(screen.getByRole('button', { name: 'Yes, stop it' }))
    expect(posted(calls)).toEqual(['/api/runs/r1/stop'])
  })

  it('asks before cancelling, says the drafts are discarded, and can be backed out of', async () => {
    const calls = mockApi({})
    const user = userEvent.setup()
    show(detail('running'))

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('alertdialog', { name: 'Confirm cancel' })).toHaveTextContent('its drafts are discarded')
    await user.click(screen.getByRole('button', { name: 'Keep it going' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(posted(calls)).toEqual([])
  })

  it('offers nothing more once a stop or cancel has been asked for', () => {
    show(detail('running', { control: 'stop' }))

    expect(screen.getByRole('status')).toHaveTextContent('Stopping after the current step')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the agent question, and sends an answer only when there is one', async () => {
    const calls = mockApi({ 'POST /api/runs/r1/answer': { run_id: 'r1', status: 'running', control: null } })
    const user = userEvent.setup()
    const changed = show(detail('waiting_for_information', { question: 'Which payment provider?', can_answer: true }))

    expect(screen.getByText('Which payment provider?')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument() // nothing is running to pause
    const send = screen.getByRole('button', { name: 'Send answer' })
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('Your answer'), 'Stripe')
    await user.click(send)

    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ text: 'Stripe' })
    expect(changed).toHaveBeenCalled()
  })

  it('lets a PM stop or cancel a run that is waiting for an answer', async () => {
    const calls = mockApi({ 'POST /api/runs/r1/cancel': { run_id: 'r1', status: 'cancelled', control: null } })
    const user = userEvent.setup()
    show(detail('waiting_for_information', { question: 'Which?', can_answer: true }))

    await user.click(screen.getByRole('button', { name: 'Cancel the run' }))
    await user.click(screen.getByRole('button', { name: 'Yes, cancel it' }))

    expect(posted(calls)).toEqual(['/api/runs/r1/cancel'])
  })

  it('shows a developer what is happening and offers nothing to press', () => {
    show(detail('waiting_for_information', { question: 'Which?', can_control: false, can_answer: false }))

    expect(screen.getByText('Which?')).toBeInTheDocument()
    expect(screen.getByText('A PM needs to answer this.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument()
  })

  it('says why when the server refuses, and leaves the buttons usable', async () => {
    mockApi({ 'POST /api/runs/r1/pause': jsonResponse({ detail: 'this run is awaiting_review; only a running run can be paused' }, 409) })
    const user = userEvent.setup()
    const changed = show(detail('running'))

    await user.click(screen.getByRole('button', { name: 'Pause' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('only a running run can be paused')
    expect(changed).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Pause' })).toBeEnabled()
  })

  it.each(['awaiting_review', 'applied', 'rejected', 'failed', 'stopped', 'cancelled'])('is not shown for a run that is %s', (status) => {
    const { container } = render(<RunControls detail={detail(status)} onChanged={() => {}} />)

    expect(container).toBeEmptyDOMElement()
  })
})
