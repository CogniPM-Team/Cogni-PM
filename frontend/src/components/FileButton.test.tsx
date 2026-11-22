import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FileButton from './FileButton'

const notes = () => new File(['Payroll moves to Q3.'], 'sprint.md', { type: 'text/markdown' })

describe('FileButton', () => {
  it('shows a button with a hint, and hands over the chosen file', async () => {
    const onFile = vi.fn()
    const user = userEvent.setup()
    render(<FileButton onFile={onFile} />)

    expect(screen.getByText('.txt or .md')).toBeInTheDocument()
    await user.upload(screen.getByLabelText('Load a text file'), notes())

    expect(onFile).toHaveBeenCalledTimes(1)
    expect(onFile.mock.calls[0][0].name).toBe('sprint.md')
  })

  it('names the loaded file instead of the hint', () => {
    render(<FileButton fileName="sprint.md" onFile={() => {}} />)

    expect(screen.getByText('Loaded sprint.md')).toBeInTheDocument()
    expect(screen.queryByText('.txt or .md')).not.toBeInTheDocument()
  })

  it('lets the same file be chosen again, because the input is emptied after each choice', async () => {
    const onFile = vi.fn()
    const user = userEvent.setup()
    render(<FileButton onFile={onFile} />)
    const input = screen.getByLabelText('Load a text file') as HTMLInputElement

    await user.upload(input, notes())
    expect(input.value).toBe('')
    await user.upload(input, notes())

    expect(onFile).toHaveBeenCalledTimes(2)
  })

  it('only offers text files, and keeps the real input reachable by keyboard', () => {
    render(<FileButton onFile={() => {}} />)

    const input = screen.getByLabelText('Load a text file')
    expect(input).toHaveAttribute('accept', expect.stringContaining('.txt'))
    expect(input).toHaveAttribute('type', 'file')
    expect(input).not.toHaveAttribute('hidden') // hidden visually only, so it can still take focus
  })
})
