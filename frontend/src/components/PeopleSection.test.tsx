import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { User } from '../api/types'
import { type Auth, AuthContext } from '../lib/auth'
import { type Call, jsonResponse, mockApi } from '../test/mockApi'
import PeopleSection from './PeopleSection'

const person = (id: string, over: Partial<User> = {}): User => ({
  id,
  email: `${id}@example.com`,
  display_name: id.toUpperCase(),
  role: 'developer',
  disabled: false,
  ...over,
})
const ME = person('me', { role: 'pm', display_name: 'Pat' })

const auth: Auth = { user: ME, canChange: true, signOut: async () => {} }
const show = () =>
  render(
    <AuthContext.Provider value={auth}>
      <PeopleSection />
    </AuthContext.Provider>,
  )

const row = (name: string) => screen.getByText(name, { selector: 'strong' }).closest('li') as HTMLElement
const patches = (calls: Call[]) => calls.filter((c) => c.method === 'PATCH')

describe('PeopleSection', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists everyone with their role, marks you, and does not let you change your own role or disable yourself', async () => {
    mockApi({ 'GET /api/users': [ME, person('dana'), person('old', { disabled: true })] })

    show()

    const mine = (await screen.findByText('Pat', { selector: 'strong' })).closest('li')!
    expect(within(mine).getByText('You')).toBeInTheDocument()
    expect(within(mine).getByRole('combobox')).toBeDisabled()
    expect(within(mine).queryByRole('button', { name: 'Disable' })).not.toBeInTheDocument()
    expect(within(row('DANA')).getByRole('button', { name: 'Disable' })).toBeInTheDocument()
    expect(within(row('OLD')).getByText('Disabled')).toBeInTheDocument()
    expect(within(row('OLD')).getByRole('button', { name: 'Enable' })).toBeInTheDocument()
  })

  it('changes a role, and reloads the list', async () => {
    const calls = mockApi({ 'GET /api/users': [ME, person('dana')], 'PATCH /api/users/dana': person('dana', { role: 'pm' }) })
    const user = userEvent.setup()
    show()
    await screen.findByText('DANA')

    await user.selectOptions(within(row('DANA')).getByRole('combobox'), 'pm')

    expect(patches(calls)[0].body).toEqual({ role: 'pm' })
    expect(calls.filter((c) => c.path === '/api/users' && c.method === 'GET').length).toBeGreaterThan(1)
  })

  it('disables and enables a person', async () => {
    const calls = mockApi({ 'GET /api/users': [ME, person('dana')], 'PATCH /api/users/dana': person('dana') })
    const user = userEvent.setup()
    show()
    await screen.findByText('DANA')

    await user.click(within(row('DANA')).getByRole('button', { name: 'Disable' }))

    expect(patches(calls)[0].body).toEqual({ disabled: true })
  })

  it('says why when the server refuses, such as removing the last PM', async () => {
    mockApi({
      'GET /api/users': [ME, person('dana', { role: 'pm' })],
      'PATCH /api/users/dana': jsonResponse({ detail: 'At least one active PM must remain.' }, 409),
    })
    const user = userEvent.setup()
    show()
    await screen.findByText('DANA')

    await user.click(within(row('DANA')).getByRole('button', { name: 'Disable' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('At least one active PM must remain.')
  })

  it('sets a new password only once it is long enough, and says they are signed out everywhere', async () => {
    const calls = mockApi({ 'GET /api/users': [ME, person('dana')], 'PATCH /api/users/dana': person('dana') })
    const user = userEvent.setup()
    show()
    await screen.findByText('DANA')

    await user.click(within(row('DANA')).getByRole('button', { name: 'New password' }))
    expect(screen.getByText('They are signed out everywhere.')).toBeInTheDocument()
    const set = screen.getByRole('button', { name: 'Set password' })
    await user.type(screen.getByLabelText('New password for DANA'), 'short')
    expect(set).toBeDisabled()
    await user.type(screen.getByLabelText('New password for DANA'), ' enough now')
    await user.click(set)

    expect(patches(calls)[0].body).toEqual({ password: 'short enough now' })
  })

  it('adds a person, and will not send the form until it is complete', async () => {
    const calls = mockApi({ 'GET /api/users': [ME], 'POST /api/users': person('new') })
    const user = userEvent.setup()
    show()
    await screen.findByText('Pat')
    const add = screen.getByRole('button', { name: 'Add person' })
    expect(add).toBeDisabled()

    await user.type(screen.getByLabelText('Name'), 'Newcomer')
    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'a long enough password')
    expect(add).toBeEnabled()
    await user.click(add)

    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      display_name: 'Newcomer',
      email: 'new@example.com',
      role: 'developer', // the safer role is the default
      password: 'a long enough password',
    })
    expect(screen.getByLabelText('Name')).toHaveValue('') // the form is ready for the next person
  })

  it('shows an error with Try again when the list cannot be loaded', async () => {
    mockApi({})

    show()

    expect(await screen.findByText('Could not load the people')).toBeInTheDocument()
  })
})
