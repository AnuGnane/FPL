import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import StackedRows, { type StackedRow } from './StackedRows'

const ROWS: StackedRow[] = [
  { key: 1, title: 'Salah', lead: <span>IN</span>,
    pairs: [{ label: 'xPts', value: '6.4', numeric: true },
            { label: 'Sims', value: '82%' }] },
  { key: 2, title: 'Isak',
    pairs: [{ label: 'xPts', value: '3.2', numeric: true }] },
]

describe('StackedRows (v19c §2.1)', () => {
  it('renders every row with its title and its label and value pairs', () => {
    render(<StackedRows rows={ROWS} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    const first = screen.getByTestId('stacked-row-1')
    expect(within(first).getByText('Salah')).toBeInTheDocument()
    expect(within(first).getByText('xPts')).toBeInTheDocument()
    expect(within(first).getByText('6.4')).toBeInTheDocument()
    expect(within(first).getByText('Sims')).toBeInTheDocument()
    expect(within(first).getByText('82%')).toBeInTheDocument()
    expect(within(first).getByText('IN')).toBeInTheDocument()
  })

  it('gives a numeric value the tabular figures a column would have', () => {
    render(<StackedRows rows={ROWS} />)
    expect(screen.getByText('6.4').className).toMatch(/\btn\b/)
    expect(screen.getByText('82%').className).not.toMatch(/\btn\b/)
  })

  it('rules between the rows and never under the last one', () => {
    render(<StackedRows rows={ROWS} />)
    expect(screen.getByTestId('stacked-row-1').className)
      .toMatch(/border-b border-divider/)
    expect(screen.getByTestId('stacked-row-2').className)
      .not.toMatch(/border-b/)
  })

  it('draws no disclosure for a row that has no detail', () => {
    render(<StackedRows rows={ROWS} />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('fires onToggle and follows the open the caller owns', async () => {
    const onToggle = vi.fn()
    const row: StackedRow = {
      key: 'hits1', title: '1 hit', pairs: [],
      detail: <p>what the last hit bought</p>, open: false, onToggle,
    }
    const { rerender } = render(<StackedRows rows={[row]} />)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('what the last hit bought')).toBeNull()
    await userEvent.click(button)
    expect(onToggle).toHaveBeenCalledTimes(1)
    // The row did not open itself: the caller owns the state, which is how
    // the desktop toggle and the phone disclosure stay the same fact.
    expect(screen.queryByText('what the last hit bought')).toBeNull()
    rerender(<StackedRows rows={[{ ...row, open: true }]} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('what the last hit bought')).toBeInTheDocument()
  })
})
