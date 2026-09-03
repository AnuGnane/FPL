/**
 * v12 W5 §6.1 — `?tab=` is the open tab.
 *
 * The unknown-tab case is the one that matters: a Radix root whose value
 * matches no `Tabs.Content` renders a blank hub with no error, so a link
 * carrying another hub's tab name has to land on the default instead.
 */
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation, useNavigationType } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { useTabParam } from './useTabParam'

const TABS = ['quality', 'journal', 'health'] as const

function wrapper(initial: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  )
}

describe('useTabParam', () => {
  it('opens the default when the parameter is absent', () => {
    const { result } = renderHook(() => useTabParam(TABS, 'quality'),
      { wrapper: wrapper('/model') })
    expect(result.current[0]).toBe('quality')
  })

  it('opens the tab the link names', () => {
    const { result } = renderHook(() => useTabParam(TABS, 'quality'),
      { wrapper: wrapper('/model?tab=health') })
    expect(result.current[0]).toBe('health')
  })

  it('falls back to the default for a tab this hub does not have', () => {
    const { result } = renderHook(() => useTabParam(TABS, 'quality'),
      { wrapper: wrapper('/model?tab=board') })
    expect(result.current[0]).toBe('quality')
  })

  it('writes the new tab into the query string', () => {
    const { result } = renderHook(
      () => [useTabParam(TABS, 'quality'), useLocation()] as const,
      { wrapper: wrapper('/model') })
    act(() => { result.current[0][1]('journal') })
    expect(result.current[0][0]).toBe('journal')
    expect(result.current[1].search).toBe('?tab=journal')
  })

  it('keeps every other query parameter', () => {
    const { result } = renderHook(
      () => [useTabParam(TABS, 'quality'), useLocation()] as const,
      { wrapper: wrapper('/model?gw=7') })
    act(() => { result.current[0][1]('journal') })
    expect(result.current[1].search).toContain('gw=7')
    expect(result.current[1].search).toContain('tab=journal')
  })

  it('replaces rather than pushes, so a tab strip is not a history trail', () => {
    const { result } = renderHook(
      () => [useTabParam(TABS, 'quality'), useLocation(),
             useNavigationType()] as const,
      { wrapper: wrapper('/model') })
    expect(result.current[2]).toBe('POP')
    act(() => { result.current[0][1]('journal') })
    act(() => { result.current[0][1]('health') })
    // The claim is about the *history*, not just the URL: six clicks through a
    // strip must be one entry, so the back button leaves the hub rather than
    // walking backwards through the tabs. `replace: false` would make this
    // 'PUSH' while leaving the search string below exactly as it is, which is
    // why the search assertion alone was not enough.
    expect(result.current[2]).toBe('REPLACE')
    expect(result.current[1].search).toBe('?tab=health')
  })
})
