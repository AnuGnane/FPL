import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet, apiPost, errorText } from './client'

afterEach(() => vi.unstubAllGlobals())

function stub(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })),
  )
}

describe('api client', () => {
  it('returns parsed JSON on success', async () => {
    stub(200, { gw: 3 })
    await expect(apiGet<{ gw: number }>('/api/advice/latest'))
      .resolves.toEqual({ gw: 3 })
  })

  it('throws ApiError carrying the status and the detail', async () => {
    stub(422, { detail: 'run `gaffer advise` first' })
    await expect(apiGet('/api/advice/latest')).rejects.toBeInstanceOf(ApiError)
    stub(422, { detail: { constraint: 'lock_and_ban', players: [5] } })
    const error = await apiPost('/api/whatif', { lock: [5], ban: [5] })
      .catch((e: ApiError) => e)
    expect((error as ApiError).status).toBe(422)
    expect((error as ApiError).detail).toEqual({
      constraint: 'lock_and_ban',
      players: [5],
    })
  })

  it('unwraps the structured detail into a sentence', () => {
    // The shape every write endpoint refuses in: {constraint, error,
    // players}. Rendering the whole object is how "[object Object]" gets on
    // the page.
    expect(errorText(new ApiError(422, {
      constraint: 'override_value',
      error: 'p_play must be between 0 and 1',
      players: [100],
    }))).toBe('p_play must be between 0 and 1')
  })

  it('falls back through a plain-string detail to the message', () => {
    expect(errorText(new ApiError(422, 'run `gaffer advise` first')))
      .toBe('run `gaffer advise` first')
    expect(errorText(new Error('the server is down')))
      .toBe('the server is down')
    expect(errorText('nope')).toBe('nope')
  })

  it('posts JSON bodies', async () => {
    stub(202, { job_id: 'abc' })
    await apiPost('/api/whatif', { lock: [1] })
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ lock: [1] })
  })
})
