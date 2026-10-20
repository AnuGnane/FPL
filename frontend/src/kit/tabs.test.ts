/**
 * Holiday F-153 — the Radix tab strip classes (spec §5): the strip scrolls
 * rather than wraps at 390px, and the active trigger is in text colour over
 * a 2px accent underline.
 */
import { describe, expect, it } from 'vitest'
import { TAB_CLASS, TAB_LIST_CLASS } from './tabs'

describe('tabs', () => {
  it('scrolls the strip sideways and keeps each trigger on one line', () => {
    expect(TAB_LIST_CLASS.split(/\s+/)).toContain('overflow-x-auto')
    expect(TAB_CLASS.split(/\s+/)).toEqual(
      expect.arrayContaining(['shrink-0', 'whitespace-nowrap']))
  })

  it('marks the active trigger with the accent underline in text colour', () => {
    expect(TAB_CLASS.split(/\s+/)).toEqual(expect.arrayContaining([
      'border-b-2', 'text-text-muted',
      'data-[state=active]:border-accent', 'data-[state=active]:text-text',
    ]))
  })
})
