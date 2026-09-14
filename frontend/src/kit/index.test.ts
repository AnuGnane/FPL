import { describe, expect, it } from 'vitest'
import * as kit from './index'

describe('kit barrel', () => {
  it('exports every component a hub is allowed to compose', () => {
    // `Badge` was the v14 alias of `Chip` and is gone in v18f §2.2: no file
    // in the tree composed it, and a name nothing writes is a second
    // vocabulary for the same thing.
    for (const name of ['Card', 'DataTable', 'EmptyState',
      'PageHeader', 'PitchView', 'PlayerCard', 'PosBadge', 'Skeleton',
      'Sparkline', 'Stat', 'Th', 'ThresholdBar', 'ToastOutlet',
      'Button', 'Segmented', 'Chip', 'Bar', 'Callout', 'StatRow', 'Section',
      'ErrorBoundary', 'Loaded']) {
      expect(typeof (kit as Record<string, unknown>)[name]).toBe('function')
    }
  })

  it('exports the shared class strings and the chart palette', () => {
    expect(kit.TAB_CLASS).toContain('data-[state=active]:border-accent')
    expect(kit.INPUT_CLASS).toContain('bg-input')
    expect(kit.SERIES_COLOURS).toHaveLength(4)
    expect(kit.thClass(true)).toContain('text-right')
  })

  it('exports the formatters and the breakpoint hook', () => {
    expect(kit.fmtNum(1.25)).toBe('1.3')
    expect(typeof kit.useIsMobile).toBe('function')
  })

  it('exports the toast raiser, so a hub never imports the module directly', () => {
    expect(typeof kit.toast).toBe('function')
    expect(kit.MAX_TOASTS).toBe(3)
  })

  it('exports the theme controls', () => {
    expect(typeof kit.ThemeToggle).toBe('function')
    expect(typeof kit.useTheme).toBe('function')
  })
})
