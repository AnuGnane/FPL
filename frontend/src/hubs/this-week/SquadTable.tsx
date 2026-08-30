import { useMemo } from 'react'
import {
  Badge, type Column, DataTable, PosBadge, Sparkline, fmtNum, fmtPct,
  useIsMobile,
} from '../../kit'

export interface SquadRow {
  code: number
  name: string
  position: string
  ep: number
  xmins: number | null
  ownership: number
  leagueEo: number
  simPct: number | null
  last4: number[]
  news: string
  chanceOfPlaying: number | null
  penalties: boolean
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
      </span>
    ),
  },
  { key: 'position', header: 'Pos', value: (r) => r.position,
    render: (r) => <PosBadge pos={r.position} /> },
  { key: 'ep', header: 'xPts', primary: true, numeric: true,
    value: (r) => r.ep, render: (r) => fmtNum(r.ep) },
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
