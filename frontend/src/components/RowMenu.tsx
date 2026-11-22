import { useEffect, useRef, useState } from 'react'

export interface MenuItem {
  label: string
  onSelect: () => void
  /** Ask once more before doing it: the first click changes the label to this, the second does it. */
  confirm?: string
  danger?: boolean
}

/** A "..." button that opens a small menu of actions. Closes on Escape, on a click elsewhere, and after choosing. */
export default function RowMenu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [place, setPlace] = useState({ top: 0, right: 0 })
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = () => {
      setOpen(false)
      setConfirming(null)
    }
    const onPointer = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) close()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true) // the menu is fixed in place, so close it if anything scrolls
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [open])

  return (
    <div className="row-menu" ref={ref}>
      <button
        type="button"
        className="menu-button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect()
          setPlace({ top: box.bottom + 4, right: window.innerWidth - box.right })
          setOpen(!open)
          setConfirming(null)
        }}
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {open && (
        <div className="menu" role="menu" aria-label={label} style={{ top: place.top, right: place.right }}>
          {items.map((item) => {
            const asking = confirming === item.label
            return (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                className={item.danger ? 'danger' : undefined}
                onClick={() => {
                  if (item.confirm && !asking) {
                    setConfirming(item.label)
                    return
                  }
                  setOpen(false)
                  setConfirming(null)
                  item.onSelect()
                }}
              >
                {asking ? item.confirm : item.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
