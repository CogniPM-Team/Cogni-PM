import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import type { ChatSessionList } from '../api/types'
import { jsonResponse, mockApi } from '../test/mockApi'
import ChatSidebar from './ChatSidebar'

const stamp = '2026-11-21T08:00:00Z'
const chat = (id: string, title: string, folder_id: string | null = null) => ({
  id,
  title,
  folder_id,
  created_at: stamp,
  updated_at: stamp,
  message_count: 2,
})

const LIST: ChatSessionList = {
  folders: [
    { id: 'f1', name: 'Sprint 12' },
    { id: 'f2', name: 'Ideas' },
  ],
  sessions: [chat('c1', 'Open stories', 'f1'), chat('c2', 'Blocked work'), chat('c3', 'Invoices export')],
}

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderSidebar(path = '/console/c2') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/console/:chatId?"
          element={
            <>
              <ChatSidebar />
              <Where />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

const row = (title: string) => screen.getByRole('link', { name: title }).closest('li') as HTMLElement

describe('ChatSidebar', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists chats in folders and ungrouped, marks the open one, and offers a new chat', async () => {
    mockApi({ 'GET /api/chat/sessions': LIST })

    renderSidebar()

    expect(await screen.findByRole('link', { name: 'Blocked work' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Invoices export' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('button', { name: /^Sprint 12/ })).toHaveAttribute('aria-expanded', 'true')
    expect(within(row('Open stories').closest('.folder') as HTMLElement).getByText('Open stories')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '+ New chat' })).toHaveAttribute('href', '/console')
    expect(screen.getByText('Empty. Drag a chat here, or move it from its menu.')).toBeInTheDocument() // the Ideas folder
  })

  it('collapses a folder to hide its chats', async () => {
    mockApi({ 'GET /api/chat/sessions': LIST })
    const user = userEvent.setup()
    renderSidebar()

    await user.click(await screen.findByRole('button', { name: /^Sprint 12/ }))

    expect(screen.queryByRole('link', { name: 'Open stories' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Sprint 12/ })).toHaveAttribute('aria-expanded', 'false')
  })

  it('renames a chat inline: Enter saves it, Escape does not', async () => {
    const calls = mockApi({
      'GET /api/chat/sessions': LIST,
      'PATCH /api/chat/sessions/c3': chat('c3', 'Invoice CSV'),
    })
    const user = userEvent.setup()
    renderSidebar()

    await user.click(await screen.findByRole('button', { name: 'Actions for Invoices export' }))
    await user.click(screen.getByRole('menuitem', { name: 'Rename' }))
    await user.type(screen.getByLabelText('Chat name'), '{Escape}')
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Actions for Invoices export' }))
    await user.click(screen.getByRole('menuitem', { name: 'Rename' }))
    const input = screen.getByLabelText('Chat name')
    await user.clear(input)
    await user.type(input, 'Invoice CSV{Enter}')

    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ title: 'Invoice CSV' }))
  })

  it('moves a chat into a folder, and out of one', async () => {
    const calls = mockApi({
      'GET /api/chat/sessions': LIST,
      'PATCH /api/chat/sessions/c3': chat('c3', 'Invoices export', 'f2'),
      'PATCH /api/chat/sessions/c1': chat('c1', 'Open stories'),
    })
    const user = userEvent.setup()
    renderSidebar()

    await user.click(await screen.findByRole('button', { name: 'Actions for Invoices export' }))
    expect(screen.queryByRole('menuitem', { name: 'Remove from folder' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: 'Move to Ideas' }))
    await waitFor(() => expect(calls.find((c) => c.path === '/api/chat/sessions/c3')?.body).toEqual({ folder_id: 'f2' }))

    await user.click(screen.getByRole('button', { name: 'Actions for Open stories' }))
    expect(screen.queryByRole('menuitem', { name: 'Move to Sprint 12' })).not.toBeInTheDocument() // it is already there
    await user.click(screen.getByRole('menuitem', { name: 'Remove from folder' }))
    await waitFor(() => expect(calls.find((c) => c.path === '/api/chat/sessions/c1')?.body).toEqual({ folder_id: null }))
  })

  it('asks twice before deleting a chat, then leaves it if it was the one open', async () => {
    const calls = mockApi({
      'GET /api/chat/sessions': LIST,
      'DELETE /api/chat/sessions/c2': new Response(null, { status: 204 }),
    })
    const user = userEvent.setup()
    renderSidebar('/console/c2')

    await user.click(await screen.findByRole('button', { name: 'Actions for Blocked work' }))
    await user.click(screen.getByRole('menuitem', { name: 'Delete' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // the first click only asks
    await user.click(screen.getByRole('menuitem', { name: 'Click again to delete for good' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/api/chat/sessions/c2')).toBe(true))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/console$/))
  })

  it('closes a menu with Escape without doing anything', async () => {
    const calls = mockApi({ 'GET /api/chat/sessions': LIST })
    const user = userEvent.setup()
    renderSidebar()

    await user.click(await screen.findByRole('button', { name: 'Actions for Invoices export' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(calls.filter((c) => c.method !== 'GET')).toEqual([])
  })

  it('creates, renames and deletes folders; deleting one says the chats are kept', async () => {
    const calls = mockApi({
      'GET /api/chat/sessions': LIST,
      'POST /api/chat/folders': { id: 'f3', name: 'Research' },
      'PATCH /api/chat/folders/f2': { id: 'f2', name: 'Backlog ideas' },
      'DELETE /api/chat/folders/f1': new Response(null, { status: 204 }),
    })
    const user = userEvent.setup()
    renderSidebar()

    await user.click(await screen.findByRole('button', { name: '+ New folder' }))
    await user.type(screen.getByLabelText('New folder name'), 'Research{Enter}')
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'Research' }))

    await user.click(screen.getByRole('button', { name: 'Actions for folder Ideas' }))
    await user.click(screen.getByRole('menuitem', { name: 'Rename' }))
    const input = screen.getByLabelText('Folder name')
    await user.clear(input)
    await user.type(input, 'Backlog ideas{Enter}')
    await waitFor(() => expect(calls.find((c) => c.path === '/api/chat/folders/f2')?.body).toEqual({ name: 'Backlog ideas' }))

    await user.click(screen.getByRole('button', { name: 'Actions for folder Sprint 12' }))
    await user.click(screen.getByRole('menuitem', { name: 'Delete folder' }))
    await user.click(screen.getByRole('menuitem', { name: 'Click again: chats are kept' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/api/chat/folders/f1')).toBe(true))
  })

  it('shows what went wrong when a change is refused', async () => {
    mockApi({
      'GET /api/chat/sessions': LIST,
      'PATCH /api/chat/sessions/c3': jsonResponse({ detail: 'folder not found' }, 404),
    })
    const user = userEvent.setup()
    renderSidebar()

    await user.click(await screen.findByRole('button', { name: 'Actions for Invoices export' }))
    await user.click(screen.getByRole('menuitem', { name: 'Move to Ideas' }))

    expect(await screen.findByText('folder not found')).toBeInTheDocument()
  })

  it('invites you to ask something when there are no chats yet', async () => {
    mockApi({ 'GET /api/chat/sessions': { folders: [], sessions: [] } })

    renderSidebar('/console')

    expect(await screen.findByText(/No chats yet/)).toBeInTheDocument()
  })

  describe('drag and drop', () => {
    /** A minimal stand-in for the browser's DataTransfer, which jsdom does not provide. */
    function transfer() {
      const store: Record<string, string> = {}
      return {
        setData: (type: string, value: string) => void (store[type] = value),
        getData: (type: string) => store[type] ?? '',
        effectAllowed: 'all',
        dropEffect: 'none',
      }
    }
    const chatItem = (title: string) => screen.getByRole('link', { name: title }).closest('li') as HTMLElement
    const folderItem = (name: RegExp) => screen.getByRole('button', { name }).closest('.folder') as HTMLElement

    it('moves a chat into a folder when it is dropped on it, and highlights the folder on the way', async () => {
      const calls = mockApi({
        'GET /api/chat/sessions': LIST,
        'PATCH /api/chat/sessions/c3': chat('c3', 'Invoices export', 'f2'),
      })
      renderSidebar()
      await screen.findByRole('link', { name: 'Invoices export' })
      const dataTransfer = transfer()
      const ideas = folderItem(/^Ideas/)

      fireEvent.dragStart(chatItem('Invoices export'), { dataTransfer })
      fireEvent.dragOver(ideas, { dataTransfer })
      expect(ideas).toHaveClass('drop-target')
      fireEvent.drop(ideas, { dataTransfer })

      await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ folder_id: 'f2' }))
      expect(calls.find((c) => c.method === 'PATCH')?.path).toBe('/api/chat/sessions/c3')
    })

    it('takes a chat out of its folder when it is dropped below the folders', async () => {
      const calls = mockApi({
        'GET /api/chat/sessions': LIST,
        'PATCH /api/chat/sessions/c1': chat('c1', 'Open stories'),
      })
      renderSidebar()
      await screen.findByRole('link', { name: 'Open stories' })
      const dataTransfer = transfer()
      const area = screen.getByRole('list', { name: 'Chats not in a folder' })

      fireEvent.dragStart(chatItem('Open stories'), { dataTransfer })
      expect(await screen.findByText('Drop here to take it out of its folder')).toBeInTheDocument()
      fireEvent.dragOver(area, { dataTransfer })
      fireEvent.drop(area, { dataTransfer })

      await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ folder_id: null }))
    })

    it('does nothing when a chat is dropped where it already is', async () => {
      const calls = mockApi({ 'GET /api/chat/sessions': LIST })
      renderSidebar()
      await screen.findByRole('link', { name: 'Open stories' })
      const dataTransfer = transfer()

      fireEvent.dragStart(chatItem('Open stories'), { dataTransfer })
      fireEvent.drop(folderItem(/^Sprint 12/), { dataTransfer }) // it is already in Sprint 12

      expect(calls.filter((c) => c.method !== 'GET')).toEqual([])
    })

    it('ignores anything that is not one of its own chats, such as a file dragged in', async () => {
      const calls = mockApi({ 'GET /api/chat/sessions': LIST })
      renderSidebar()
      await screen.findByRole('link', { name: 'Open stories' })
      const ideas = folderItem(/^Ideas/)

      fireEvent.dragOver(ideas, { dataTransfer: transfer() }) // no chat was picked up
      fireEvent.drop(ideas, { dataTransfer: transfer() })

      expect(ideas).not.toHaveClass('drop-target')
      expect(calls.filter((c) => c.method !== 'GET')).toEqual([])
    })

    it('lets go of the highlight when the drag is cancelled', async () => {
      mockApi({ 'GET /api/chat/sessions': LIST })
      renderSidebar()
      await screen.findByRole('link', { name: 'Invoices export' })
      const dataTransfer = transfer()
      const ideas = folderItem(/^Ideas/)

      fireEvent.dragStart(chatItem('Invoices export'), { dataTransfer })
      fireEvent.dragOver(ideas, { dataTransfer })
      fireEvent.dragEnd(chatItem('Invoices export'), { dataTransfer })

      expect(ideas).not.toHaveClass('drop-target')
      expect(chatItem('Invoices export')).not.toHaveClass('dragging')
    })
  })
})
