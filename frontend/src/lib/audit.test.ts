import { auditParams } from './audit'

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
