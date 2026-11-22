import type { AuditRow } from '../api/types'
import { auditParams, groupByRun, runTitle } from './audit'

const base = { filter: 'all', q: '', from: '', to: '' } as const

describe('auditParams', () => {
  it('sends only what was chosen', () => {
    expect(auditParams(base)).toBe('filter=all')
    expect(auditParams({ ...base, filter: 'rejected' }, { limit: '500' })).toBe('filter=rejected&limit=500')
  })

  it('trims the search and ignores a blank one', () => {
    expect(auditParams({ ...base, q: '  invoices ' })).toBe('filter=all&q=invoices')
    expect(auditParams({ ...base, q: '   ' })).toBe('filter=all')
  })

  it('turns a chosen day into that whole day in the viewer\'s time zone, with an exclusive end', () => {
    const params = new URLSearchParams(auditParams({ ...base, from: '2026-11-18', to: '2026-11-18' }))

    const start = new Date(params.get('from')!)
    const end = new Date(params.get('to')!)
    expect(start.getTime()).toBe(new Date(2026, 10, 18).getTime()) // local midnight, whatever the zone
    expect(end.getTime()).toBe(new Date(2026, 10, 19).getTime()) // midnight starting the next day
  })

  it('encodes the search so punctuation survives', () => {
    expect(new URLSearchParams(auditParams({ ...base, q: '100% & more' })).get('q')).toBe('100% & more')
  })
})

const entry = (id: number, run_id: string | null, action = 'approve'): AuditRow => ({
  id,
  ts: '2026-11-20T08:00:00Z',
  run_id,
  actor: 'human:reviewer',
  mode: 'M2',
  action,
  outcome: 'ok',
  detail: null,
  before: null,
  after: null,
})

describe('groupByRun', () => {
  it('puts the entries of one run together, in the place of its newest entry', () => {
    const items = groupByRun([entry(6, 'b'), entry(5, 'a'), entry(4, 'b'), entry(3, 'a'), entry(2, 'a')])

    expect(items.map((i) => [i.runId, i.rows.map((r) => r.id)])).toEqual([
      ['b', [6, 4]],
      ['a', [5, 3, 2]],
    ])
  })

  it('leaves an entry that belongs to no run standing alone, each on its own', () => {
    const items = groupByRun([entry(4, null, 'chat_turn'), entry(3, 'a'), entry(2, null, 'delete_chat')])

    expect(items.map((i) => [i.key, i.runId])).toEqual([
      ['entry-4', null],
      ['a', 'a'],
      ['entry-2', null],
    ])
  })

  it('has nothing to show for no entries', () => {
    expect(groupByRun([])).toEqual([])
  })
})

describe('runTitle', () => {
  it('names the task from what the agent proposed, and falls back to a plain word', () => {
    expect(runTitle([entry(1, 'a', 'propose_backlog_item'), entry(2, 'a')])).toBe('Draft backlog')
    expect(runTitle([entry(1, 'a', 'propose_task_breakdown')])).toBe('Break down a story')
    expect(runTitle([entry(1, 'a', 'approve')])).toBe('Run')
  })
})
