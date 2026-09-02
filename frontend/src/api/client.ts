// Every response the server sends is JSON, including its errors: the SPA
// fallback deliberately refuses /api paths so a typo can never come back as
// the HTML shell (see src/gaffer/web/app.py).
export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

/**
 * The sentence to show a user for anything a request threw.
 *
 * Every write endpoint refuses in the what-if lab's shape —
 * `{constraint, error, players}` — so the readable half is `detail.error` and
 * rendering the object itself is how `[object Object]` reaches the page. Kept
 * here rather than in each caller because three of them were unwrapping it
 * differently, and the fourth was not unwrapping it at all.
 */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = e.detail
    if (detail && typeof detail === 'object' && 'error' in detail) {
      return String((detail as { error: unknown }).error)
    }
    if (typeof detail === 'string') return detail
  }
  return e instanceof Error ? e.message : String(e)
}

export const TOKEN_KEY = 'gaffer-token'

/**
 * The LAN write token, from `?token=` on first load or from storage after.
 *
 * `useTheme`'s idiom, try/catch included: a browser refusing site data must
 * degrade to "this tab works, the next one will not" rather than throwing on
 * every request. The parameter is consumed into storage and left in the URL —
 * stripping it would mean touching history from a module that has no business
 * doing so, and the URL is one the user typed off a QR code on their own phone.
 *
 * One consequence, accepted rather than overlooked: the `?token=` arrives in
 * the query string, so uvicorn's access log records it once, on the first
 * request of the first load. That log is a terminal on the user's own machine
 * — the same terminal that just printed the token in the LAN banner.
 */
export function readToken(): string {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('token')
    if (fromUrl) {
      localStorage.setItem(TOKEN_KEY, fromUrl)
      return fromUrl
    }
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    try {
      return new URLSearchParams(window.location.search).get('token') ?? ''
    } catch {
      return ''
    }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // On every request, GETs included. Simpler than branching on the method,
  // harmless on loopback where nothing reads it, and a read route that
  // becomes protected later needs no change here.
  const token = readToken()
  const headers = token
    ? { ...(init?.headers ?? {}), 'X-Gaffer-Token': token }
    : init?.headers
  const response = await fetch(path, { ...init, headers })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, body?.detail ?? body)
  }
  return body as T
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}
