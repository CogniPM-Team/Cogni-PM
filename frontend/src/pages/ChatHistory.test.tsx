import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { CHATS_CHANGED } from '../lib/chatEvents'
import { jsonResponse, mockApi } from '../test/mockApi'
import AgentConsole from './AgentConsole'

const stamp = '2026-11-21T08:00:00Z'
const session = { id: 's1', title: 'Open stories', folder_id: null, created_at: stamp, updated_at: stamp, message_count: 2 }
const history = {
  session,
  messages: [
    { id: 1, role: 'user', content: 'Which stories are open?', reads: null, created_at: stamp },
    { id: 2, role: 'agent', content: 'There are **12** open stories.', reads: 2, created_at: stamp },
  ],
}

function Where() {
  return <p data-testid="where">{useLocation().pathname + useLocation().search}</p>
}

function renderConsole(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/console/:chatId?"
          element={
            <>
              <AgentConsole />
              <Where />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Reopening a chat', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the whole earlier conversation, formatted, with how much Jira was read', async () => {
    mockApi({ 'GET /api/chat/sessions/s1': history })

    renderConsole('/console/s1')

    expect(await screen.findByText('Which stories are open?')).toBeInTheDocument()
    expect(screen.getByText('12', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Read Jira 2 times')).toBeInTheDocument()
  })

  it('continues the same chat when you ask again, instead of starting a new one', async () => {
    const calls = mockApi({
      'GET /api/chat/sessions/s1': history,
      'POST /api/chat': { session_id: 's1', title: 'Open stories', answer: 'Eight are in progress.', tool_calls: [] },
    })
    const user = userEvent.setup()
    renderConsole('/console/s1')

    await user.type(await screen.findByLabelText('Your question'), 'And in progress?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByText('Eight are in progress.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ message: 'And in progress?', session_id: 's1' })
    expect(screen.getByText('Which stories are open?')).toBeInTheDocument() // the earlier messages stay
  })

  it('gives a brand new chat its own address and tells the sidebar to list it', async () => {
    mockApi({
      'POST /api/chat': { session_id: 's1', title: 'Open stories', answer: 'Twelve.', tool_calls: [] },
      'GET /api/chat/sessions/s1': history,
    })
    const heard = vi.fn()
    window.addEventListener(CHATS_CHANGED, heard)
    const user = userEvent.setup()
    renderConsole('/console')

    await user.type(screen.getByLabelText('Your question'), 'Which stories are open?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/console/s1'))
    expect(heard).toHaveBeenCalled()
    window.removeEventListener(CHATS_CHANGED, heard)
    expect(await screen.findByText('Which stories are open?')).toBeInTheDocument() // reloaded from the server
  })

  it('says so, and offers a fresh start, when the chat is gone', async () => {
    mockApi({ 'GET /api/chat/sessions/gone': jsonResponse({ detail: 'chat not found' }, 404) })

    renderConsole('/console/gone')

    expect(await screen.findByText(/Could not open this chat: chat not found/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start a new chat' })).toHaveAttribute('href', '/console')
  })

  it('treats "New chat" as the Co-Pilot even if Super-Pilot was chosen before', async () => {
    mockApi({ 'GET /api/chat/sessions/s1': history, 'GET /api/stories': [] })
    const user = userEvent.setup()
    renderConsole('/console?mode=M2')
    expect(screen.getByRole('button', { name: /Super-Pilot/ })).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: /Co-Pilot/ }))

    expect(screen.getByTestId('where')).toHaveTextContent(/^\/console$/)
    expect(screen.getByRole('button', { name: /Co-Pilot/ })).toHaveAttribute('aria-pressed', 'true')
  })
})
