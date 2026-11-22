import { useState } from 'react'
import { api } from '../api/client'
import type { ConnectionTest, Deleted, Mode, Settings as SettingsData } from '../api/types'
import { useFetch } from '../api/useFetch'
import { ErrorState, PageHeader } from '../components/PageParts'
import Spinner from '../components/Spinner'
import { plural } from '../lib/format'

const README_URL = 'https://github.com/CogniPM-Team/Cogni-PM#readme'

/** What a mode can do, in a sentence, from what the gateway says it may do. */
function reach(mode: Mode): string {
  if (mode.can_commit) return 'Can create issues in Jira by itself.'
  if (mode.can_stage_drafts) return 'Drafts issues. A person approves every one before it reaches Jira.'
  return 'Only reads Jira. It cannot draft or create anything.'
}

type Outcome = { state: 'idle' } | { state: 'testing' } | { state: 'done'; result: ConnectionTest } | { state: 'failed'; message: string }

/** One connection: a Test button and, once pressed, what happened. */
function Connection({
  title,
  facts,
  path,
  buttonHint,
}: {
  title: string
  facts: string[]
  path: string
  buttonHint?: string
}) {
  const [outcome, setOutcome] = useState<Outcome>({ state: 'idle' })

  async function test() {
    setOutcome({ state: 'testing' })
    try {
      setOutcome({ state: 'done', result: await api.post<ConnectionTest>(path) })
    } catch (e) {
      setOutcome({ state: 'failed', message: (e as Error).message })
    }
  }

  return (
    <div className="connection">
      <div className="connection-head">
        <div>
          <h3>{title}</h3>
          {facts.map((fact) => (
            <div key={fact} className="meta">
              {fact}
            </div>
          ))}
        </div>
        <button type="button" disabled={outcome.state === 'testing'} onClick={() => void test()}>
          {outcome.state === 'testing' && <Spinner />}
          {outcome.state === 'testing' ? 'Testing...' : 'Test'}
        </button>
      </div>
      {buttonHint && <p className="meta">{buttonHint}</p>}
      <div aria-live="polite">
        {outcome.state === 'done' && outcome.result.ok && (
          <p className="notice good" role="status">
            {outcome.result.detail}
          </p>
        )}
        {outcome.state === 'done' && !outcome.result.ok && (
          <p className="error" role="alert">
            {outcome.result.problem}
          </p>
        )}
        {outcome.state === 'failed' && (
          <p className="error" role="alert">
            Could not run the test: {outcome.message}
          </p>
        )}
      </div>
    </div>
  )
}

/** A destructive button that asks once, says what it did, and says what it leaves alone. */
function EraseButton({
  label,
  warning,
  run,
  done,
}: {
  label: string
  warning: string
  run: () => Promise<Deleted>
  done: (count: number) => string
}) {
  const [step, setStep] = useState<'idle' | 'asking' | 'working'>('idle')
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)

  async function erase() {
    setStep('working')
    try {
      setResult({ ok: true, text: done((await run()).deleted) })
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message })
    }
    setStep('idle')
  }

  return (
    <div className="erase">
      {step === 'idle' ? (
        <button type="button" onClick={() => setStep('asking')}>
          {label}
        </button>
      ) : (
        <div className="confirm" role="alertdialog" aria-label={label}>
          <span>{warning}</span>
          <button type="button" className="primary small" disabled={step === 'working'} onClick={() => void erase()}>
            {step === 'working' ? 'Deleting...' : 'Yes, delete'}
          </button>
          <button type="button" className="small" disabled={step === 'working'} onClick={() => setStep('idle')}>
            Cancel
          </button>
        </div>
      )}
      {result && (
        <p className={result.ok ? 'meta' : 'error'} role={result.ok ? 'status' : 'alert'}>
          {result.text}
        </p>
      )}
    </div>
  )
}

export default function Settings() {
  const settings = useFetch<SettingsData>('/api/settings')
  const modes = useFetch<Mode[]>('/api/modes')

  if (settings.loading) return <p className="muted">Loading...</p>
  if (settings.error || !settings.data) {
    return <ErrorState title="Could not load the settings" message={settings.error?.message} onRetry={settings.reload} />
  }
  const s = settings.data

  return (
    <>
      <PageHeader description="How this CogniPM is set up, and what the AI is allowed to do. To change a connection, edit the .env file and restart." />

      <section className="card settings-section" aria-labelledby="set-connections">
        <h2 id="set-connections">Connections</h2>
        <Connection
          title="Jira"
          path="/api/settings/test-jira"
          facts={[`Site ${s.jira_host}`, `Project ${s.jira_project}`, s.story_points_field_set ? 'Story points field set' : 'No story points field']}
        />
        <Connection
          title="AI model"
          path="/api/settings/test-model"
          buttonHint="The test sends one tiny request, so it uses a few tokens."
          facts={[`Model ${s.ai_model}`, s.ai_key_set ? 'Key is set' : 'No key set (GEMINI_API_KEY)']}
        />
      </section>

      <section className="card settings-section" aria-labelledby="set-modes">
        <h2 id="set-modes">What each mode can do</h2>
        <p className="meta">This list comes from the tools the system actually gives each mode, so it cannot drift from what is enforced.</p>
        {modes.loading && <p className="muted">Loading...</p>}
        {modes.error && <ErrorState title="Could not load the modes" message={modes.error.message} onRetry={modes.reload} />}
        {modes.data?.map((mode) => (
          <div key={mode.id} className="mode-block">
            <h3>
              {mode.name}
              {mode.id === 'M3' && <span className="soon">Not available yet</span>}
            </h3>
            <p>{reach(mode)}</p>
            <ul className="tool-list">
              {mode.tools.map((tool) => (
                <li key={tool}>
                  <code>{tool}</code> <span className="meta">{mode.tool_help[tool]}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section className="card settings-section" aria-labelledby="set-rules">
        <h2 id="set-rules">Rules and limits</h2>
        <p>
          One run may draft or create at most <strong>{plural(s.max_items_per_run, 'issue')}</strong>.
        </p>
        <p className="meta">Every draft is checked against these {s.guardrails.length} rules before you see it and again when it is approved.</p>
        <ul className="rule-list">
          {s.guardrails.map((rule) => (
            <li key={rule.name}>
              <strong>{rule.name.replace(/_/g, ' ')}</strong>
              <span className="meta">{rule.description}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card settings-section" aria-labelledby="set-privacy">
        <h2 id="set-privacy">Data and privacy</h2>
        <p>What is sent to the AI model:</p>
        <ul>
          {s.sent_to_model.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p>
          Inputs, chats, drafts and the activity log are kept in this install&apos;s own database. The activity log cannot be
          changed or deleted.
        </p>
        <h3>Delete my stored inputs</h3>
        <EraseButton
          label="Delete all saved documents"
          warning="This removes the text of every document in your library for good. Runs keep their own copy."
          run={() => api.delete<Deleted>('/api/documents')}
          done={(n) => `Deleted ${plural(n, 'document')}.`}
        />
        <EraseButton
          label="Erase the saved input of past runs"
          warning="This erases the pasted notes and instructions of runs you already approved or rejected. Their drafts and the activity log stay, but you will no longer see the original text beside the drafts."
          run={() => api.post<Deleted>('/api/settings/clear-run-inputs')}
          done={(n) => `Erased the saved input of ${plural(n, 'run')}.`}
        />
      </section>

      <section className="card settings-section" aria-labelledby="set-about">
        <h2 id="set-about">About</h2>
        <p>
          CogniPM version <strong>{s.version}</strong>, a research prototype.{' '}
          <a href={README_URL} target="_blank" rel="noopener noreferrer">
            Read the guide
          </a>
        </p>
      </section>
    </>
  )
}
