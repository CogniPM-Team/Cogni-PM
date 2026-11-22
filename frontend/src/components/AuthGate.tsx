import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { User } from '../api/types'
import { type Auth, AuthContext } from '../lib/auth'
import { SIGNED_OUT } from '../lib/authEvents'
import Login from '../pages/Login'

type State = { status: 'loading' } | { status: 'out' } | { status: 'error'; message: string } | { status: 'in'; user: User }

/**
 * Everything inside needs a signed-in person. It asks the server who that is, shows the sign-in page if nobody is, and
 * goes back to it when the server later says the session is over.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .get<User>('/api/auth/me')
      .then((user) => !cancelled && setState({ status: 'in', user }))
      .catch((e: Error) => {
        if (cancelled) return
        // 401 just means nobody is signed in; anything else means the server could not be asked.
        setState(e instanceof ApiError && e.status === 401 ? { status: 'out' } : { status: 'error', message: e.message })
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  useEffect(() => {
    const out = () => setState({ status: 'out' })
    window.addEventListener(SIGNED_OUT, out)
    return () => window.removeEventListener(SIGNED_OUT, out)
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.post('/api/auth/logout')
    } catch {
      // The server could not be told. This page is signed out anyway, and the session ends on its own.
    }
    setState({ status: 'out' })
  }, [])

  const auth = useMemo<Auth | null>(
    () => (state.status === 'in' ? { user: state.user, canChange: state.user.role === 'pm', signOut } : null),
    [state, signOut],
  )

  if (state.status === 'loading') return <p className="auth-wait muted">Loading...</p>
  if (state.status === 'error') {
    return (
      <main className="login">
        <div className="login-card" role="alert">
          <h1>Could not reach the server</h1>
          <p className="muted">{state.message}</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      </main>
    )
  }
  if (state.status === 'out') return <Login onSignedIn={(user) => setState({ status: 'in', user })} />
  return <AuthContext.Provider value={auth!}>{children}</AuthContext.Provider>
}
