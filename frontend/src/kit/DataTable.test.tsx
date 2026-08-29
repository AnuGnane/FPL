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
