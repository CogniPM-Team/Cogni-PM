import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { draft, RESET } from '../test/fixtures'
import DraftCard from './DraftCard'

const show = (d = draft('d1', 'Password reset', RESET), extra: Partial<React.ComponentProps<typeof DraftCard>> = {}) =>
  render(<DraftCard draft={d} ticked={false} canTick canEdit onTick={() => {}} onActivate={() => {}} onSaved={() => {}} {...extra} />)

const LONG = 'The reset flow must send a time-limited link by email. '.repeat(8)

describe('DraftCard', () => {
  it('leads with what you decide on: the title, the description and when it is done', () => {
    show(draft('d1', 'Password reset', RESET, { payload: { issue_type: 'Story', summary: 'Password reset', description: 'Let users reset it.', acceptance_criteria: ['A link is emailed', 'It expires in an hour'], labels: ['auth'] }, effective: { issue_type: 'Story', summary: 'Password reset', description: 'Let users reset it.', acceptance_criteria: ['A link is emailed', 'It expires in an hour'], labels: ['auth'] } }))

    expect(screen.getByRole('heading', { name: 'Password reset' })).toBeInTheDocument()
    expect(screen.getByText('Let users reset it.')).toBeInTheDocument()
    const criteria = within(screen.getByRole('region', { name: 'Acceptance criteria' }))
    expect(criteria.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['A link is emailed', 'It expires in an hour'])
    expect(within(screen.getByRole('list', { name: 'Labels' })).getByText('auth')).toBeInTheDocument()
  })

  it('keeps the reasons and the quotes out of the way until asked, and shows one at a time', async () => {
    const user = userEvent.setup()
    show()
    expect(screen.queryByText('The notes ask for this directly.')).not.toBeInTheDocument()
    expect(screen.queryByText(new RegExp(RESET))).not.toBeInTheDocument()

    const why = screen.getByRole('button', { name: 'Why the agent drafted this' })
    const quotes = screen.getByRole('button', { name: /From your input/ })
    await user.click(why)
    expect(why).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('The notes ask for this directly.')).toBeInTheDocument()

    await user.click(quotes)
    expect(quotes).toHaveAttribute('aria-expanded', 'true')
    expect(why).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('The notes ask for this directly.')).not.toBeInTheDocument()
    expect(screen.getByText(new RegExp(RESET))).toBeInTheDocument()

    await user.click(quotes)
    expect(screen.queryByText(new RegExp(RESET))).not.toBeInTheDocument()
  })

  it('counts the quotes on their tab, and warns when one is not in the saved input', async () => {
    const user = userEvent.setup()
    show(draft('d1', 'Password reset', 'A quote nobody wrote'))

    const tab = screen.getByRole('button', { name: /From your input/ })
    expect(tab).toHaveTextContent('1')
    expect(tab).toHaveTextContent('1 not found in the saved input')
    expect(tab).toHaveClass('warn')
    await user.click(tab)
    expect(screen.getByText(/not found in the saved input/, { selector: '.muted' })).toBeInTheDocument()
  })

  it('keeps an assumption in view, and says nothing when there is none', () => {
    const { unmount } = show(draft('d1', 'Password reset', RESET, { assumptions: 'Logs are kept for 90 days' }))
    expect(screen.getByRole('note')).toHaveTextContent('Check this assumption')
    expect(screen.getByRole('note')).toHaveTextContent('Logs are kept for 90 days')
    unmount()

    show(draft('d2', 'Login audit', RESET, { assumptions: 'NA' }))
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    expect(screen.queryByText(/None stated/)).not.toBeInTheDocument()
  })

  it('cuts a long description to a few lines and lets you read all of it, but not a short one', async () => {
    const user = userEvent.setup()
    const long = draft('d1', 'Password reset', RESET)
    long.effective = { ...long.effective, description: LONG }
    show(long)

    const text = screen.getByText(LONG.trim())
    expect(text).toHaveClass('clamped')
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    expect(text).not.toHaveClass('clamped')
    await user.click(screen.getByRole('button', { name: 'Show less' }))
    expect(text).toHaveClass('clamped')
  })

  it('does not offer Show more for a short description', () => {
    show()

    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
  })

  it('offers an edit only while the draft can still be changed, and hides the evidence while editing', async () => {
    const user = userEvent.setup()
    const { unmount } = show(undefined, { canEdit: false })
    expect(screen.queryByRole('button', { name: 'Edit before approving' })).not.toBeInTheDocument()
    unmount()

    show()
    await user.click(screen.getByRole('button', { name: 'Edit before approving' }))
    expect(screen.getByRole('textbox', { name: 'Title' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Why the agent drafted this' })).not.toBeInTheDocument()
  })

  it('tells the reviewer what the agent originally wrote when they changed the title', () => {
    const edited = draft('d1', 'Reset by email', RESET)
    edited.edited_payload = { ...edited.payload, summary: 'Reset by email' }
    edited.payload = { ...edited.payload, summary: 'Password reset' }
    show(edited)

    expect(screen.getByText('Password reset')).toBeInTheDocument() // struck through
    expect(screen.getByText('Edited by you')).toBeInTheDocument()
  })
})
