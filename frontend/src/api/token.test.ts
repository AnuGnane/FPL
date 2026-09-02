import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TOKEN_KEY, apiGet, apiPost, readToken } from './client'

// v12 W1 §2.8. `gaffer ui --lan` prints a token and a `?token=` URL to scan off
// a QR code. The page has to survive three states a phone actually reaches: the
// first load with the parameter, every load after it without, and a browser
// that refuses site data entirely — where the honest degradation is "this tab
// works, the next one will not", never an exception on every request.

function visit(search: string) {
  Object.defineProperty(window, 'location', {
    value: { ...window.location, search },
    writable: true,
  })
}

beforeEach(() => {
  localStorage.clear()
  visit('')
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({}),
  })))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('readToken', () => {
  it('stores the parameter on first load', () => {
    visit('?token=abc123')
    expect(readToken()).toBe('abc123')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('abc123')
  })

  it('reads storage on a later load with no parameter', () => {
    localStorage.setItem(TOKEN_KEY, 'abc123')
    expect(readToken()).toBe('abc123')
  })

  it('is empty when there is neither', () => {
    expect(readToken()).toBe('')
  })

  it('still returns the URL token when storage throws', () => {
    // Safari in a private window, and a browser set to block site data.
    // The tab must keep working; only the next one loses the token.
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => { throw new Error('denied') })
    visit('?token=abc123')
    expect(readToken()).toBe('abc123')
    setItem.mockRestore()
  })
})

describe('the header', () => {
  it('is absent when there is no token', async () => {
    await apiGet('/api/ping')
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(init?.headers?.['X-Gaffer-Token']).toBeUndefined()
  })

  it('rides on a GET as well as a POST', async () => {
    localStorage.setItem(TOKEN_KEY, 'abc123')
    await apiGet('/api/ping')
    await apiPost('/api/watchlist', { code: 1 })
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
    expect(calls[0][1].headers['X-Gaffer-Token']).toBe('abc123')
    expect(calls[1][1].headers['X-Gaffer-Token']).toBe('abc123')
    // and the POST keeps the content type it always had
    expect(calls[1][1].headers['Content-Type']).toBe('application/json')
  })
})
