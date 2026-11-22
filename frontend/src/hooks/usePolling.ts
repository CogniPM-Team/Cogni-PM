import { useEffect } from 'react'

/** Calls `tick` every `ms` while `active`. For a page that must notice a change nothing announces, such as a run
 *  moving from working to paused: the event stream carries steps, not status changes in between. */
export function usePolling(tick: () => void, active: boolean, ms = 2000) {
  useEffect(() => {
    if (!active) return
    const timer = setInterval(tick, ms)
    return () => clearInterval(timer)
  }, [tick, active, ms])
}
