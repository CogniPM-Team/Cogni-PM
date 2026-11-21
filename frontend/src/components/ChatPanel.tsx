import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ChatResult, ChatSessionDetail } from '../api/types'
import { useFetch } from '../api/useFetch'
import { notifyChatsChanged } from '../lib/chatEvents'
import { plural } from '../lib/format'
import Markdown from './Markdown'
import Spinner from './Spinner'

interface Message {
  role: 'user' | 'agent'
  text: string
  reads?: number
}

/**
 * The Co-Pilot (M1): ask questions about the project. It can only read; it cannot propose or create anything.
 * With a `chatId` it reopens that conversation from the server; without one it is a new chat, which exists once
 * the first answer comes back and then appears in the sidebar.
 */
export default function ChatPanel({ chatId }: { chatId?: string }) {
  const history = useFetch<ChatSessionDetail>(chatId ? `/api/chat/sessions/${chatId}` : null)

  if (chatId && history.loading) return <p className="muted">Opening chat...</p>
  if (chatId && history.error) {
    return (
      <p className="error">
        Could not open this chat: {history.error.message} <Link to="/console">Start a new chat</Link>
      </p>
    )
  }
  const initial: Message[] =
    history.data?.messages.map((m) => ({ role: m.role, text: m.content, reads: m.reads ?? undefined })) ?? []
  return <Conversation key={chatId ?? 'new'} chatId={chatId} initial={initial} />
}

function Conversation({ chatId, initial }: { chatId?: string; initial: Message[] }) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>(initial)
  const [sessionId, setSessionId] = useState<string | null>(chatId ?? null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)

  // Keep the newest message in view as the conversation grows.
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length, busy])

  async function send() {
    const text = draft.trim()
    if (!text || busy) return
    setMessages((m) => [...m, { role: 'user', text }])
    setDraft('')
    setBusy(true)
    setError(null)
    try {
      const reply = await api.post<ChatResult>('/api/chat', { message: text, session_id: sessionId })
      setMessages((m) => [...m, { role: 'agent', text: reply.answer, reads: reply.tool_calls.length }])
      setSessionId(reply.session_id)
      notifyChatsChanged() // the sidebar lists it (or moves it to the top)
      if (!chatId) navigate(`/console/${reply.session_id}`, { replace: true }) // a new chat now has an address
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Co-Pilot chat" className="chat-panel">
      <p className="page-subtitle">
        Ask about the project in plain words. The Co-Pilot only reads Jira: it cannot draft or create anything.
      </p>
      {messages.length === 0 && (
        <p className="empty">Try “Which stories are still open?” or “Is anything blocked?”</p>
      )}
      <div className="chat-thread" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.role === 'agent' ? <Markdown text={m.text} /> : m.text}
            {m.role === 'agent' && m.reads ? <span className="reads">Read Jira {plural(m.reads, 'time')}</span> : null}
          </div>
        ))}
        {busy && (
          <div className="bubble agent working" role="status">
            <Spinner />
            <span>The Co-Pilot is looking at Jira...</span>
          </div>
        )}
        <div ref={end} />
      </div>
      {error && <p className="error">{error}</p>}
      <form
        className="chat-form"
        onSubmit={(event) => {
          event.preventDefault()
          void send()
        }}
      >
        <textarea
          aria-label="Your question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send()
            }
          }}
          placeholder="Ask a question about the project"
        />
        <button type="submit" className="primary" disabled={busy || !draft.trim()}>
          {busy ? 'Working...' : 'Ask'}
        </button>
      </form>
    </section>
  )
}
