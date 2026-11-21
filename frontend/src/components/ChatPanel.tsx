import { useState } from 'react'
import { api } from '../api/client'
import type { ChatResult } from '../api/types'
import { plural } from '../lib/format'

interface Message {
  role: 'user' | 'agent'
  text: string
  reads?: number
}

/** The Co-Pilot (M1): ask questions about the project. It can only read; it cannot propose or create anything. */
export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send() {
    const text = draft.trim()
    if (!text || busy) return
    setMessages((m) => [...m, { role: 'user', text }])
    setDraft('')
    setBusy(true)
    setError(null)
    try {
      const reply = await api.post<ChatResult>('/api/chat', { message: text, session_id: sessionId })
      setSessionId(reply.session_id)
      setMessages((m) => [...m, { role: 'agent', text: reply.answer, reads: reply.tool_calls.length }])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Co-Pilot chat">
      <p className="page-subtitle">
        Ask about the project in plain words. The Co-Pilot only reads Jira: it cannot draft or create anything.
      </p>
      {messages.length === 0 && (
        <p className="empty">Try “Which stories are still open?” or “Is anything blocked?”</p>
      )}
      <div className="chat-thread" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.text}
            {m.role === 'agent' && m.reads ? <span className="reads">Read Jira {plural(m.reads, 'time')}</span> : null}
          </div>
        ))}
        {busy && <div className="bubble muted">Looking at Jira...</div>}
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
          Ask
        </button>
      </form>
    </section>
  )
}
