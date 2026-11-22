import { vi } from 'vitest'

export interface Call {
  method: string
  path: string
  body?: unknown
}

type Route = unknown | ((call: Call) => unknown | Response)

/**
 * Stubs global fetch with canned API responses, keyed "METHOD /path" (query strings are ignored). A route may
 * be a function, evaluated per request, and may return a Response to simulate an error. Returns the recorded
 * calls.
 */
export function mockApi(routes: Record<string, Route>): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = url.replace(/\?.*$/, '')
      const call: Call = { method, path, body: init?.body ? JSON.parse(init.body as string) : undefined }
      calls.push(call)

      const key = `${method} ${path}`
      if (!(key in routes)) return jsonResponse({ detail: `no mock for ${key}` }, 404)
      const route = routes[key]
      const value = typeof route === 'function' ? (route as (c: Call) => unknown)(call) : route
      return value instanceof Response ? value : jsonResponse(value)
    }),
  )
  return calls
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** A stand-in for EventSource: `FakeEventSource.last.emit('step', {...})` plays a server message. */
export class FakeEventSource {
  static last: FakeEventSource
  listeners: Record<string, ((event: MessageEvent<string>) => void)[]> = {}
  closed = false
  constructor(public url: string) {
    FakeEventSource.last = this
  }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    ;(this.listeners[type] ??= []).push(listener)
  }
  emit(type: string, data: unknown) {
    this.listeners[type]?.forEach((l) => l({ data: JSON.stringify(data) } as MessageEvent<string>))
  }
  close() {
    this.closed = true
  }
}
