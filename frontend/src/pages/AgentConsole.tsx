import { useCallback, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import ChatPanel from '../components/ChatPanel'
import ChatSidebar from '../components/ChatSidebar'
import RunProgress, { type Snapshot } from '../components/RunProgress'
import TaskInspector from '../components/TaskInspector'
import TaskStarter, { type Task } from '../components/TaskStarter'

type Mode = 'M1' | 'M2'

const MODES: { id: Mode | 'M3'; name: string; hint: string; disabled?: boolean }[] = [
  { id: 'M1', name: 'Co-Pilot', hint: 'Ask questions. Read only.' },
  { id: 'M2', name: 'Super-Pilot', hint: 'Give it a task. You approve every change.' },
  { id: 'M3', name: 'Auto-Pilot', hint: 'Coming later', disabled: true },
]

export default function AgentConsole() {
  const { chatId } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // The mode lives in the address, so "New chat" is always the Co-Pilot and a chat is never mistaken for a task.
  const mode: Mode = !chatId && params.get('mode') === 'M2' ? 'M2' : 'M1'
  const [runs, setRuns] = useState<{ id: string; task: Task }[]>([])
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const onSnapshot = useCallback((s: Snapshot) => setSnapshot(s), [])

  return (
    <div className="console">
      <ChatSidebar />
      <div className="console-main">
        <div className="modes" role="group" aria-label="Mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`mode-option mode-${m.id}`}
              aria-pressed={mode === m.id}
              disabled={m.disabled}
              onClick={() => {
                if (m.id === 'M2') navigate('/console?mode=M2')
                else if (mode !== 'M1') navigate('/console')
              }}
            >
              {m.name}
              <small>{m.hint}</small>
            </button>
          ))}
        </div>

        {mode === 'M1' ? (
          <ChatPanel chatId={chatId} />
        ) : (
          <div className="console-body">
            <TaskStarter onStarted={(id, task) => setRuns((r) => [{ id, task }, ...r])} />
            {runs.length > 0 && (
              <section aria-label="Runs this session" style={{ marginTop: 24 }}>
                <h2>This session</h2>
                {runs.map((run, index) => (
                  <RunProgress key={run.id} runId={run.id} task={run.task} latest={index === 0} onSnapshot={onSnapshot} />
                ))}
              </section>
            )}
          </div>
        )}
      </div>
      <TaskInspector snapshot={snapshot} />
    </div>
  )
}
