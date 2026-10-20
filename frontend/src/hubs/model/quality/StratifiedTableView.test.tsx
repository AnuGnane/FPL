import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { StratifiedTable } from '../../../types'
import StratifiedTableView from './StratifiedTableView'

// Holiday F-155: the table cut from `QualityTab.tsx` in v19h §2.1, with
// OpenFPL's five categories as rows and an RMSE and MAE pair per column.

const TABLE = {
  zeros: { rmse: 0.9, mae: 0.4, n: 900 },
  blanks: { rmse: 1.4, mae: 0.8, n: 400 },
  tickers: { rmse: 1.6, mae: 1.2, n: 200 },
  haulers: { rmse: 5.3, mae: 4.4, n: 100 },
  all: { rmse: 2.1, mae: 1.0, n: 1600 },
} as StratifiedTable

describe('StratifiedTableView', () => {
  it('draws a row per OpenFPL category with each column’s RMSE and MAE', () => {
    render(<StratifiedTableView columns={[['All', TABLE]]} />)
    expect(screen.getByRole('columnheader', { name: 'All' }))
      .toBeInTheDocument()
    const haulers = screen.getByRole('row', { name: /Haulers/ })
    expect(within(haulers).getByText('5.3')).toBeInTheDocument()
    expect(within(haulers).getByText('4.4')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(2 + 5)
  })

  it('prints a dash for a stratum the table has no row for', () => {
    const partial = Object.fromEntries(Object.entries(TABLE)
      .filter(([key]) => key !== 'haulers')) as StratifiedTable
    render(<StratifiedTableView columns={[['Starters', partial]]} />)
    const haulers = screen.getByRole('row', { name: /Haulers/ })
    expect(within(haulers).getAllByText('—')).toHaveLength(2)
  })
})
