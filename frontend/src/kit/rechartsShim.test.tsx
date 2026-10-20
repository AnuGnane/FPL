import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Bar, BarChart, ResponsiveContainer } from 'recharts'
import { CHART_BOX } from './rechartsShim'

vi.mock('recharts', () => import('./rechartsShim').then((m) => m.mockRecharts({ height: 240 })))

describe('the recharts shim (holiday F-161)', () => {
  it('draws the container as a fixed box, a height passed in over the default', () => {
    const { container } = render(
      <ResponsiveContainer><BarChart data={[]} /></ResponsiveContainer>)
    const box = container.firstElementChild as HTMLElement
    expect(box.style.width).toBe(`${CHART_BOX.width}px`)
    expect(box.style.height).toBe('240px')
  })

  it('hands the chart the box, so a chart child renders under jsdom', () => {
    const { container } = render(
      <ResponsiveContainer>
        <BarChart data={[{ v: 1 }, { v: 2 }]}><Bar dataKey="v" /></BarChart>
      </ResponsiveContainer>)
    const svg = container.querySelector('svg.recharts-surface')
    expect(svg?.getAttribute('width')).toBe(`${CHART_BOX.width}`)
    expect(svg?.getAttribute('height')).toBe('240')
  })
})
