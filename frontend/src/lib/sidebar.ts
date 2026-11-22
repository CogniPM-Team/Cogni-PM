/** Where each collapsible panel remembers its state. */
export const SIDEBAR_KEY = 'cognipm.sidebar.collapsed'
export const CONSOLE_LIST_KEY = 'cognipm.console.list.collapsed'

/** Whether a panel was left collapsed last time. Storage can be blocked, so a failure just means "open". */
export function readCollapsed(key: string = SIDEBAR_KEY): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

export function saveCollapsed(collapsed: boolean, key: string = SIDEBAR_KEY): void {
  try {
    localStorage.setItem(key, collapsed ? '1' : '0')
  } catch {
    // not remembered across visits, but it still works for now
  }
}
