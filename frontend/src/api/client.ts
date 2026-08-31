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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
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
