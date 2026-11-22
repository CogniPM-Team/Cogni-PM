import { useEffect, useState } from 'react'
import { apiUrl } from '../api/client'
import type { Step } from '../api/types'

/**
 * Follows a run's steps as the server records them (Server-Sent Events). Give the component that calls it a
 * `key` of the run id, so each run starts from an empty list. `status` stays null until the run is no longer
 * running; the stream then ends by itself. If the connection drops, the browser reconnects and the server
 * resumes after the last step it saw.
 */
export function useRunEvents(runId: string) {
  const [steps, setSteps] = useState<Step[]>([])
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    const source = new EventSource(apiUrl(`/api/runs/${runId}/events`))
    source.addEventListener('step', (event) => {
      const step = JSON.parse((event as MessageEvent<string>).data) as Step
      setSteps((previous) => (previous.some((s) => s.id === step.id) ? previous : [...previous, step]))
    })
    source.addEventListener('end', (event) => {
      setStatus((JSON.parse((event as MessageEvent<string>).data) as { status: string }).status)
      source.close()
    })
    return () => source.close()
  }, [runId])

  return { steps, status }
}
