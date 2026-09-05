import { describe, expect, it } from 'vitest'
import { TR_CLASS, TR_SELECTED_CLASS, tdClass, thClass } from './table'

describe('the one table style', () => {
  it('right-aligns and tabularises numeric cells only', () => {
    expect(tdClass(true)).toContain('tn')
    expect(tdClass(true)).toContain('text-right')
    expect(tdClass()).not.toContain('tn')
    expect(thClass(true)).toContain('text-right')
    expect(thClass()).toContain('text-left')
  })

  it('is 32px rows on hairlines, raised on hover, accent-tinted when selected', () => {
    expect(thClass()).toContain('h-8')
    expect(tdClass()).toContain('h-8')
    expect(TR_CLASS).toContain('border-divider')
    expect(TR_CLASS).toContain('hover:bg-raised')
    expect(TR_SELECTED_CLASS).toBe('bg-accent-tint')
  })
})
