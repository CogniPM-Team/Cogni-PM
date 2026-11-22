import { useState } from 'react'
import { api } from '../api/client'
import type { RunDetail } from '../api/types'
import Icon from './Icon'

const LIVE = ['running', 'paused', 'waiting_for_information']

/** What is happening to the run right now, in a sentence, including a request that has not taken effect yet. */
function stateLine(detail: RunDetail): string {
  const { control, run } = detail
  if (run.status === 'paused') return 'Paused. Nothing happens until you resume it.'
  if (run.status === 'waiting_for_information') return 'The agent has a question for you.'
  if (control === 'pause') return 'Pausing after the current step...'
  if (control === 'stop') return 'Stopping after the current step...'
  if (control === 'cancel') return 'Cancelling after the current step...'
  return 'The agent is working.'
}

/**
 * Pause, resume, stop and cancel a run that has not finished, and answer the agent when it asks something. A request
 * takes effect between two steps of the run, never in the middle of one, so the sentence at the top says what is
 * pending. Only a PM gets the buttons; everyone else sees what is happening.
 */
export default function RunControls({ detail, onChanged }: { detail: RunDetail; onChanged: () => void }) {
  const { run, control, question, can_control: canControl, can_answer: canAnswer } = detail
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<'stop' | 'cancel' | null>(null)
  const [answer, setAnswer] = useState('')

  if (!LIVE.includes(run.status)) return null

  async function act(action: string, body?: unknown) {
    setBusy(true)
    setProblem(null)
    try {
      await api.post(`/api/runs/${run.id}/${action}`, body)
      setConfirming(null)
      setAnswer('')
      onChanged()
    } catch (e) {
      setProblem((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const ending = control === 'stop' || control === 'cancel' // asked for, and about to happen: nothing more to ask
  const holding = run.status === 'paused' || control === 'pause'

  return (
    <section className="card run-controls" aria-label="Run controls">
      <div className="run-controls-head">
        <p role="status">{stateLine(detail)}</p>
        {canControl && !ending && run.status !== 'waiting_for_information' && (
          <div className="control-buttons">
            {holding ? (
              <button type="button" disabled={busy} onClick={() => void act('resume')}>
                <Icon name="play" size={14} />
                {run.status === 'paused' ? 'Resume' : 'Keep going'}
              </button>
            ) : (
              <button type="button" disabled={busy} onClick={() => void act('pause')}>
                <Icon name="pause" size={14} />
                Pause
              </button>
            )}
            <button type="button" disabled={busy} onClick={() => setConfirming('stop')}>
              <Icon name="stop" size={14} />
              Stop
            </button>
            <button type="button" className="reject" disabled={busy} onClick={() => setConfirming('cancel')}>
              <Icon name="close" size={14} />
              Cancel
            </button>
          </div>
        )}
      </div>

      {run.status === 'waiting_for_information' && question && (
        <div className="question">
          <strong>The agent asks</strong>
          <p>{question}</p>
        </div>
      )}

      {canAnswer && (
        <form
          className="answer-form"
          onSubmit={(event) => {
            event.preventDefault()
            void act('answer', { text: answer })
          }}
        >
          <label className="field">
            <span>Your answer</span>
            <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={4000} />
          </label>
          <p className="meta">The agent carries on from where it stopped. It will not ask again: it drafts what it honestly can.</p>
          <div className="control-buttons">
            <button type="submit" className="primary" disabled={busy || !answer.trim()}>
              {busy ? 'Sending...' : 'Send answer'}
            </button>
            <button type="button" disabled={busy} onClick={() => setConfirming('stop')}>
              Stop the run
            </button>
            <button type="button" className="reject" disabled={busy} onClick={() => setConfirming('cancel')}>
              Cancel the run
            </button>
          </div>
        </form>
      )}

      {!canControl && run.status === 'waiting_for_information' && (
        <p className="meta">A PM needs to answer this.</p>
      )}

      {confirming && (
        <div className="confirm" role="alertdialog" aria-label={confirming === 'stop' ? 'Confirm stop' : 'Confirm cancel'}>
          <span>
            {confirming === 'stop'
              ? 'Stop this run? It ends after the current step. Anything already staged stays. Nothing is created in Jira.'
              : 'Cancel this run? It ends after the current step and its drafts are discarded. Nothing is created in Jira.'}
          </span>
          <button type="button" className="primary small" disabled={busy} onClick={() => void act(confirming)}>
            {confirming === 'stop' ? 'Yes, stop it' : 'Yes, cancel it'}
          </button>
          <button type="button" className="small" disabled={busy} onClick={() => setConfirming(null)}>
            Keep it going
          </button>
        </div>
      )}

      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
    </section>
  )
}
