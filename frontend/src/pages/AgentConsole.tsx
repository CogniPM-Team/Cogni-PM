import { useCallback, useState } from 'react'
import ChatPanel from '../components/ChatPanel'
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
  const [mode, setMode] = useState<Mode>('M1')
  const [runs, setRuns] = useState<{ id: string; task: Task }[]>([])
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const onSnapshot = useCallback((s: Snapshot) => setSnapshot(s), [])

  return (
    <div className="console">
      <div>
        <div className="modes" role="group" aria-label="Mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`mode-option mode-${m.id}`}
              aria-pressed={mode === m.id}
              disabled={m.disabled}
              onClick={() => setMode(m.id as Mode)}
            >
              {m.name}
              <small>{m.hint}</small>
            </button>
          ))}
        </div>

        {mode === 'M1' ? (
          <ChatPanel />
        ) : (
          <TaskStarter onStarted={(id, task) => setRuns((r) => [{ id, task }, ...r])} />
        )}

        {runs.length > 0 && (
          <section aria-label="Runs this session" style={{ marginTop: 24 }}>
            <h2>This session</h2>
            {runs.map((run, index) => (
              <RunProgress key={run.id} runId={run.id} task={run.task} latest={index === 0} onSnapshot={onSnapshot} />
            ))}
          </section>
        )}
      </div>
      <TaskInspector snapshot={snapshot} />
    </div>
  )
}
