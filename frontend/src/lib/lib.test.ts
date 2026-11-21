import type { AuditRow } from '../api/types'
import { AUDIT, draft, NOTES, RESET, step } from '../test/fixtures'
import { auditToCsv, cell } from './csv'
import { actionLabel, actorLabel, ago, duration, plural } from './format'
import { segments } from './spans'
import { traceLines } from './steps'

describe('format', () => {
  it('says how long something has waited, in words', () => {
    const now = new Date('2026-11-20T12:00:00Z')
    expect(ago('2026-11-20T11:59:40Z', now)).toBe('just now')
    expect(ago('2026-11-20T11:30:00Z', now)).toBe('30 min ago')
    expect(ago('2026-11-20T09:00:00Z', now)).toBe('3 h ago')
    expect(ago('2026-11-19T12:00:00Z', now)).toBe('yesterday')
    expect(ago('2026-11-17T12:00:00Z', now)).toBe('3 days ago')
  })

  it('formats durations and plurals', () => {
    expect(duration(42)).toBe('42 s')
    expect(duration(600)).toBe('10 min')
    expect(duration(7200)).toBe('2.0 h')
    expect(plural(1, 'draft')).toBe('1 draft')
    expect(plural(3, 'draft')).toBe('3 drafts')
  })

  it('names who did something and what, the way a PM would', () => {
    expect(actorLabel('human:reviewer')).toBe('You')
    expect(actorLabel('agent:orchestrator:gemini-3.6-flash')).toBe('Agent (gemini-3.6-flash)')
    expect(actorLabel('agent:orchestrator:gemini-3.6-flash:chat')).toBe('Agent (gemini-3.6-flash)')
    expect(actionLabel('create_issue')).toBe('Created a Jira issue')
    expect(actionLabel('guardrail:no_duplicate')).toBe('Refused by no duplicate')
    expect(actionLabel('something_new')).toBe('something new')
  })
})

describe('traceLines', () => {
  it('turns step rows into plain sentences and shows only what is happening now as running', () => {
    const lines = traceLines([
      step(1, 'analysing', 'start'),
      step(2, 'analysing', 'end', { tool: 'search_issues', detail: { existing: 14 } }),
      step(3, 'generating', 'start', { detail: { attempt: 1 } }),
      step(4, 'generating', 'end', { detail: { drafts: 2 } }),
      step(5, 'verifying', 'start'),
    ])

    expect(lines.map((l) => [l.text, l.state])).toEqual([
      ['Looked at 14 existing backlog items to avoid duplicates', 'done'],
      ['Drafted 2 items', 'done'],
      ['Checking each quote against your input', 'running'],
    ])
  })

  it('shows retries, refusals and what was left out', () => {
    const lines = traceLines([
      step(1, 'generating', 'retry', { detail: { code: 429, wait_seconds: 2 } }),
      step(2, 'verifying', 'end', { detail: { kept: 1, problems: ['x', 'y'] } }),
      step(3, 'staging', 'error', { tool: 'propose_backlog_item', detail: { summary: 'Dup', reason: 'already open' } }),
      step(4, 'staging', 'end', { tool: 'finish_run' }),
    ])

    expect(lines.map((l) => l.text)).toEqual([
      'The model is busy (429); trying again in 2 s',
      'Kept 1; left out 2 that could not be traced to your input',
      'Refused "Dup": already open',
      'Ready for your review',
    ])
    expect(lines.map((l) => l.state)).toEqual(['retry', 'done', 'failed', 'done'])
  })
})

describe('segments', () => {
  it('cuts the input so each cited quote can be highlighted where it stands', () => {
    const pieces = segments(NOTES, [draft('d1', 'A', RESET), draft('d2', 'B', AUDIT)])

    expect(pieces.map((p) => p.text).join('')).toBe(NOTES)
    expect(pieces.filter((p) => p.drafts.length).map((p) => [p.text, p.drafts])).toEqual([
      [RESET, ['d1']],
      [AUDIT, ['d2']],
    ])
  })

  it('records both drafts when two cite the same words, and ignores quotes that could not be located', () => {
    const pieces = segments(NOTES, [draft('d1', 'A', RESET), draft('d2', 'B', RESET), draft('d3', 'C', 'not in the text')])

    expect(pieces.find((p) => p.text === RESET)?.drafts).toEqual(['d1', 'd2'])
    expect(pieces.every((p) => !p.drafts.includes('d3'))).toBe(true)
    expect(segments('', [])).toEqual([])
  })
})

describe('csv', () => {
  it('quotes cells, doubles quotes, and defuses anything a spreadsheet would run as a formula', () => {
    expect(cell('plain')).toBe('plain')
    expect(cell('a, b')).toBe('"a, b"')
    expect(cell('say "hi"')).toBe('"say ""hi"""')
    expect(cell('=HYPERLINK("http://evil")')).toBe('"\'=HYPERLINK(""http://evil"")"')
    expect(cell('+1')).toBe("'+1")
    expect(cell(null)).toBe('')
  })

  it('writes a header and one line per entry, including the before and after', () => {
    const row: AuditRow = {
      id: 1,
      ts: '2026-11-20T08:00:00Z',
      run_id: 'r1',
      actor: 'human:reviewer',
      mode: 'M2',
      action: 'edit_draft',
      outcome: 'edited',
      detail: 'changed summary',
      before: { summary: 'old' },
      after: { summary: 'new' },
    }

    const lines = auditToCsv([row]).trim().split('\n')

    expect(lines[0]).toBe('time,run,actor,mode,action,outcome,detail,before,after')
    expect(lines[1]).toContain('human:reviewer,M2,edit_draft,edited,changed summary')
    expect(lines[1]).toContain('"{""summary"":""old""}"')
  })
})
