import type { Draft, RunDetail, RunSummary, Step } from '../api/types'

export const NOTES = 'Meeting 12 Nov. Customers keep asking to reset their password by email. Admins need an audit trail.'
export const RESET = 'Customers keep asking to reset their password by email.'
export const AUDIT = 'Admins need an audit trail.'

export function draft(id: string, summary: string, quote: string, over: Partial<Draft> = {}): Draft {
  const start = NOTES.indexOf(quote)
  const payload = {
    issue_type: 'Story',
    summary,
    description: `Details for ${summary}.`,
    acceptance_criteria: ['It works as described'],
    labels: [],
  }
  return {
    id,
    kind: 'backlog_item',
    status: 'proposed',
    payload,
    edited_payload: null,
    effective: payload,
    parent_change_id: null,
    sources: [{ quote, start: start < 0 ? null : start, end: start < 0 ? null : start + quote.length }],
    reasoning: 'The notes ask for this directly.',
    assumptions: 'NA',
    action_class: 'structural',
    created_issue_key: null,
    issue_url: null,
    error: null,
    ...over,
  }
}

export function runSummary(id: string, over: Partial<RunSummary> = {}): RunSummary {
  return {
    id,
    mode: 'M2',
    task_type: 'p1',
    status: 'awaiting_review',
    scope: 'pasted text',
    agent: 'orchestrator:gemini-3.6-flash',
    created_at: '2026-11-20T08:00:00Z',
    ready_at: '2026-11-20T08:01:00Z',
    decided_at: null,
    comment: null,
    rerun_of: null,
    model: 'gemini-3.6-flash',
    input_tokens: 593,
    output_tokens: 373,
    draft_count: 2,
    ...over,
  }
}

export function runDetail(id = 'run-1', over: Partial<RunDetail> = {}): RunDetail {
  return {
    run: runSummary(id),
    input_text: NOTES,
    instructions: null,
    story_key: null,
    parent_story: null,
    drafts: [draft('d1', 'Password reset', RESET), draft('d2', 'Login audit', AUDIT, { assumptions: 'Logs are kept for 90 days' })],
    steps: [],
    status_note: 'Nothing has been created in Jira yet. Review the drafts, then approve the ones you want.',
    editable: true,
    can_decide: true,
    seconds_to_decision: null,
    ...over,
  }
}

export function step(id: number, phase: string, state: string, over: Partial<Step> = {}): Step {
  return { id, ts: '2026-11-20T08:00:00Z', phase, state, tool: null, detail: null, ...over }
}
