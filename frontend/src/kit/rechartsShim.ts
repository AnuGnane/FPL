/**
 * Holiday F-161 — the one `vi.mock('recharts', …)` factory the hub tests share.
 *
 * jsdom measures every box as 0×0, so the real `ResponsiveContainer` never
 * hands its chart a size and the chart draws nothing. The stub is a fixed box
 * that clones its chart with the same width and height, which is what the
 * real container does once it has measured. Seventeen test files carried
 * this block by hand until F-161; a test that needs a taller box passes its
 * height (the Live hub's 220, the radar's 300) rather than its own copy.
 *
 *     vi.mock('recharts', () => import('../kit/rechartsShim').then((m) => m.mockRecharts()))
 *
 * `vi.mock` is hoisted above every import, so the factory imports the shim
 * itself: a factory naming an imported `mockRecharts` would run before the
 * binding exists.
 */
import { cloneElement, createElement, isValidElement } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { vi } from 'vitest'

/** The box a stubbed `ResponsiveContainer` draws its chart into. */
export const CHART_BOX = { width: 400, height: 200 }

export async function mockRecharts(box: Partial<typeof CHART_BOX> = {}) {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const size = { ...CHART_BOX, ...box }
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => createElement(
      'div', { style: size },
      isValidElement(children)
        ? cloneElement(children as ReactElement<Record<string, unknown>>, size)
        : children,
    ),
  }
}
