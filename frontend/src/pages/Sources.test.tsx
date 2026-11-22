import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { DocumentSummary } from '../api/types'
import { type Call, mockApi } from '../test/mockApi'
import Library from './Library'

const doc = (id: string, over: Partial<DocumentSummary> = {}): DocumentSummary => ({
  id,
  title: `Notes ${id}`,
  kind: 'notes',
  filename: null,
  char_count: 1200,
  created_at: '2026-11-20T08:00:00Z',
  updated_at: '2026-11-20T08:00:00Z',
  used_in_runs: 0,
  ...over,
})

function renderSources() {
  return render(
    <MemoryRouter initialEntries={['/library?tab=sources']}>
      <Library />
    </MemoryRouter>,
  )
}

describe('Library: Sources', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('switches between Created issues and Sources, and remembers the tab in the address', async () => {
    mockApi({ 'GET /api/artifacts': { items: [], jira_reachable: true }, 'GET /api/documents': [doc('d1')] })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/library']}>
        <Library />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/Nothing has been created yet/)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Sources' }))

    expect(await screen.findByText('Notes d1')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'true')
  })

  it('lists saved documents with their use, and links each to Draft a backlog', async () => {
    mockApi({
      'GET /api/documents': [doc('d1', { used_in_runs: 2, filename: 'sprint.md' }), doc('d2', { kind: 'requirements' })],
    })

    renderSources()

    expect(await screen.findByText('Used in 2 runs')).toBeInTheDocument()
    expect(screen.getByText('Not used yet')).toBeInTheDocument()
    expect(screen.getByText('sprint.md')).toBeInTheDocument()
    expect(screen.getByText('Requirements')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Draft a backlog from this' })[0]).toHaveAttribute(
      'href',
      '/console?mode=M2&document=d1',
    )
  })

  it('opens a document to read its text, and closes it again', async () => {
    mockApi({
      'GET /api/documents': [doc('d1')],
      'GET /api/documents/d1': { ...doc('d1'), text: 'Payroll moves to Q3.' },
    })
    const user = userEvent.setup()
    renderSources()

    await user.click(await screen.findByRole('button', { name: 'Open' }))
    expect(await screen.findByText('Payroll moves to Q3.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Hide' }))
    expect(screen.queryByText('Payroll moves to Q3.')).not.toBeInTheDocument()
  })

  it('renames a document', async () => {
    let title = 'Notes d1'
    const calls = mockApi({
      'GET /api/documents': () => [doc('d1', { title })],
      'PATCH /api/documents/d1': (call: Call) => {
        title = (call.body as { title: string }).title
        return doc('d1', { title })
      },
    })
    const user = userEvent.setup()
    renderSources()

    await user.click(await screen.findByRole('button', { name: 'Rename' }))
    await user.clear(screen.getByLabelText('New title'))
    await user.type(screen.getByLabelText('New title'), 'Retro notes')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Retro notes')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ title: 'Retro notes' })
  })

  it('asks before deleting, says what is kept, and then removes the document', async () => {
    let docs = [doc('d1', { used_in_runs: 1 })]
    const calls = mockApi({
      'GET /api/documents': () => docs,
      'DELETE /api/documents/d1': () => {
        docs = []
        return new Response(null, { status: 204 })
      },
    })
    const user = userEvent.setup()
    renderSources()

    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    const ask = screen.getByRole('alertdialog')
    expect(ask).toHaveTextContent('removed for good')
    expect(ask).toHaveTextContent('Runs made from it keep their own copy')
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // nothing happens until it is confirmed

    await user.click(within(ask).getByRole('button', { name: 'Yes, delete it' }))

    expect(await screen.findByText(/No saved documents yet/)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(1)
  })

  it('cancelling a delete leaves the document alone', async () => {
    const calls = mockApi({ 'GET /api/documents': [doc('d1')] })
    const user = userEvent.setup()
    renderSources()

    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByText('Notes d1')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  })

  it('adds a document, and will not save without a title and some text', async () => {
    let docs: DocumentSummary[] = []
    const calls = mockApi({
      'GET /api/documents': () => docs,
      'POST /api/documents': () => {
        docs = [doc('d9', { title: 'Sprint notes' })]
        return { ...docs[0], text: 'x' }
      },
    })
    const user = userEvent.setup()
    renderSources()

    await user.click(await screen.findByRole('button', { name: 'Add a document' }))
    const save = screen.getByRole('button', { name: 'Save document' })
    expect(save).toBeDisabled()
    await user.type(screen.getByLabelText('Title'), 'Sprint notes')
    expect(save).toBeDisabled() // a title alone is not enough
    await user.type(screen.getByLabelText('Text'), 'Payroll moves to Q3.')
    await user.click(save)

    expect(await screen.findByText('Sprint notes')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ title: 'Sprint notes', kind: 'notes', text: 'Payroll moves to Q3.' })
  })

  it('shows an error with Try again when the documents cannot be loaded', async () => {
    mockApi({})

    renderSources()

    expect(await screen.findByText('Could not load your documents')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
