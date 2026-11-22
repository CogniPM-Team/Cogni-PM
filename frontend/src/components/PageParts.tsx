import { type ReactNode, useRef } from 'react'

/** Under the top bar: a sentence saying what the page is for, and optional buttons on the right. */
export function PageHeader({ description, actions }: { description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      {description && <p className="page-subtitle">{description}</p>}
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

/** Nothing here yet: say so in a sentence, and (when there is one) offer the obvious next step. */
export function EmptyState({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state">
      {title && <h3>{title}</h3>}
      <p>{children}</p>
      {action}
    </div>
  )
}

/** Something went wrong: what, in plain words, and (when it can help) a button to try again. */
export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string
  message?: string
  onRetry?: () => void
}) {
  return (
    <div className="error-state" role="alert">
      <strong>{title}</strong>
      {message && <p>{message}</p>}
      {onRetry && (
        <button type="button" className="small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

/** A label and a number, for Home and Insights. */
export function StatCard({ label, value, hint, source }: { label: string; value: ReactNode; hint?: string; source?: string }) {
  return (
    <div className="stat-card" title={source}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  )
}

export interface Tab {
  id: string
  label: string
  count?: number
}

/**
 * A row of tabs. One tab is in the tab order at a time; the arrow keys, Home and End move between them and select as
 * they go. The caller shows the content (put `{...tabPanelProps(value)}` from `lib/tabs` on it).
 */
export function Tabs({
  tabs,
  value,
  onChange,
  label,
  prefix = 'tab',
}: {
  tabs: Tab[]
  value: string
  onChange: (id: string) => void
  label: string
  prefix?: string
}) {
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({})

  function select(id: string) {
    onChange(id)
    buttons.current[id]?.focus()
  }

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const last = tabs.length - 1
    const target =
      event.key === 'ArrowRight' ? (index === last ? 0 : index + 1)
      : event.key === 'ArrowLeft' ? (index === 0 ? last : index - 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : null
    if (target === null) return
    event.preventDefault()
    select(tabs[target].id)
  }

  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => {
        const selected = tab.id === value
        return (
          <button
            key={tab.id}
            ref={(element) => {
              buttons.current[tab.id] = element
            }}
            type="button"
            role="tab"
            id={`${prefix}-${tab.id}`}
            aria-selected={selected}
            aria-controls={`${prefix}-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.label}
            {tab.count !== undefined && <span className="tab-count">{tab.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
