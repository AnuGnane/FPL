import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import SquadTable, { type SquadRow } from './SquadTable'

const ROWS: SquadRow[] = [
  {
    code: 1, name: 'Salah', position: 'MID', ep: 6.4, epLo: null,
    epHi: null, pHaul: null, pBlank: null, xmins: 88,
    ownership: 42.1, leagueEo: 61.5, simPct: 0.82, last4: [2, 9, 5, 12],
    news: 'Knock - 75% chance of playing', chanceOfPlaying: 75,
    penalties: true,
  },
  {
    code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6, epLo: null,
    epHi: null, pHaul: null, pBlank: null, xmins: 90,
    ownership: 30.0, leagueEo: 12.0, simPct: null, last4: [],
    news: '', chanceOfPlaying: null, penalties: false,
  },
]

describe('SquadTable', () => {
  it('renders one row per squad member with its numbers', () => {
    render(<SquadTable rows={ROWS} breakdown={{}} />)
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('6.4')).toBeInTheDocument()
    expect(screen.getByText('61.5')).toBeInTheDocument()
  })

  it('badges a player carrying news and one on penalties', () => {
    render(<SquadTable rows={ROWS} breakdown={{}} />)
    expect(screen.getByTitle('Knock - 75% chance of playing'))
      .toHaveTextContent('75%')
    expect(screen.getByText('Pens')).toBeInTheDocument()
  })

  it('shows an em dash for a missing sim percentage', () => {
    render(<SquadTable rows={ROWS} breakdown={{}} />)
    const row = screen.getByText('Gabriel').closest('tr')!
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('expands a row into its EP component breakdown', async () => {
    render(
      <SquadTable
        rows={ROWS}
        breakdown={{
          1: {
            ep: 6.4,
            components: [{ label: 'Minutes', points: 1.9 },
                         { label: 'Goals', points: 3.1 }],
            penTaker: 0.6,
          },
        }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /expand Salah/i }))
    expect(screen.getByText('Minutes')).toBeInTheDocument()
    expect(screen.getByText('3.1')).toBeInTheDocument()
    expect(screen.getByText(/0.6 of Goals is penalty duty/))
      .toBeInTheDocument()
  })

  it('says so when a row has no saved breakdown', async () => {
    render(<SquadTable rows={ROWS} breakdown={{}} />)
    await userEvent.click(screen.getByRole('button', { name: /expand Salah/i }))
    expect(screen.getByText(/no saved breakdown/i)).toBeInTheDocument()
  })
})

// One template row, so each v8g test states only the field it is about.
function row(over: Partial<SquadRow>): SquadRow {
  return {
    code: 1, name: 'Salah', position: 'MID', ep: 5.4, epLo: null, epHi: null,
    pHaul: null, pBlank: null, xmins: 88, ownership: 20, leagueEo: 20,
    simPct: null, last4: [], news: '', chanceOfPlaying: null,
    penalties: false, ...over,
  }
}

function renderTable(rows: SquadRow[]) {
  render(<SquadTable rows={rows} breakdown={{}} />)
}

describe('v8g bands', () => {
  it('prints the quartile range beside the point estimate', () => {
    renderTable([row({ code: 1, ep: 5.4, epLo: 4.1, epHi: 6.8 })])
    expect(screen.getByText('4.1\u20136.8')).toBeInTheDocument()
  })

  it('prints an em dash for a player with no minutes model', () => {
    renderTable([row({ code: 1, ep: 5.4, epLo: null, epHi: null })])
    // Not "5.4-5.4": no band is a different claim from a band of width zero.
    expect(screen.queryByText('5.4\u20135.4')).toBeNull()
  })

  it('chips a genuine haul chance and not a negligible one', () => {
    renderTable([row({ code: 1, pHaul: 0.22 }),
                 row({ code: 2, pHaul: 0.02 })])
    expect(screen.getAllByTitle(/chance of 10\+ points/)).toHaveLength(1)
  })

  it('chips a serious blank risk', () => {
    renderTable([row({ code: 1, pBlank: 0.55 })])
    expect(screen.getByTitle(/chance of 2 points or fewer/))
      .toBeInTheDocument()
  })
})
