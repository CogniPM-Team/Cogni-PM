// The one list of pages in the sidebar. The sidebar and the page titles both read it, so adding a page is one line
// here plus its route in App.tsx.
//
// A page that is not built yet is listed with `enabled: false` and simply does not appear: nothing in the sidebar
// should ever lead to an empty or "coming soon" page. Flip it to true in the same change that adds the page.

export type NavSection = 'WORK' | 'RECORD'

export interface NavItem {
  id: string
  label: string
  path: string
  section: NavSection
  enabled: boolean
  /** Show a count next to the label. Only Approvals has one: what is waiting for you. */
  badge?: 'waiting'
}

export const SECTIONS: NavSection[] = ['WORK', 'RECORD']

export const NAV_ITEMS: NavItem[] = [
  { id: 'home', label: 'Home', path: '/home', section: 'WORK', enabled: false }, // U1
  { id: 'console', label: 'Agent console', path: '/console', section: 'WORK', enabled: true },
  { id: 'approvals', label: 'Approvals', path: '/approvals', section: 'WORK', enabled: true, badge: 'waiting' },
  { id: 'activity', label: 'Activity log', path: '/activity', section: 'RECORD', enabled: true },
]

/** The sidebar: only enabled items, grouped by section in the order of SECTIONS. Empty sections are dropped. */
export function visibleNav(items: NavItem[] = NAV_ITEMS): { section: NavSection; items: NavItem[] }[] {
  return SECTIONS.map((section) => ({
    section,
    items: items.filter((item) => item.enabled && item.section === section),
  })).filter((group) => group.items.length > 0)
}

/** The title and breadcrumb for the top bar, from the page the address belongs to. */
export function pageInfo(pathname: string, items: NavItem[] = NAV_ITEMS): { title: string; crumb: string } {
  if (pathname.startsWith('/approvals/')) return { title: 'Review a run', crumb: 'Approvals › Review' }
  const item = items.find((i) => i.enabled && (pathname === i.path || pathname.startsWith(`${i.path}/`)))
  const title = item?.label ?? 'CogniPM'
  return { title, crumb: title }
}
