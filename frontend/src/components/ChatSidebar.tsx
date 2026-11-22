import { type DragEvent, useEffect, useRef, useState } from 'react'
import { Link, useMatch, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ChatFolder, ChatSession, ChatSessionList } from '../api/types'
import { useFetch } from '../api/useFetch'
import { CHATS_CHANGED } from '../lib/chatEvents'
import RowMenu, { type MenuItem } from './RowMenu'

/** A name being typed: Enter or clicking away saves it, Escape cancels. */
function NameInput({ initial, label, onSave, onCancel }: { initial: string; label: string; onSave: (name: string) => void; onCancel: () => void }) {
  const [value, setValue] = useState(initial)
  const finished = useRef(false)

  function finish(save: boolean) {
    if (finished.current) return
    finished.current = true
    if (save && value.trim() && value.trim() !== initial) onSave(value.trim())
    else onCancel()
  }

  return (
    <input
      type="text"
      className="name-input"
      aria-label={label}
      value={value}
      autoFocus
      maxLength={120}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => finish(true)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') finish(true)
        if (e.key === 'Escape') finish(false)
      }}
    />
  )
}

/**
 * The Co-Pilot's chats: start a new one, go back to an old one, rename, delete, and keep them in folders.
 * The list and every change to it live on the server, so it is the same after a reload.
 */
export default function ChatSidebar() {
  const { data, error, reload } = useFetch<ChatSessionList>('/api/chat/sessions')
  const active = useMatch('/console/:chatId')?.params.chatId
  const navigate = useNavigate()
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<string | null>(null) // "chat:<id>", "folder:<id>" or "new-folder"
  const [problem, setProblem] = useState<string | null>(null)
  const [dragging, setDragging] = useState<string | null>(null) // the chat being dragged
  const [over, setOver] = useState<string | null>(null) // the folder id, or "root", it is over

  useEffect(() => {
    window.addEventListener(CHATS_CHANGED, reload)
    return () => window.removeEventListener(CHATS_CHANGED, reload)
  }, [reload])

  async function change(work: () => Promise<unknown>) {
    setProblem(null)
    try {
      await work()
      reload()
    } catch (e) {
      setProblem((e as Error).message)
    } finally {
      setEditing(null)
    }
  }

  /** Drag and drop: a folder (or the "no folder" area) accepts a dragged chat and moves it there. */
  function dropTarget(key: string, folderId: string | null) {
    return {
      onDragOver: (event: DragEvent) => {
        if (!dragging) return // only our own chats, never a file or text dragged in from elsewhere
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
        if (over !== key) setOver(key)
      },
      onDragLeave: (event: DragEvent) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(null)
      },
      onDrop: (event: DragEvent) => {
        event.preventDefault()
        const id = event.dataTransfer.getData('text/plain') || dragging
        setDragging(null)
        setOver(null)
        const chat = data?.sessions.find((s) => s.id === id)
        if (chat && chat.folder_id !== folderId) {
          void change(() => api.patch(`/api/chat/sessions/${chat.id}`, { folder_id: folderId }))
        }
      },
    }
  }

  const folders = data?.folders ?? []
  const chatsIn = (folderId: string | null) => (data?.sessions ?? []).filter((s) => s.folder_id === folderId)

  function chatMenu(chat: ChatSession): MenuItem[] {
    const moves: MenuItem[] = folders
      .filter((f) => f.id !== chat.folder_id)
      .map((f) => ({ label: `Move to ${f.name}`, onSelect: () => void change(() => api.patch(`/api/chat/sessions/${chat.id}`, { folder_id: f.id })) }))
    if (chat.folder_id) {
      moves.push({ label: 'Remove from folder', onSelect: () => void change(() => api.patch(`/api/chat/sessions/${chat.id}`, { folder_id: null })) })
    }
    return [
      { label: 'Rename', onSelect: () => setEditing(`chat:${chat.id}`) },
      ...moves,
      {
        label: 'Delete',
        confirm: 'Click again to delete for good',
        danger: true,
        onSelect: () =>
          void change(async () => {
            await api.delete(`/api/chat/sessions/${chat.id}`)
            if (active === chat.id) navigate('/console')
          }),
      },
    ]
  }

  function folderMenu(folder: ChatFolder): MenuItem[] {
    return [
      { label: 'Rename', onSelect: () => setEditing(`folder:${folder.id}`) },
      {
        label: 'Delete folder',
        confirm: 'Click again: chats are kept',
        danger: true,
        onSelect: () => void change(() => api.delete(`/api/chat/folders/${folder.id}`)),
      },
    ]
  }

  function chatRow(chat: ChatSession) {
    if (editing === `chat:${chat.id}`) {
      return (
        <li key={chat.id}>
          <NameInput
            initial={chat.title ?? ''}
            label="Chat name"
            onSave={(title) => void change(() => api.patch(`/api/chat/sessions/${chat.id}`, { title }))}
            onCancel={() => setEditing(null)}
          />
        </li>
      )
    }
    return (
      <li
        key={chat.id}
        className={`chat-row${active === chat.id ? ' active' : ''}${dragging === chat.id ? ' dragging' : ''}`}
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData('text/plain', chat.id)
          event.dataTransfer.effectAllowed = 'move'
          setDragging(chat.id)
        }}
        onDragEnd={() => {
          setDragging(null)
          setOver(null)
        }}
      >
        <Link to={`/console/${chat.id}`} aria-current={active === chat.id ? 'page' : undefined} title={chat.title ?? undefined}>
          {chat.title || 'New chat'}
        </Link>
        <RowMenu label={`Actions for ${chat.title ?? 'this chat'}`} items={chatMenu(chat)} />
      </li>
    )
  }

  const ungrouped = chatsIn(null)

  return (
    <section className="chats" aria-label="Chats">
      <h2 className="chats-title">Chats</h2>
      <Link className="new-chat" to="/console">
        + New chat
      </Link>

      {error && <p className="error">Could not load your chats: {error.message}</p>}
      {problem && <p className="error">{problem}</p>}

      <ul className="chat-list">
        {folders.map((folder) => {
          const open = !closed.has(folder.id)
          const inside = chatsIn(folder.id)
          return (
            <li key={folder.id} className={`folder${over === folder.id ? ' drop-target' : ''}`} {...dropTarget(folder.id, folder.id)}>
              {editing === `folder:${folder.id}` ? (
                <NameInput
                  initial={folder.name}
                  label="Folder name"
                  onSave={(name) => void change(() => api.patch(`/api/chat/folders/${folder.id}`, { name }))}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <div className="folder-head">
                  <button
                    type="button"
                    className="folder-toggle"
                    aria-expanded={open}
                    onClick={() =>
                      setClosed((previous) => {
                        const next = new Set(previous)
                        if (!next.delete(folder.id)) next.add(folder.id)
                        return next
                      })
                    }
                  >
                    <span aria-hidden="true">{open ? '▾' : '▸'}</span> {folder.name}
                    <span className="count">{inside.length}</span>
                  </button>
                  <RowMenu label={`Actions for folder ${folder.name}`} items={folderMenu(folder)} />
                </div>
              )}
              {open && (
                <ul className="chat-list nested">
                  {inside.length === 0 ? <li className="muted small-note">Empty. Drag a chat here, or move it from its menu.</li> : inside.map(chatRow)}
                </ul>
              )}
            </li>
          )
        })}
      </ul>

      <ul className={`chat-list root-drop${over === 'root' ? ' drop-target' : ''}`} aria-label="Chats not in a folder" {...dropTarget('root', null)}>
        {ungrouped.map(chatRow)}
        {dragging && data?.sessions.find((s) => s.id === dragging)?.folder_id && (
          <li className="drop-hint">Drop here to take it out of its folder</li>
        )}
      </ul>

      {data && data.sessions.length === 0 && <p className="small-note muted">No chats yet. Ask the Co-Pilot something and it appears here.</p>}

      {editing === 'new-folder' ? (
        <NameInput initial="" label="New folder name" onSave={(name) => void change(() => api.post('/api/chat/folders', { name }))} onCancel={() => setEditing(null)} />
      ) : (
        <button type="button" className="link small-note" onClick={() => setEditing('new-folder')}>
          + New folder
        </button>
      )}
    </section>
  )
}
