import { useCallback, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import ChatPanel from '../components/ChatPanel'
import ChatSidebar from '../components/ChatSidebar'
import RunHistory from '../components/RunHistory'
import RunProgress, { type Snapshot } from '../components/RunProgress'
import TaskInspector from '../components/TaskInspector'
import TaskStarter, { type Task } from '../components/TaskStarter'

type Mode = 'M1' | 'M2'

const TABS: { id: Mode | 'M3'; name: string; hint: string; disabled?: boolean }[] = [
  { id: 'M1', name: 'Co-Pilot', hint: 'Ask questions about the project. It only reads Jira: it cannot draft or create anything.' },
  { id: 'M2', name: 'Super-Pilot', hint: 'Give it a task. It drafts Jira issues and you approve every change.' },
  { id: 'M3', name: 'Auto-Pilot', hint: '', disabled: true },
]

export default function AgentConsole() {
  const { chatId } = useParams()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // The mode is in the address (`?mode=M2`) and the open chat is in the path, so switching mode keeps the chat you
  // were in, and "+ New chat" or a chat in the list (which carry no mode) always mean the Co-Pilot.
  const mode: Mode = params.get('mode') === 'M2' ? 'M2' : 'M1'
  const [runs, setRuns] = useState<{ id: string; task: Task }[]>([])
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const onSnapshot = useCallback((s: Snapshot) => setSnapshot(s), [])

  return (
    <div className="console">
      {/* The frame is the same in every mode: a history list on the left (chats for the Co-Pilot, tasks for the
          Super-Pilot) and the work area beside it. Only what fills them changes. */}
      <aside className="console-side">
        <div className="mode-pane" hidden={mode !== 'M1'}>
          <ChatSidebar />
        </div>
        <div className="mode-pane" hidden={mode !== 'M2'}>
          <RunHistory />
        </div>
      </aside>

      <div className="console-main">
        <header className="console-head">
          <div className="mode-tabs" role="group" aria-label="Mode">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`mode-${tab.id}`}
                aria-pressed={mode === tab.id}
                disabled={tab.disabled}
                onClick={() => navigate(tab.id === 'M2' ? `${pathname}?mode=M2` : pathname)}
              >
                {tab.name}
                {tab.disabled && <span className="soon">Soon</span>}
              </button>
            ))}
          </div>
          <p className="mode-hint" aria-live="polite">
            {TABS.find((tab) => tab.id === mode)?.hint}
          </p>
        </header>

        {/* Both stay mounted and the other is hidden, so an unsent question, an open chat and the runs started
            here are all still there when you come back to a mode. */}
        <div className="mode-pane" hidden={mode !== 'M1'}>
          <ChatPanel chatId={chatId} />
        </div>
        <div className="mode-pane console-body" hidden={mode !== 'M2'}>
          <div className="task-layout">
            <div className="task-col">
              <TaskStarter initialTask={params.get('task') === 'p2' ? 'p2' : 'p1'} onStarted={(id, task) => setRuns((r) => [{ id, task }, ...r])} />
            </div>
            <div className="task-col">
              {runs.length === 0 ? (
                <div className="card results-empty">
                  <h3>Progress and results</h3>
                  <p className="muted">Start a task and its steps appear here as they happen, then the drafts for you to review.</p>
                </div>
              ) : (
                <section aria-label="Runs this session">
                  <TaskInspector snapshot={snapshot} />
                  {runs.map((run, index) => (
                    <RunProgress key={run.id} runId={run.id} task={run.task} latest={index === 0} onSnapshot={onSnapshot} />
                  ))}
                </section>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
