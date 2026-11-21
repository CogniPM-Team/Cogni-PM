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

const SUGGESTIONS = ['Which stories are still open?', 'Is anything blocked?', 'What is in progress right now?', 'Summarise the epics']

/**
 * The Co-Pilot (M1): ask questions about the project. It can only read; it cannot propose or create anything.
 * With a `chatId` it reopens that conversation from the server; without one it is a new chat, which exists once
 * the first answer comes back and then appears in the chat list.
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
  return <Conversation key={chatId ?? 'new'} chatId={chatId} title={history.data?.session.title ?? null} initial={initial} />
}

function Conversation({ chatId, title, initial }: { chatId?: string; title: string | null; initial: Message[] }) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>(initial)
  const [sessionId, setSessionId] = useState<string | null>(chatId ?? null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLTextAreaElement>(null)

  // Keep the newest message in view as the conversation grows.
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length, busy])

  // The question box grows with what is typed, up to a limit, and goes back down once it is sent.
  useEffect(() => {
    const element = box.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [draft])

  async function send(question: string = draft) {
    const text = question.trim()
    if (!text || busy) return
    setMessages((m) => [...m, { role: 'user', text }])
    setDraft('')
    setBusy(true)
    setError(null)
    try {
      const reply = await api.post<ChatResult>('/api/chat', { message: text, session_id: sessionId })
      setMessages((m) => [...m, { role: 'agent', text: reply.answer, reads: reply.tool_calls.length }])
      setSessionId(reply.session_id)
      notifyChatsChanged() // the chat list shows it (or moves it to the top)
      if (!chatId) navigate(`/console/${reply.session_id}`, { replace: true }) // a new chat now has an address
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const empty = messages.length === 0 && !busy

  return (
    <section aria-label="Co-Pilot chat" className="chat-panel">
      {title && <h2 className="chat-title">{title}</h2>}

      <div className="chat-scroll">
        <div className="chat-inner">
          {empty && (
            <div className="chat-empty">
              <h2>What would you like to know?</h2>
              <p>The Co-Pilot reads Jira and answers in plain words.</p>
              <div className="chips" role="group" aria-label="Suggested questions">
                {SUGGESTIONS.map((suggestion) => (
                  <button key={suggestion} type="button" className="chip" onClick={() => void send(suggestion)}>
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="chat-thread" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <span className="who">{m.role === 'agent' ? 'Co-Pilot' : 'You'}</span>
                <div className={`bubble ${m.role}`}>
                  {m.role === 'agent' ? <Markdown text={m.text} /> : m.text}
                  {m.role === 'agent' && m.reads ? <span className="reads">Read Jira {plural(m.reads, 'time')}</span> : null}
                </div>
              </div>
            ))}
            {busy && (
              <div className="msg agent">
                <span className="who">Co-Pilot</span>
                <div className="bubble agent working" role="status">
                  <Spinner />
                  <span>The Co-Pilot is looking at Jira...</span>
                </div>
              </div>
            )}
          </div>
          <div ref={end} />
        </div>
      </div>

      <div className="composer-wrap">
        <div className="chat-inner">
          {error && <p className="error">{error}</p>}
          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault()
              void send()
            }}
          >
            <textarea
              ref={box}
              rows={1}
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
          <p className="composer-hint">Enter to send, Shift+Enter for a new line.</p>
        </div>
      </div>
    </section>
  )
}
