import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import League from './League'
import Model from './Model'
import Planning from './Planning'
import Players from './Players'
import ThisWeek from './ThisWeek'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

function phone() {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: true, media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

beforeEach(() => {
  apiGet.mockReset()
  // Every hub must survive a total absence of artifacts on a phone: the
  // cold-clone-on-mobile case, which is the one that used to crash.
  apiGet.mockRejectedValue(Object.assign(
    new Error('no advice on disk yet — run `gaffer advise` first'),
    { status: 422 }))
  phone()
})

afterEach(() => { vi.unstubAllGlobals() })

describe('hubs on a phone', () => {
  const hubs: Array<[string, () => JSX.Element]> = [
    ['This Week', ThisWeek],
    ['Planning', Planning],
    ['Players', Players],
    ['League', League],
    ['Model', Model],
  ]

  for (const [name, Hub] of hubs) {
    it(`${name} renders an empty state and no console error`, async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<MemoryRouter><Hub /></MemoryRouter>)
      expect(await screen.findByRole('heading', { level: 1 }))
        .toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
  }
})
