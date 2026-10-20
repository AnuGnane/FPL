/**
 * Holiday F-153 — useOpener (v18f §2.2): the element holding focus when the
 * dialog mounts is the one the close handler hands focus back to, and the
 * handler prevents Radix's own return to a trigger that is not there.
 */
import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import useOpener from './useOpener'

afterEach(() => { document.body.innerHTML = '' })

describe('useOpener', () => {
  it('hands focus back to the element focused at mount', () => {
    const opener = document.createElement('button')
    const elsewhere = document.createElement('button')
    document.body.append(opener, elsewhere)
    opener.focus()
    const { result } = renderHook(() => useOpener())
    elsewhere.focus()
    result.current(new Event('focusout', { cancelable: true }))
    expect(document.activeElement).toBe(opener)
  })

  it('prevents the default return to a trigger', () => {
    const { result } = renderHook(() => useOpener())
    const event = new Event('focusout', { cancelable: true })
    result.current(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('remembers the opener from mount, not from a later render', () => {
    const opener = document.createElement('button')
    const later = document.createElement('button')
    document.body.append(opener, later)
    opener.focus()
    const { result, rerender } = renderHook(() => useOpener())
    later.focus()
    rerender()
    later.blur()
    result.current(new Event('focusout', { cancelable: true }))
    expect(document.activeElement).toBe(opener)
  })
})
