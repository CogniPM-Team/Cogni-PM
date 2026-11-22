import type { ApplyProblem } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

/** The URL of an API path; the event stream needs it too, because EventSource cannot go through `request`. */
export const apiUrl = (path: string) => `${BASE}${path}`

/**
 * An error response from the API. `message` is written for people. When Jira failed part-way through an
 * approval the API sends exactly what was and was not created, kept here as `problem`.
 */
export class ApiError extends Error {
  readonly status: number
  readonly problem?: ApplyProblem

  constructor(status: number, message: string, problem?: ApplyProblem) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
  }
}

function describe(detail: unknown, status: number): { message: string; problem?: ApplyProblem } {
  if (typeof detail === 'string') return { message: detail }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] }
    const field = first.loc?.slice(1).join(' ')
    return { message: `Check ${field || 'the form'}: ${first.msg ?? 'invalid value'}` }
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const problem = detail as ApplyProblem
    return { message: problem.message, problem }
  }
  return { message: `Request failed (${status})` }
}

async function request<T>(method: 'GET' | 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let payload: { detail?: unknown } | null = null
    try {
      payload = await response.json()
    } catch {
      // not JSON: keep the generic message
    }
    const { message, problem } = describe(payload?.detail, response.status)
    throw new ApiError(response.status, message, problem)
  }
  if (response.status === 204) return undefined as T // nothing to read: the delete worked
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: <T = void>(path: string) => request<T>('DELETE', path),
}
