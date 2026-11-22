import { NAV_ITEMS, type NavItem, pageInfo, visibleNav } from './nav'
import { tabPanelProps } from './tabs'

const item = (over: Partial<NavItem>): NavItem => ({
  id: 'x',
  label: 'X',
  path: '/x',
  section: 'WORK',
  enabled: true,
  ...over,
})

describe('the sidebar config', () => {
  it('lists only enabled pages, grouped by section in order', () => {
    const groups = visibleNav([
      item({ id: 'a', label: 'A', path: '/a' }),
      item({ id: 'later', label: 'Later', path: '/later', enabled: false }),
      item({ id: 'log', label: 'Log', path: '/log', section: 'RECORD' }),
    ])

    expect(groups.map((g) => [g.section, g.items.map((i) => i.label)])).toEqual([
      ['WORK', ['A']],
      ['RECORD', ['Log']],
    ])
  })

  it('drops a section whose pages are all switched off, so no empty heading is shown', () => {
    const groups = visibleNav([item({ enabled: false }), item({ id: 'log', section: 'RECORD', path: '/log' })])

    expect(groups.map((g) => g.section)).toEqual(['RECORD'])
  })

  it('has unique, absolute paths for every enabled page', () => {
    const enabled = NAV_ITEMS.filter((i) => i.enabled)

    expect(new Set(enabled.map((i) => i.path)).size).toBe(enabled.length)
    expect(enabled.every((i) => i.path.startsWith('/'))).toBe(true)
  })

  it('keeps Home out of the sidebar until it exists', () => {
    expect(
      visibleNav()
        .flatMap((g) => g.items)
        .map((i) => i.id),
    ).not.toContain('home')
  })
})

describe('pageInfo', () => {
  it('names the page from the address, including pages under it', () => {
    expect(pageInfo('/console')).toEqual({ title: 'Agent console', crumb: 'Agent console' })
    expect(pageInfo('/console/some-chat').title).toBe('Agent console')
    expect(pageInfo('/activity').title).toBe('Activity log')
    expect(pageInfo('/approvals/abc')).toEqual({ title: 'Review a run', crumb: 'Approvals › Review' })
  })

  it('does not name a page that is switched off, and falls back to the product name', () => {
    expect(pageInfo('/home').title).toBe('CogniPM')
    expect(pageInfo('/nowhere').title).toBe('CogniPM')
    expect(pageInfo('/consolex').title).toBe('CogniPM') // a different word, not a page under /console
  })
})

describe('tabPanelProps', () => {
  it('points a panel at its tab', () => {
    expect(tabPanelProps('waiting')).toEqual({
      role: 'tabpanel',
      id: 'tab-panel-waiting',
      'aria-labelledby': 'tab-waiting',
    })
    expect(tabPanelProps('x', 'filter')['aria-labelledby']).toBe('filter-x')
  })
})
