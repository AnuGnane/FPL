/**
 * Holiday F-153 — useMediaQuery: absent `matchMedia` (jsdom) the answer is
 * false, the desktop layout; with it, the hook reads the query and follows
 * its `change` events. `matchMedia` is stubbed as AppShell.test.tsx does.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useIsMobile, useMediaQuery } from './useMediaQuery'

afterEach(() => { vi.unstubAllGlobals() })

function stubMatchMedia(initial: boolean) {
  const listeners = new Set<() => void>()
  const list = {
    matches: initial, media: '', onchange: null,
    addEventListener: (_: string, fn: () => void) => { listeners.add(fn) },
    removeEventListener: (_: string, fn: () => void) => { listeners.delete(fn) },
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  }
  const matchMedia = vi.fn((query: string) => { list.media = query; return list })
  vi.stubGlobal('matchMedia', matchMedia)
  return {
    matchMedia,
    listeners,
    flip(matches: boolean) {
      list.matches = matches
      listeners.forEach((fn) => fn())
    },
  }
}

describe('useMediaQuery', () => {
  it('answers false with no matchMedia, the desktop layout', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(result.current).toBe(false)
  })

  it('reads the query and follows its change events', () => {
    const media = stubMatchMedia(true)
    const { result, unmount } = renderHook(() => useMediaQuery('(x)'))
    expect(result.current).toBe(true)
    act(() => media.flip(false))
    expect(result.current).toBe(false)
    unmount()
    expect(media.listeners.size).toBe(0)
  })

  it('puts the mobile line at the md breakpoint', () => {
    const media = stubMatchMedia(false)
    renderHook(() => useIsMobile())
    expect(media.matchMedia).toHaveBeenCalledWith('(max-width: 767px)')
  })
})
