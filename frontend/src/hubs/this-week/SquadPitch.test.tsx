import { render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import SquadPitch from './SquadPitch'
import type { SquadRow } from './SquadTable'

function row(over: Partial<SquadRow>): SquadRow {
  return {
    code: 1, name: 'Player', position: 'MID', ep: 4.0, epLo: null, epHi: null,
    pHaul: null, pBlank: null, xmins: null, ownership: 0, leagueEo: 0,
    simPct: null, last4: [], news: '', chanceOfPlaying: null,
    penalties: false, teamShort: 'ARS', teamCode: 3,
    nextFixture: { opponent_short: 'MUN', home: true,
                   kickoff_utc: '2026-09-12T14:00:00Z', difficulty: 0.3 },
    ...over,
  }
}

const XI: SquadRow[] = [
  row({ code: 1, name: 'Raya', position: 'GKP' }),
  row({ code: 2, name: 'Saliba', position: 'DEF' }),
  row({ code: 3, name: 'Gabriel', position: 'DEF' }),
  row({ code: 4, name: 'White', position: 'DEF' }),
  row({ code: 5, name: 'Timber', position: 'DEF' }),
  row({ code: 6, name: 'Saka', position: 'MID' }),
  row({ code: 7, name: 'Odegaard', position: 'MID' }),
  row({ code: 8, name: 'Rice', position: 'MID' }),
  row({ code: 9, name: 'Rogers', position: 'MID' }),
  row({ code: 10, name: 'Haaland', position: 'FWD' }),
  row({ code: 11, name: 'Isak', position: 'FWD' }),
]

const BENCH: SquadRow[] = [
  row({ code: 12, name: 'Sels', position: 'GKP' }),
  row({ code: 13, name: 'Andersen', position: 'DEF' }),
  row({ code: 14, name: 'Semenyo', position: 'MID' }),
  row({ code: 15, name: 'Wood', position: 'FWD' }),
]

function pitch(over: Partial<ComponentProps<typeof SquadPitch>> = {}) {
  return render(
    <SquadPitch xi={XI} bench={BENCH} captain={6} vice={10} {...over} />,
  )
}

describe('SquadPitch', () => {
  it('lays the XI out in four formation rows', () => {
    pitch()
    expect(within(screen.getByTestId('pitch-row-GKP'))
      .getAllByText(/Raya/)).toHaveLength(1)
    expect(within(screen.getByTestId('pitch-row-DEF'))
      .getAllByRole('img')).toHaveLength(4)
    expect(within(screen.getByTestId('pitch-row-MID'))
      .getAllByRole('img')).toHaveLength(4)
    expect(within(screen.getByTestId('pitch-row-FWD'))
      .getAllByRole('img')).toHaveLength(2)
  })

  it('omits a line nobody is playing rather than drawing an empty band', () => {
    // A 3-5-2 with no forwards is not a formation, but a payload can arrive
    // mid-solve with a line unfilled and an empty green stripe reads as a bug.
    pitch({ xi: XI.filter((p) => p.position !== 'FWD') })
    expect(screen.queryByTestId('pitch-row-FWD')).not.toBeInTheDocument()
  })

  it('puts a player with no position in a row of his own, not nowhere', () => {
    // Advice written before v3.1 has no `position`. Losing a player off the
    // pitch entirely would be worse than an ugly extra row.
    pitch({ xi: [...XI.slice(0, 10), row({ code: 99, name: 'Legacy',
                                           position: '' })] })
    expect(within(screen.getByTestId('pitch-row-OTHER'))
      .getByText('Legacy')).toBeInTheDocument()
  })

  it('draws the bench below the pitch, in bench order', () => {
    pitch()
    const strip = screen.getByTestId('bench-strip')
    expect(within(strip).getAllByRole('img')).toHaveLength(4)
    const names = within(strip).getAllByText(/Sels|Andersen|Semenyo|Wood/)
      .map((n) => n.textContent)
    expect(names).toEqual(['Sels', 'Andersen', 'Semenyo', 'Wood'])
  })

  it('renders an empty bench without collapsing the pitch', () => {
    pitch({ bench: [] })
    expect(screen.getByTestId('pitch-row-GKP')).toBeInTheDocument()
    expect(screen.queryByTestId('bench-strip')).not.toBeInTheDocument()
  })

  it('puts the armbands on the right two heads', () => {
    pitch()
    expect(screen.getByTitle('Captain')).toBeInTheDocument()
    expect(screen.getByTitle('Vice-captain')).toBeInTheDocument()
  })

  it('gives a benched captain his armband too', () => {
    // Rare and real: a captain the solver benched should not silently lose
    // the band on the one screen that shows it.
    pitch({ captain: 12 })
    const strip = screen.getByTestId('bench-strip')
    expect(within(strip).getByTitle('Captain')).toBeInTheDocument()
  })

  it('carries a doubtful player’s flag onto the pitch', () => {
    pitch({ xi: [...XI.slice(0, 5), row({ code: 6, name: 'Saka',
                                          position: 'MID',
                                          news: 'Knock',
                                          chanceOfPlaying: 50 }),
                 ...XI.slice(6)] })
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('says Blank for a player whose team does not play', () => {
    pitch({ xi: [row({ code: 1, name: 'Raya', position: 'GKP',
                       nextFixture: null }), ...XI.slice(1)] })
    expect(screen.getAllByText('Blank')).toHaveLength(1)
  })

  it('renders with no identity at all, as a cold clone would', () => {
    // Every new field null: no snapshot, no fixtures, no ticker. The pitch is
    // still a pitch.
    pitch({
      xi: XI.map((p) => ({ ...p, teamShort: null, teamCode: null,
                           nextFixture: null })),
      bench: [],
    })
    expect(screen.getByTestId('pitch-row-GKP')).toBeInTheDocument()
    expect(screen.getAllByText('Blank').length).toBeGreaterThan(0)
  })
})

describe('SquadPitch: the EO lens (v10b §F1c)', () => {
  const tinted = () => Array.from(document.querySelectorAll('[data-code]'))
    .filter((el) => (el as HTMLElement).style.borderColor !== '')

  const lensXi = XI.map((p, i) => (
    i === 0 ? { ...p, fieldClass: 'shield' as const } : p))
  const lensBench = BENCH.map((p, i) => (
    i === 0 ? { ...p, fieldClass: 'sword' as const } : p))

  it('tints through the one card() funnel when the lens is on', () => {
    render(<SquadPitch xi={lensXi} bench={BENCH} captain={1} vice={2} lens />)
    expect(tinted()).toHaveLength(1)
  })

  it('tints a bench card on the same rule as an XI card', () => {
    render(<SquadPitch xi={XI} bench={lensBench} captain={1} vice={2} lens />)
    expect(tinted()).toHaveLength(1)
  })

  it('tints nothing when the lens is off', () => {
    render(<SquadPitch xi={lensXi} bench={lensBench} captain={1} vice={2} />)
    expect(tinted()).toHaveLength(0)
  })

  it('renders rows built by the existing factory, without the new fields',
     () => {
       // Plan A6's "optional", asserted: three factories in two files predate
       // fieldEo/fieldClass and none of them should have to change.
       render(<SquadPitch xi={XI} bench={BENCH} captain={1} vice={2} lens />)
       expect(screen.getByTestId('pitch-row-MID')).toBeInTheDocument()
     })
})
