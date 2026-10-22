import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { routerFuture } from '../../kit/router'
import { describe, expect, it } from 'vitest'
import type { WhatIfResult } from '../../types'
import PlanDiffTable from './PlanDiffTable'

// Holiday F-155: the What-If lab's original-against-yours table. A changed
// row is marked by `data-changed`, which is the whole point of the table.

const PLAN = {
  expected_pts: 60.2, horizon_pts: 250.4, hits: 0,
  buys: [{ code: 1, name: 'Wirtz' }], sells: [{ code: 2, name: 'Saka' }],
  captain: { code: 3, name: 'Salah' },
}

const DIFF = {
  baseline: PLAN,
  yours: { ...PLAN, captain: { code: 4, name: 'Haaland' } },
  delta_xpts: 0, transfers_changed: false, captain_changed: true,
  xi_in: [{ code: 4, name: 'Haaland', position: 'FWD' }],
  xi_out: [],
  verdict: 'Your plan scores the same.',
} as unknown as WhatIfResult

function rowOf(label: string | RegExp) {
  return screen.getByText(label).closest('tr')
}

describe('PlanDiffTable', () => {
  it('marks the changed captain row and leaves the unchanged rows plain', () => {
    render(<MemoryRouter {...routerFuture}><PlanDiffTable diff={DIFF} /></MemoryRouter>)
    expect(rowOf('Captain')).toHaveAttribute('data-changed', 'true')
    expect(rowOf('Hits')).toHaveAttribute('data-changed', 'false')
    expect(rowOf('Transfers in')).toHaveTextContent('Wirtz')
    expect(screen.getByText('Your plan scores the same.')).toBeInTheDocument()
  })

  it('marks transfers changed and prints a dash for an empty side', () => {
    render(<MemoryRouter {...routerFuture}><PlanDiffTable diff={{
      ...DIFF, transfers_changed: true,
      yours: { ...DIFF.yours, buys: [], sells: [] },
    } as WhatIfResult} /></MemoryRouter>)
    expect(rowOf('Transfers in')).toHaveAttribute('data-changed', 'true')
    expect(rowOf('Transfers out')).toHaveTextContent('Saka—')
  })

  it('lists the XI coming in and a dash for the side nobody leaves', () => {
    render(<MemoryRouter {...routerFuture}><PlanDiffTable diff={DIFF} /></MemoryRouter>)
    expect(screen.getByText('XI In').parentElement)
      .toHaveTextContent('Haaland')
    expect(screen.getByText('XI Out').parentElement).toHaveTextContent('—')
  })
})
