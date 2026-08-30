import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEMES, THEME_KEY, applyTheme, readTheme, useTheme } from './useTheme'

function hostileStorage() {
  vi.stubGlobal('localStorage', {
    getItem() { throw new Error('storage denied') },
    setItem() { throw new Error('storage denied') },
  })
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => { vi.unstubAllGlobals() })

describe('useTheme', () => {
  it('offers the three states in a stable order', () => {
    expect(THEMES).toEqual(['system', 'dark', 'light'])
  })

  it('defaults to following the system', () => {
    expect(readTheme()).toBe('system')
  })

  it('reads a stored choice', () => {
    localStorage.setItem(THEME_KEY, 'light')
    expect(readTheme()).toBe('light')
  })

  it('ignores a stored value that is not a theme', () => {
    localStorage.setItem(THEME_KEY, 'neon')
    expect(readTheme()).toBe('system')
  })

  // Safari's private mode throws on both ends of localStorage. A theme
  // preference is not worth a white screen.
  it('follows the system when storage refuses to be read', () => {
    hostileStorage()
    expect(readTheme()).toBe('system')
  })

  it('stamps an explicit choice on the document element', () => {
    applyTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('removes the attribute for system, which is its whole meaning', () => {
    applyTheme('dark')
    applyTheme('system')
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })

  it('persists and applies what the hook is given', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current[0]).toBe('system')
    act(() => { result.current[1]('dark') })
    expect(result.current[0]).toBe('dark')
    expect(localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('still switches when storage refuses the write', () => {
    hostileStorage()
    const { result } = renderHook(() => useTheme())
    act(() => { result.current[1]('light') })
    expect(result.current[0]).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
