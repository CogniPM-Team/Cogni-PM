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

/** "gemini-3.6-flash" becomes "Gemini 3.6 Flash". */
export function prettyName(raw: string): string {
  return raw
    .split(/[-_]/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Who did it, in words a PM would use. The stored actor is `human:reviewer`, or an agent written with or
 * without an `agent:` prefix: `orchestrator:<model>[:chat]`, `claude-code`, and so on.
 */
export function actorLabel(actor: string): string {
  if (actor.startsWith('human:')) return 'You'
  const agent = actor.replace(/^agent:/, '')
  const parts = agent.split(':')
  const name = parts[0] === 'orchestrator' && parts[1] ? parts[1] : parts[0]
  return `${prettyName(name)} Agent`
}

export type DetailPart = string | { pill: string; title?: string }

const DRAFT_KINDS: Record<string, string> = { backlog_item: 'backlog item', subtask: 'sub-task', task: 'task' }

/**
 * An activity entry's detail in plain words, with ids and keys as small pills. Returns null when there is
 * nothing friendlier to say, and the raw text is shown instead.
 */
export function describeDetail(action: string, detail: string | null): DetailPart[] | null {
  if (!detail) return null
  let m: RegExpExecArray | null
  if (action === 'chat_turn' && (m = /^session ([\w-]+); (\d+) read\(s\)$/.exec(detail))) {
    return ['Session ', { pill: m[1].slice(0, 8), title: m[1] }, ` · ${plural(Number(m[2]), 'read')} of Jira`]
  }
  if (action === 'create_issue' && (m = /^(\w+) draft [\w-]+ -> (\S+)$/.exec(detail))) {
    return ['Created ', { pill: m[2] }, ` from a ${DRAFT_KINDS[m[1]] ?? m[1]} draft`]
  }
  if (action === 'start_run' && (m = /^task_type=(\w+) scope=(.*)$/.exec(detail))) {
    return [`${TASK_NAMES[m[1]] ?? m[1]} · ${m[2]}`]
  }
  if (action.startsWith('propose_') && (m = /^\w+: (.*)$/.exec(detail))) return [m[1]]
  if (action === 'edit_draft' && (m = /^\w+ [\w-]+: changed \[(.*)\]$/.exec(detail))) {
    return [`Changed ${m[1].replaceAll("'", '').replaceAll('_', ' ')}`]
  }
  return null
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
