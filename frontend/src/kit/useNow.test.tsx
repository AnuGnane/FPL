/**
 * Holiday F-153 — useNow (v19a §2.1): the clock is re-read every `ms`, so a
 * countdown moves without a new payload, and the interval goes with the
 * component.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import useNow from './useNow'

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-20T12:00:00Z'))
})
afterEach(() => { vi.useRealTimers() })

describe('useNow', () => {
  it('reads the clock at mount', () => {
    const { result } = renderHook(() => useNow(60_000))
    expect(result.current.toISOString()).toBe('2026-10-20T12:00:00.000Z')
  })

  it('re-reads it on each tick and not between them', () => {
    const { result } = renderHook(() => useNow(60_000))
    act(() => { vi.advanceTimersByTime(59_000) })
    expect(result.current.toISOString()).toBe('2026-10-20T12:00:00.000Z')
    act(() => { vi.advanceTimersByTime(1_000) })
    expect(result.current.toISOString()).toBe('2026-10-20T12:01:00.000Z')
  })

  it('clears its interval on unmount', () => {
    const { unmount } = renderHook(() => useNow(60_000))
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
