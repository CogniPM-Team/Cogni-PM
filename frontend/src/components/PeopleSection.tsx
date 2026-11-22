import { useState } from 'react'
import { api } from '../api/client'
import type { User } from '../api/types'
import { useFetch } from '../api/useFetch'
import { ROLE_NAMES, useAuth } from '../lib/auth'
import { ErrorState } from './PageParts'

const MIN_PASSWORD = 10

/** Settings, for a PM: who can sign in, and as what. A PM can approve; a developer can only look. */
export default function PeopleSection() {
  const { user: me } = useAuth()
  const people = useFetch<User[]>('/api/users')
  const [problem, setProblem] = useState<string | null>(null)
  const [resetting, setResetting] = useState<string | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [form, setForm] = useState({ display_name: '', email: '', role: 'developer', password: '' })

  async function run(work: () => Promise<unknown>) {
    setProblem(null)
    try {
      await work()
      people.reload()
    } catch (e) {
      setProblem((e as Error).message)
    }
  }

  const change = (id: string, body: Partial<Pick<User, 'role' | 'display_name' | 'disabled'>> & { password?: string }) =>
    run(async () => {
      await api.patch(`/api/users/${id}`, body)
      setResetting(null)
      setNewPassword('')
    })

  return (
    <section className="card settings-section" aria-labelledby="set-people">
      <h2 id="set-people">People</h2>
      <p className="meta">A PM can start tasks, approve and change settings. A developer can look at everything and change nothing.</p>

      {people.error && <ErrorState title="Could not load the people" message={people.error.message} onRetry={people.reload} />}
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}

      <ul className="people">
        {people.data?.map((person) => {
          const you = person.id === me?.id
          return (
            <li key={person.id} className={person.disabled ? 'off' : undefined}>
              <div className="person">
                <strong>
                  {person.display_name}
                  {you && <span className="tag"> You</span>}
                  {person.disabled && <span className="tag"> Disabled</span>}
                </strong>
                <span className="meta">{person.email}</span>
              </div>
              <label className="role-pick">
                <span className="sr-only">Role of {person.display_name}</span>
                <select
                  value={person.role}
                  disabled={you}
                  title={you ? 'Ask another PM to change your own role' : undefined}
                  onChange={(e) => void change(person.id, { role: e.target.value as User['role'] })}
                >
                  {Object.entries(ROLE_NAMES).map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="person-actions">
                <button type="button" className="link" onClick={() => setResetting(resetting === person.id ? null : person.id)}>
                  New password
                </button>
                {!you && (
                  <button type="button" className={person.disabled ? 'link' : 'link danger'} onClick={() => void change(person.id, { disabled: !person.disabled })}>
                    {person.disabled ? 'Enable' : 'Disable'}
                  </button>
                )}
              </div>
              {resetting === person.id && (
                <form
                  className="inline-form reset"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void change(person.id, { password: newPassword })
                  }}
                >
                  <input
                    type="password"
                    aria-label={`New password for ${person.display_name}`}
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder={`At least ${MIN_PASSWORD} characters`}
                  />
                  <button type="submit" className="small primary" disabled={newPassword.length < MIN_PASSWORD}>
                    Set password
                  </button>
                  <span className="meta">They are signed out everywhere.</span>
                </form>
              )}
            </li>
          )
        })}
      </ul>

      <h3>Add a person</h3>
      <form
        className="person-form"
        onSubmit={(event) => {
          event.preventDefault()
          void run(async () => {
            await api.post('/api/users', form)
            setForm({ display_name: '', email: '', role: 'developer', password: '' })
          })
        }}
      >
        <label className="field">
          <span>Name</span>
          <input type="text" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        </label>
        <label className="field">
          <span>Email</span>
          <input type="email" autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label className="field">
          <span>Role</span>
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {Object.entries(ROLE_NAMES).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={`At least ${MIN_PASSWORD} characters`} />
        </label>
        <button type="submit" disabled={!form.display_name.trim() || !form.email.trim() || form.password.length < MIN_PASSWORD}>
          Add person
        </button>
      </form>
    </section>
  )
}
