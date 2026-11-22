/** The props for the content a tab controls, so the tab and its panel point at each other. */
export function tabPanelProps(id: string, prefix = 'tab') {
  return { role: 'tabpanel', id: `${prefix}-panel-${id}`, 'aria-labelledby': `${prefix}-${id}` } as const
}
