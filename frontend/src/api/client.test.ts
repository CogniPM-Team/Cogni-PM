import { SIGNED_OUT } from '../lib/authEvents'
import { jsonResponse, mockApi } from '../test/mockApi'
import { api, ApiError } from './client'

describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends JSON bodies and returns the parsed reply', async () => {
    const calls = mockApi({ 'POST /api/chat': { answer: 'hi' } })

    const reply = await api.post<{ answer: string }>('/api/chat', { message: 'hello' })

    expect(reply.answer).toBe('hi')
    expect(calls[0]).toEqual({ method: 'POST', path: '/api/chat', body: { message: 'hello' } })
  })

  it('turns a plain error into a message people can read', async () => {
    mockApi({ 'POST /api/runs/r1/approve': jsonResponse({ detail: 'this run is applied; it cannot be approved again' }, 409) })

    await expect(api.post('/api/runs/r1/approve')).rejects.toMatchObject({
      status: 409,
      message: 'this run is applied; it cannot be approved again',
    })
  })

  it('keeps exactly what was and was not created when Jira failed part-way', async () => {
    const problem = {
      message: 'stopped at draft d2',
      created: [{ change_id: 'd1', issue_key: 'MCP-15', url: 'u', recovered: false }],
      not_created: ['d2'],
    }
    mockApi({ 'POST /api/runs/r1/approve': jsonResponse({ detail: problem }, 502) })

    const error = await api.post('/api/runs/r1/approve').catch((e: ApiError) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).problem?.not_created).toEqual(['d2'])
    expect((error as ApiError).message).toBe('stopped at draft d2')
  })

  it('names the field when the form is invalid, and copes with a body that is not JSON', async () => {
    mockApi({
      'PATCH /api/changes/d1': jsonResponse({ detail: [{ loc: ['body', 'summary'], msg: 'String should have at least 1 character' }] }, 422),
      'GET /api/boom': new Response('<html>bad gateway</html>', { status: 502 }),
    })

    await expect(api.patch('/api/changes/d1', {})).rejects.toThrow('Check summary: String should have at least 1 character')
    await expect(api.get('/api/boom')).rejects.toThrow('Request failed (502)')
  })
})

describe('api client and signing in', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends the sign-in cookie with every request', async () => {
    mockApi({ 'GET /api/x': { ok: true } })

    await api.get('/api/x')

    const init = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1]
    expect(init.credentials).toBe('include')
  })

  it('announces that the session has ended when any page of data comes back 401', async () => {
    mockApi({ 'GET /api/runs': jsonResponse({ detail: 'Sign in to continue.' }, 401) })
    const heard = vi.fn()
    window.addEventListener(SIGNED_OUT, heard)

    await expect(api.get('/api/runs')).rejects.toMatchObject({ status: 401 })

    expect(heard).toHaveBeenCalledTimes(1)
    window.removeEventListener(SIGNED_OUT, heard)
  })

  it('does not announce it for the sign-in itself, where 401 just means a wrong password', async () => {
    mockApi({ 'POST /api/auth/login': jsonResponse({ detail: 'Wrong email or password.' }, 401) })
    const heard = vi.fn()
    window.addEventListener(SIGNED_OUT, heard)

    await expect(api.post('/api/auth/login', {})).rejects.toMatchObject({ message: 'Wrong email or password.' })

    expect(heard).not.toHaveBeenCalled()
    window.removeEventListener(SIGNED_OUT, heard)
  })

  it('does not announce it for a 403, which is a signed-in person being refused', async () => {
    mockApi({ 'POST /api/runs': jsonResponse({ detail: 'Your account can look but not change anything. Ask a PM.' }, 403) })
    const heard = vi.fn()
    window.addEventListener(SIGNED_OUT, heard)

    await expect(api.post('/api/runs', {})).rejects.toMatchObject({ status: 403 })

    expect(heard).not.toHaveBeenCalled()
    window.removeEventListener(SIGNED_OUT, heard)
  })
})
