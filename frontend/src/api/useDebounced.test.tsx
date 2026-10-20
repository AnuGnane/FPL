/**
 * Holiday F-153 — useDebounced: the value settles only once it has stopped
 * changing for `delay`, so a five-letter name is one request, not five.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useDebounced } from './useDebounced'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('useDebounced', () => {
  it('starts settled on the first value', () => {
    const { result } = renderHook(() => useDebounced('sa'))
    expect(result.current).toBe('sa')
  })

  it('settles on the last value once typing stops for the delay', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounced(value, 250), { initialProps: { value: 's' } })
    rerender({ value: 'sa' })
    act(() => { vi.advanceTimersByTime(200) })
    rerender({ value: 'sal' })
    act(() => { vi.advanceTimersByTime(200) })
    expect(result.current).toBe('s')
    act(() => { vi.advanceTimersByTime(50) })
    expect(result.current).toBe('sal')
  })

  it('waits 250ms by default', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounced(value), { initialProps: { value: 'a' } })
    rerender({ value: 'ab' })
    act(() => { vi.advanceTimersByTime(249) })
    expect(result.current).toBe('a')
    act(() => { vi.advanceTimersByTime(1) })
    expect(result.current).toBe('ab')
  })
})
