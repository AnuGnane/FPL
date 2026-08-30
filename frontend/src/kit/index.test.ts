import { describe, expect, it } from 'vitest'
import * as kit from './index'

describe('kit barrel', () => {
  it('exports every component a hub is allowed to compose', () => {
    for (const name of ['Badge', 'Card', 'DataTable', 'EmptyState',
      'PageHeader', 'PitchView', 'PosBadge', 'Sparkline', 'Stat',
      'ThresholdBar']) {
      expect(typeof (kit as Record<string, unknown>)[name]).toBe('function')
    }
  })

  it('exports the formatters and the breakpoint hook', () => {
    expect(kit.fmtNum(1.25)).toBe('1.3')
    expect(typeof kit.useIsMobile).toBe('function')
  })

  it('exports the theme controls', () => {
    expect(typeof kit.ThemeToggle).toBe('function')
    expect(typeof kit.useTheme).toBe('function')
  })
})
