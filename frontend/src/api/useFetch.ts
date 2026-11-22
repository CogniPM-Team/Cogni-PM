import { useCallback, useEffect, useState } from 'react'
import { api } from './client'

interface FetchState<T> {
  path: string | null
  data?: T
  error?: Error
}

/**
 * Loads `path` and exposes `reload`. While reloading, the previous data stays on screen. Pass `null` to skip
 * fetching.
 */
export function useFetch<T>(path: string | null) {
  const [state, setState] = useState<FetchState<T>>({ path: null })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (path === null) return
    let cancelled = false
    api
      .get<T>(path)
      .then((data) => {
        if (!cancelled) setState({ path, data })
      })
      .catch((error: Error) => {
        if (!cancelled) setState({ path, error })
      })
    return () => {
      cancelled = true
    }
  }, [path, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const current = state.path === path ? state : { path }
  return {
    data: current.data,
    error: current.error,
    loading: path !== null && current.data === undefined && current.error === undefined,
    reload,
  }
}
