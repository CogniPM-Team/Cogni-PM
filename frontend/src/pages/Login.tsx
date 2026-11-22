import { useState } from 'react'
import { api } from '../api/client'
import type { User } from '../api/types'
import Spinner from '../components/Spinner'

/** The page everyone sees first: who are you? It says one thing, in one way, when it fails, so it reveals nothing. */
export default function Login({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setProblem(null)
    try {
      onSignedIn(await api.post<User>('/api/auth/login', { email, password }))
    } catch (e) {
      setProblem((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <form
        className="login-card"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <img src="/cognipm-wordmark.png" alt="CogniPM" className="login-logo" />
        <h1>Sign in</h1>
        <label className="field">
          <span>Email</span>
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {problem && (
          <p className="error" role="alert">
            {problem}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy || !email.trim() || !password}>
          {busy && <Spinner />}
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
        <p className="fine-print">Ask a PM for an account if you do not have one.</p>
      </form>
    </main>
  )
}
