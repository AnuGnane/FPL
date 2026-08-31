import { useMemo } from 'react'
import {
  Badge, type Column, DataTable, PosBadge, Sparkline, fmtNum, fmtPct,
  useIsMobile,
} from '../../kit'
import type { NextFixture } from '../../types'

export interface SquadRow {
  code: number
  name: string
  position: string
  ep: number
  /** p25/p75 of the sweep's noise on `ep`. Null for a player with no minutes
   *  model — an em dash, never a zero-width band. */
  epLo: number | null
  epHi: number | null
  pHaul: number | null
  pBlank: number | null
  xmins: number | null
  ownership: number
  leagueEo: number
  simPct: number | null
  last4: number[]
  news: string
  chanceOfPlaying: number | null
  penalties: boolean
  /** v9a identity, resolved server-side. The table does not draw any of
   *  these — they live here because the pitch and the table render from one
   *  array, and one row type is the whole reason the toggle is a toggle
   *  rather than two data paths. */
  teamShort: string | null
  teamCode: number | null
  nextFixture: NextFixture | null
}

export interface SquadBreakdown {
  ep: number
  components: Array<{ label: string; points: number }>
  /** How much of the Goals term is penalty duty, when any of it is. */
  penTaker: number | null
}

export interface SquadTableProps {
  rows: SquadRow[]
  breakdown: Record<number, SquadBreakdown>
}

/** Below this, "he might haul" is not news: it is the ordinary tail every
 *  forward carries, and a chip on every row is a chip on no row. */
const HAUL_CHIP = 0.15
/** Above this, the likeliest single outcome is a blank, which is worth saying
 *  out loud beside a starting place. */
const BLANK_CHIP = 0.35

function pct(value: number): string {
  return `${Math.round(value * 100)}%`
}

// The collapsed card shows only the primary columns, and Pos is not one of
// them — so on mobile the position rides along with the name as a dot rather
// than disappearing until the row is expanded.
function columnsFor(mobile: boolean): Column<SquadRow>[] { return [
  {
    key: 'name',
    header: 'Player',
    primary: true,
    value: (r) => r.name,
    render: (r) => (
      <span className="flex items-center gap-1.5">
        {mobile && <PosBadge pos={r.position} variant="dot" />}
        {r.name}
        {r.news && (
          <Badge variant="negative" title={r.news}>
            {r.chanceOfPlaying === null ? 'News' : `${r.chanceOfPlaying}%`}
          </Badge>
        )}
        {r.penalties && <Badge variant="info">Pens</Badge>}
        {r.pHaul !== null && r.pHaul >= HAUL_CHIP && (
          <Badge variant="positive"
                 title={`${pct(r.pHaul)} chance of 10+ points — the upper `
                   + 'tail of his outcome distribution, which is his '
                   + 'expected points plus the variance a footballer’s week '
                   + 'carries, not a guess at his ceiling'}>
            {`haul ${pct(r.pHaul)}`}
          </Badge>
        )}
        {r.pBlank !== null && r.pBlank >= BLANK_CHIP && (
          <Badge variant="negative"
                 title={`${pct(r.pBlank)} chance of 2 points or fewer — the `
                   + 'lower tail of the same distribution. A blank is an '
                   + 'appearance and nothing else, not a missed match'}>
            {`blank ${pct(r.pBlank)}`}
          </Badge>
        )}
      </span>
    ),
  },
  { key: 'position', header: 'Pos', value: (r) => r.position,
    render: (r) => <PosBadge pos={r.position} /> },
  { key: 'ep', header: 'xPts', primary: true, numeric: true,
    value: (r) => r.ep, render: (r) => fmtNum(r.ep) },
  { key: 'range', header: 'Range', numeric: true,
    value: (r) => (r.epHi === null || r.epLo === null
      ? null : r.epHi - r.epLo),
    render: (r) => (r.epLo === null || r.epHi === null
      ? <span className="num text-text-muted">—</span>
      : (
        <span className="num text-text-secondary"
              title={'p25–p75 of what he might score: his expected points '
                + 'plus football’s own variance, plus how far the forecast '
                + 'itself might move. Not a plus-or-minus — the centre is '
                + 'shifted down so the clipped range still averages the '
                + 'forecast, so the pair is quartiles.'}>
          {`${r.epLo.toFixed(1)}–${r.epHi.toFixed(1)}`}
        </span>
      )) },
  { key: 'xmins', header: 'xMin', numeric: true, value: (r) => r.xmins,
    render: (r) => fmtNum(r.xmins, 0) },
  { key: 'leagueEo', header: 'EO%', primary: true, numeric: true,
    value: (r) => r.leagueEo, render: (r) => fmtNum(r.leagueEo) },
  { key: 'ownership', header: 'Own%', numeric: true,
    value: (r) => r.ownership, render: (r) => fmtNum(r.ownership) },
  { key: 'simPct', header: 'sim%', numeric: true, value: (r) => r.simPct,
    render: (r) => fmtPct(r.simPct) },
  { key: 'last4', header: 'Last 4', numeric: true,
    value: (r) => r.last4.length ? r.last4[r.last4.length - 1] : null,
    render: (r) => <Sparkline values={r.last4} /> },
] }

export default function SquadTable({ rows, breakdown }: SquadTableProps) {
  const mobile = useIsMobile()
  // A fresh array on every render would defeat DataTable's sort memo.
  const columns = useMemo(() => columnsFor(mobile), [mobile])
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.code}
      rowLabel={(r) => r.name}
      initialSort="ep"
      expand={(row) => {
        const detail = breakdown[row.code]
        if (!detail) {
          return (
            <p className="text-text-muted">
              No saved breakdown for this player — run advise to write one.
            </p>
          )
        }
        return (
          <div>
            <div className="overflow-x-auto">
            <table className="w-full">
              <tbody>
                {detail.components.map((c) => (
                  <tr key={c.label}>
                    <td className="py-0.5 text-text-secondary">{c.label}</td>
                    <td className="num py-0.5 text-right text-text">
                      {fmtNum(c.points)}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td className="label pt-1">Total</td>
                  <td className="num pt-1 text-right text-text">
                    {fmtNum(detail.ep)}
                  </td>
                </tr>
              </tbody>
            </table>
            </div>
            {detail.penTaker !== null && (
              <p className="mt-2 text-text-muted">
                {fmtNum(detail.penTaker, 1)} of Goals is penalty duty.
              </p>
            )}
          </div>
        )
      }}
    />
  )
}
