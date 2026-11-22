import { insightsParams, share } from './insights'

describe('share', () => {
  it('says how many out of how many, with the percentage rounded to a whole number', () => {
    expect(share(2, 4)).toEqual({ text: '2 of 4', percent: '50%' })
    expect(share(2, 12)).toEqual({ text: '2 of 12', percent: '17%' })
    expect(share(7, 12).percent).toBe('58%')
    expect(share(12, 12).percent).toBe('100%')
  })

  it('shows no percentage when there is nothing to divide by, never 0%', () => {
    expect(share(0, 0)).toEqual({ text: '', percent: '–' })
  })

  it('shows 0% only when there were decisions and none of them counted', () => {
    expect(share(0, 4).percent).toBe('0%')
  })
})

describe('insightsParams', () => {
  it('sends only what was chosen', () => {
    expect(insightsParams({ from: '', to: '', task: '' })).toBe('')
    expect(insightsParams({ from: '', to: '', task: 'p2' })).toBe('task=p2')
  })

  it('turns the chosen days into that whole span in the viewer own time zone, with an exclusive end', () => {
    const params = new URLSearchParams(insightsParams({ from: '2026-11-18', to: '2026-11-18', task: '' }))

    expect(new Date(params.get('from')!).getTime()).toBe(new Date(2026, 10, 18).getTime())
    expect(new Date(params.get('to')!).getTime()).toBe(new Date(2026, 10, 19).getTime())
  })
})
