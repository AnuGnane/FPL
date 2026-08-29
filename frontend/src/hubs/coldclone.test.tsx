/**
 * Smoke 3, the scriptable half (spec §9, plan Task 43).
 *
 * A clone with no `reports/`, `data/` or `models/`: every request fails the
 * way the backend fails on a cold tree, and every one of the six hubs must
 * answer with an EmptyState naming its action rather than a blank screen or a
 * console error.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import League from './League'
import Live from './Live'
import Model from './Model'
import Planning from './Planning'
import Players from './Players'
import ThisWeek from './ThisWeek'

const { apiGet, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  // The real client throws this, and hubs branch on `instanceof` + status to
  // tell "nothing built yet" from "something broke". The cold clone must be
  // rejected with the same shape or the branch under test never runs.
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockRejectedValue(
    new ApiError('no advice on disk yet — run `gaffer advise` first'))
})

afterEach(() => { vi.unstubAllGlobals() })

describe('a cold clone', () => {
  const hubs: Array<[string, () => JSX.Element]> = [
    ['This Week', ThisWeek],
    ['Planning', Planning],
    ['Players', Players],
    ['League', League],
    ['Live', Live],
    ['Model', Model],
  ]

  for (const [name, Hub] of hubs) {
    it(`${name} shows an EmptyState with no console error`, async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<MemoryRouter><Hub /></MemoryRouter>)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
  }
})
