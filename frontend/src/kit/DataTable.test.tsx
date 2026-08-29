import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import DataTable, { type Column } from './DataTable'

interface Row { code: number; name: string; ep: number }

const ROWS: Row[] = [
  { code: 1, name: 'Salah', ep: 6.4 },
  { code: 2, name: 'Haaland', ep: 7.1 },
  { code: 3, name: 'Palmer', ep: 5.2 },
]

const COLUMNS: Column<Row>[] = [
  { key: 'name', header: 'Player', primary: true, value: (r) => r.name },
  { key: 'ep', header: 'xPts', primary: true, numeric: true, value: (r) => r.ep },
  { key: 'code', header: 'Code', numeric: true, value: (r) => r.code },
]

describe('DataTable', () => {
  it('renders one row per record with numeric cells in the mono face', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.code} />)
    expect(screen.getAllByRole('row')).toHaveLength(4) // header + 3
    expect(screen.getByText('6.4')).toHaveClass('num')
  })

  it('sorts descending on the first header click and ascending on the second',
    async () => {
      render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.code} />)
      await userEvent.click(screen.getByRole('button', { name: /xPts/ }))
      let cells = screen.getAllByRole('row').slice(1)
        .map((row) => within(row).getAllByRole('cell')[0].textContent)
      expect(cells).toEqual(['Haaland', 'Salah', 'Palmer'])
      await userEvent.click(screen.getByRole('button', { name: /xPts/ }))
      cells = screen.getAllByRole('row').slice(1)
        .map((row) => within(row).getAllByRole('cell')[0].textContent)
      expect(cells).toEqual(['Palmer', 'Salah', 'Haaland'])
    })

  it('expands a row into the expand renderer on click', async () => {
    render(
      <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.code}
                 expand={(r) => <p>breakdown for {r.name}</p>} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /expand Salah/i }))
    expect(screen.getByText('breakdown for Salah')).toBeInTheDocument()
  })

  it('renders the empty slot when there are no rows', () => {
    render(<DataTable columns={COLUMNS} rows={[]} rowKey={(r) => r.code}
                      empty={<p>nothing here</p>} />)
    expect(screen.getByText('nothing here')).toBeInTheDocument()
  })

  it('collapses to cards showing only the primary columns', async () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.code}
                      collapse />)
    expect(screen.queryByRole('table')).toBeNull()
    const card = screen.getByTestId('row-card-1')
    expect(within(card).getByText('Salah')).toBeInTheDocument()
    expect(within(card).getByText('6.4')).toBeInTheDocument()
    expect(within(card).queryByText('Code')).toBeNull()
    await userEvent.click(within(card).getByRole('button', { name: /more/i }))
    expect(within(card).getByText('Code')).toBeInTheDocument()
  })

  it('offers sorting through a dropdown in collapse mode', async () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.code}
                      collapse />)
    await userEvent.click(screen.getByRole('button', { name: /sort/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'xPts' }))
    expect(screen.getAllByTestId(/row-card-/)[0]).toHaveAttribute(
      'data-testid', 'row-card-2')
  })
})

describe('descending sort', () => {
  // reverse() on the ascending order is not the descending order: it reverses
  // *everything*, so rows that tied land in the opposite order to the one they
  // came in, and the nulls the comparator carefully pushed to the bottom come
  // out on top.
  interface Row { id: number; name: string; score: number | null }

  const cols: Column<Row>[] = [
    { key: 'name', header: 'Name', value: (r) => r.name },
    { key: 'score', header: 'Score', numeric: true, value: (r) => r.score },
  ]

  const names = () => screen.getAllByRole('row').slice(1)
    .map((row) => row.querySelectorAll('td')[0].textContent)

  it('keeps nulls last in both directions', async () => {
    const rows: Row[] = [
      { id: 1, name: 'A', score: 5 },
      { id: 2, name: 'B', score: null },
      { id: 3, name: 'C', score: 9 },
    ]
    render(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id}
                      collapse={false} initialSort="score" />)
    expect(names()).toEqual(['C', 'A', 'B'])
    await userEvent.click(screen.getByRole('button', { name: /Score/ }))
    expect(names()).toEqual(['A', 'C', 'B'])
  })

  it('is stable across ties', async () => {
    const rows: Row[] = [
      { id: 1, name: 'A', score: 5 },
      { id: 2, name: 'B', score: 5 },
      { id: 3, name: 'C', score: 5 },
    ]
    render(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id}
                      collapse={false} initialSort="score" />)
    expect(names()).toEqual(['A', 'B', 'C'])
    await userEvent.click(screen.getByRole('button', { name: /Score/ }))
    // Same score, so the input order stands; reversing flipped them to C,B,A.
    expect(names()).toEqual(['A', 'B', 'C'])
  })
})
