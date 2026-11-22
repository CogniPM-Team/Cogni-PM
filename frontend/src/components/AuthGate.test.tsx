import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { notifySignedOut } from '../lib/authEvents'
import { useAuth } from '../lib/auth'
import { jsonResponse, mockApi } from '../test/mockApi'
import AuthGate from './AuthGate'

const PM = { id: 'u1', email: 'pat@example.com', display_name: 'Pat PM', role: 'pm', disabled: false }

function Inside() {
  const { user, canChange, signOut } = useAuth()
  return (
    <>
      <p>
        Hello {user?.display_name}, {canChange ? 'can change' : 'view only'}
      </p>
      <button onClick={() => void signOut()}>out</button>
    </>
  )
}

const show = () =>
  render(
    <AuthGate>
      <Inside />
    </AuthGate>,
  )

describe('AuthGate', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the app to someone who is signed in, and tells it who they are', async () => {
    mockApi({ 'GET /api/auth/me': PM })

    show()

    expect(await screen.findByText('Hello Pat PM, can change')).toBeInTheDocument()
  })

  it('treats a developer as view-only', async () => {
    mockApi({ 'GET /api/auth/me': { ...PM, role: 'developer' } })

    show()

    expect(await screen.findByText('Hello Pat PM, view only')).toBeInTheDocument()
  })

  it('shows the sign-in page, and not the app, when nobody is signed in', async () => {
    mockApi({ 'GET /api/auth/me': jsonResponse({ detail: 'Sign in to continue.' }, 401) })

    show()

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByText(/Hello/)).not.toBeInTheDocument()
  })

  it('says the server could not be reached, instead of showing a sign-in page that cannot work', async () => {
    mockApi({ 'GET /api/auth/me': jsonResponse({ detail: 'boom' }, 500) })

    show()

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('goes to the app after a good sign-in', async () => {
    mockApi({ 'GET /api/auth/me': jsonResponse({ detail: 'x' }, 401), 'POST /api/auth/login': PM })
    const user = userEvent.setup()
    show()

    await user.type(await screen.findByLabelText('Email'), 'pat@example.com')
    await user.type(screen.getByLabelText('Password'), 'a long enough password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Hello Pat PM, can change')).toBeInTheDocument()
  })

  it('says the same plain thing for a wrong password, and stays on the sign-in page', async () => {
    const calls = mockApi({
      'GET /api/auth/me': jsonResponse({ detail: 'x' }, 401),
      'POST /api/auth/login': jsonResponse({ detail: 'Wrong email or password.' }, 401),
    })
    const user = userEvent.setup()
    show()

    await user.type(await screen.findByLabelText('Email'), 'pat@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password.')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled() // can try again
    expect(calls.filter((c) => c.path === '/api/auth/login')[0].body).toEqual({ email: 'pat@example.com', password: 'wrong' })
  })

  it('will not send a sign-in with nothing typed', async () => {
    mockApi({ 'GET /api/auth/me': jsonResponse({ detail: 'x' }, 401) })
    show()

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeDisabled()
  })

  it('signs out, even if the server is unreachable, and shows the sign-in page again', async () => {
    mockApi({ 'GET /api/auth/me': PM, 'POST /api/auth/logout': jsonResponse({ detail: 'down' }, 500) })
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: 'out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('returns to the sign-in page when the server says the session has ended', async () => {
    mockApi({ 'GET /api/auth/me': PM })
    show()
    await screen.findByText('Hello Pat PM, can change')

    notifySignedOut()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument())
  })
})
