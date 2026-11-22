import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { tabPanelProps } from '../lib/tabs'
import { EmptyState, ErrorState, PageHeader, StatCard, Tabs } from './PageParts'

describe('PageHeader', () => {
  it('shows the description and the actions, and nothing when it has neither', () => {
    const { container, rerender } = render(
      <PageHeader description="What this page is for" actions={<button>Export</button>} />,
    )

    expect(screen.getByText('What this page is for')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()

    rerender(<PageHeader />)
    expect(container.querySelector('.page-subtitle, .page-actions')).toBeNull()
  })
})

describe('EmptyState', () => {
  it('says what is missing, with an optional title and next step', () => {
    render(
      <EmptyState title="No tasks yet" action={<a href="/console">Start one</a>}>
        Nothing has been run.
      </EmptyState>,
    )

    expect(screen.getByRole('heading', { name: 'No tasks yet' })).toBeInTheDocument()
    expect(screen.getByText('Nothing has been run.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start one' })).toBeInTheDocument()
  })

  it('works with only a sentence', () => {
    render(<EmptyState>Nothing here.</EmptyState>)

    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })
})

describe('ErrorState', () => {
  it('announces what went wrong, and offers Try again only when it can help', async () => {
    const retry = vi.fn()
    const user = userEvent.setup()
    const { rerender } = render(<ErrorState title="Could not load runs" message="Jira returned 401" onRetry={retry} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Could not load runs')
    expect(screen.getByRole('alert')).toHaveTextContent('Jira returned 401')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledTimes(1)

    rerender(<ErrorState message="Nothing to retry" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
  })
})

describe('StatCard', () => {
  it('shows a label, a number and an optional hint', () => {
    render(<StatCard label="Approval rate" value="82%" hint="last 30 days" />)

    expect(screen.getByText('Approval rate')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('last 30 days')).toBeInTheDocument()
  })
})

describe('Tabs', () => {
  const TABS = [
    { id: 'waiting', label: 'Waiting', count: 2 },
    { id: 'history', label: 'History' },
    { id: 'steps', label: 'Steps' },
  ]

  function Harness({ onChange }: { onChange?: (id: string) => void }) {
    const [value, setValue] = useState('waiting')
    return (
      <>
        <Tabs
          label="View"
          tabs={TABS}
          value={value}
          onChange={(id) => {
            setValue(id)
            onChange?.(id)
          }}
        />
        <div {...tabPanelProps(value)}>content for {value}</div>
      </>
    )
  }

  it('marks the selected tab, shows counts, and links each tab to its panel', () => {
    render(<Harness />)

    const waiting = screen.getByRole('tab', { name: /Waiting/ })
    expect(waiting).toHaveAttribute('aria-selected', 'true')
    expect(waiting).toHaveTextContent('2')
    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', waiting.id)
    expect(waiting).toHaveAttribute('aria-controls', screen.getByRole('tabpanel').id)
  })

  it('puts only the selected tab in the tab order', () => {
    render(<Harness />)

    expect(screen.getByRole('tab', { name: /Waiting/ })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('tabindex', '-1')
  })

  it('moves and selects with the arrow keys, wrapping at the ends, and with Home and End', () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    const waiting = screen.getByRole('tab', { name: /Waiting/ })
    waiting.focus()

    fireEvent.keyDown(waiting, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'History' })).toHaveFocus()

    fireEvent.keyDown(screen.getByRole('tab', { name: 'History' }), { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Steps' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Steps' }), { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /Waiting/ })).toHaveAttribute('aria-selected', 'true') // wrapped round

    fireEvent.keyDown(screen.getByRole('tab', { name: /Waiting/ }), { key: 'ArrowLeft' })
    expect(screen.getByRole('tab', { name: 'Steps' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Steps' }), { key: 'Home' })
    expect(screen.getByRole('tab', { name: /Waiting/ })).toHaveAttribute('aria-selected', 'true')
    expect(onChange).toHaveBeenCalledTimes(5)
  })

  it('ignores other keys and changes tab on a click', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<Harness onChange={onChange} />)

    fireEvent.keyDown(screen.getByRole('tab', { name: /Waiting/ }), { key: 'a' })
    expect(onChange).not.toHaveBeenCalled()

    await user.click(screen.getByRole('tab', { name: 'Steps' }))
    expect(onChange).toHaveBeenCalledWith('steps')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('content for steps')
  })
})
