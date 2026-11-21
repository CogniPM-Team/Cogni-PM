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
