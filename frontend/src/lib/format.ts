export const MODE_NAMES: Record<string, string> = { M1: 'Co-Pilot', M2: 'Super-Pilot', M3: 'Auto-Pilot' }
export const TASK_NAMES: Record<string, string> = { p1: 'Draft backlog', p2: 'Break down a story' }

export const STATUS_LABELS: Record<string, string> = {
  running: 'Working',
  awaiting_review: 'Waiting for you',
  applied: 'Approved',
  rejected: 'Rejected',
  failed: 'Failed',
  proposed: 'Proposed',
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
}

/** "3 min ago", "2 h ago", "yesterday"... for how long something has been waiting. */
export function ago(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

export function duration(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)} s`
  const minutes = seconds / 60
  if (minutes < 90) return `${Math.round(minutes)} min`
  return `${(minutes / 60).toFixed(1)} h`
}

/** Who did it, in words a PM would use. Actors look like `human:reviewer` or `agent:orchestrator:<model>[:chat]`. */
export function actorLabel(actor: string): string {
  if (actor.startsWith('human:')) return 'You'
  if (actor.startsWith('agent:orchestrator:')) return `Agent (${actor.split(':')[2]})`
  if (actor.startsWith('agent:')) return `Agent (${actor.slice(6)})`
  return actor
}

const ACTIONS: Record<string, string> = {
  start_run: 'Started a run',
  propose_backlog_item: 'Drafted a backlog item',
  propose_task_breakdown: 'Drafted a sub-task',
  finish_run: 'Finished drafting',
  edit_draft: 'Edited a draft',
  drop_draft: 'Left a draft out',
  approve: 'Approved',
  reject: 'Rejected',
  rerun: 'Asked for another attempt',
  create_issue: 'Created a Jira issue',
  commit_changes: 'Committed changes',
  chat_turn: 'Answered a question',
  provenance_comment: 'Added a comment in Jira',
}

export function actionLabel(action: string): string {
  if (action.startsWith('guardrail:')) return `Refused by ${action.slice(10).replaceAll('_', ' ')}`
  return ACTIONS[action] ?? action.replaceAll('_', ' ')
}
