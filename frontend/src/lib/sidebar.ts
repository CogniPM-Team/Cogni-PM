const KEY = 'cognipm.sidebar.collapsed'

/** Whether the sidebar was left collapsed last time. Storage can be blocked, so a failure just means "expanded". */
export function readCollapsed(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function saveCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(KEY, collapsed ? '1' : '0')
  } catch {
    // not remembered across visits, but it still works for now
  }
}
