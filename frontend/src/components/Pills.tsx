import { MODE_NAMES, STATUS_LABELS } from '../lib/format'

export function ModePill({ mode }: { mode: string }) {
  return <span className={`pill mode-${mode}`}>{MODE_NAMES[mode] ?? mode}</span>
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`status status-${status}`}>{STATUS_LABELS[status] ?? status}</span>
}
