import { useMemo, useState } from 'react'
import {
  Bar, Chip, type Column, DataTable, PosBadge, Sparkline, StackedPairs,
  StackedRows, TABLE_CLASS, TR_CLASS, fmtNum, fmtPct, tdClass, useIsMobile,
} from '../../kit'
import type { StackedPair, StackedRow } from '../../kit'
import type { NextFixture } from '../../types'
import PlayerActions from './PlayerActions'

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
  /** v10b §F1a: the top-10k share and its classification, joined client-side
   *  off `/api/players` — which already computes both against the same owned
   *  set these rows describe. Optional, because the server's own contract is
   *  "may be absent" and because three row factories predate them. */
  fieldEo?: number | null
  fieldClass?: 'shield' | 'sword' | 'threat' | null
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
 *  forward carries, and a chip on every row is a chip on no row.
 *
 *  The quantity is the *band* one — P(total points >= 10) in the tail of the
 *  whole forecast (`uncertainty.Band.p_haul`), not the attacking P(2+ returns)
 *  the advice payload carries as `p_attacking_haul`. The chip says "10+ pts"
 *  rather than "haul" for exactly that reason (v9c D3). */
const HAUL_CHIP = 0.15
/** Above this, the likeliest single outcome is a blank, which is worth saying
 *  out loud beside a starting place. */
const BLANK_CHIP = 0.35

function pct(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** The three verdict chips a row can carry.
 *
 *  v18f §2.2. Three chips whose tone carries the verdict — doubt, upside,
 *  downside — and a bare percentage in a colour says nothing to a screen
 *  reader. Each names its own tone in `sr-only` text, which is absolutely
 *  positioned and so changes no layout.
 *
 *  Lifted out of the name cell in v19c §2.1, unchanged, so the phone's
 *  stacked row can lead with the same chips the column draws. */
function Verdicts({ row: r }: { row: SquadRow }) {
  return (
    <>
      {r.news && (
        <Chip tone="warn" title={r.news}>
          <span className="sr-only">doubt: </span>
          {r.chanceOfPlaying === null ? 'News' : `${r.chanceOfPlaying}%`}
        </Chip>
      )}
      {r.penalties && <Chip>Pens</Chip>}
      {r.pHaul !== null && r.pHaul >= HAUL_CHIP && (
        <Chip tone="up"
              title={`${pct(r.pHaul)} chance of 10+ points — the upper `
                 + 'tail of his outcome distribution, which is his '
                 + 'expected points plus the variance a footballer’s week '
                 + 'carries, not a guess at his ceiling'}>
          <span className="sr-only">upside: </span>
          {`10+ pts ${pct(r.pHaul)}`}
        </Chip>
      )}
      {r.pBlank !== null && r.pBlank >= BLANK_CHIP && (
        <Chip tone="down"
              title={`${pct(r.pBlank)} chance of 2 points or fewer — the `
                + 'lower tail of the same distribution. A blank is an '
                + 'appearance and nothing else, not a missed match'}>
          <span className="sr-only">downside: </span>
          {`blank ${pct(r.pBlank)}`}
        </Chip>
      )}
    </>
  )
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
        <Verdicts row={r} />
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
      ? <span className="tn text-text-muted">—</span>
      : (
        <span className="tn text-text-secondary"
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
  // Rule 7: ownership and effective ownership are magnitudes against one
  // ceiling with a whole squad to compare, so each gets the bar with its
  // number beside it. The Bar clamps, so an EO above 100 fills the track.
  { key: 'leagueEo', header: 'EO%', primary: true, numeric: true,
    value: (r) => r.leagueEo,
    render: (r) => (
      <Bar fraction={r.leagueEo / 100} text={fmtNum(r.leagueEo)}
           testId={`eo-${r.code}`} aria-label={`EO ${fmtNum(r.leagueEo)}%`} />
    ) },
  // v10b §F1a. Deliberately not `primary`: EO% already holds the primary slot
  // for ownership on the 390px collapsed card, and two ownership columns
  // there is how the card stops being readable. The sort value falls back to
  // -1 so unknowns sort below a genuine 0.0 rather than beside it.
  { key: 'fieldEo', header: 'Field%', numeric: true,
    value: (r) => r.fieldEo ?? -1,
    render: (r) => (r.fieldEo == null
      ? <span className="tn text-text-muted">—</span>
      : (
        <Bar fraction={r.fieldEo / 100} text={fmtNum(r.fieldEo, 1)}
             testId={`field-${r.code}`}
             aria-label={`Field ${fmtNum(r.fieldEo, 1)}%`} />
        )) },
  { key: 'ownership', header: 'Own%', numeric: true,
    value: (r) => r.ownership,
    render: (r) => (
      <Bar fraction={r.ownership / 100} text={fmtNum(r.ownership)}
           testId={`own-${r.code}`}
           aria-label={`Owned by ${fmtNum(r.ownership)}%`} />
    ) },
  { key: 'simPct', header: 'sim%', numeric: true, value: (r) => r.simPct,
    render: (r) => fmtPct(r.simPct) },
  { key: 'last4', header: 'Last 4', numeric: true,
    value: (r) => r.last4.length ? r.last4[r.last4.length - 1] : null,
    render: (r) => <Sparkline values={r.last4} /> },
  // v19e §2.4: the row's own menu, at its end because it is not a fact about
  // the player — it is what to do about him. Headerless, so the table reads
  // exactly as it did with one glyph more per row.
  { key: 'actions', header: '', value: () => null,
    render: (r) => <PlayerActions code={r.code} name={r.name} /> },
] }

/** The columns a stacked row shows before it is opened (v19c §2.1): what he
 *  is worth, how wide the forecast is, whether he plays, and where he puts
 *  you against your league. Every other column is a pair inside the
 *  disclosure, so the phone loses nothing the table has. */
const PHONE_PAIRS = ['ep', 'range', 'xmins', 'leagueEo']

/** The columns as label/value pairs — the same `render` the `<td>` calls, so
 *  the two renderings print one number and not two. */
function pairsFrom(
  columns: Column<SquadRow>[], row: SquadRow): StackedPair[] {
  return columns.map((column) => ({
    label: column.header,
    value: column.render ? column.render(row) : column.value(row),
    numeric: column.numeric,
  }))
}

/** The EP decomposition, as pairs rather than as the desktop's two-column
 *  table: a phone row must carry no `<table>` of its own (v19c §2.1), and the
 *  numbers are `breakdown`'s either way. */
function PhoneBreakdown({ detail }: { detail: SquadBreakdown | undefined }) {
  if (!detail) {
    return (
      <p className="text-text-muted">
        No saved breakdown for this player — run advise to write one.
      </p>
    )
  }
  return (
    <>
      <StackedPairs
        pairs={[...detail.components.map((c) => ({
          label: c.label, value: fmtNum(c.points), numeric: true,
        })), { label: 'Total', value: fmtNum(detail.ep), numeric: true }]}
      />
      {detail.penTaker !== null && (
        <p className="mt-2 text-text-muted">
          {fmtNum(detail.penTaker, 1)} of Goals is penalty duty.
        </p>
      )}
    </>
  )
}

export default function SquadTable({ rows, breakdown }: SquadTableProps) {
  const mobile = useIsMobile()
  // A fresh array on every render would defeat DataTable's sort memo.
  const columns = useMemo(() => columnsFor(mobile), [mobile])
  // The phone's open rows. DataTable owns the desktop's; this is the same
  // fact for the rendering that does not go through it.
  const [open, setOpen] = useState<Set<number>>(new Set())

  if (mobile) {
    const shown = columns.filter((c) => PHONE_PAIRS.includes(c.key))
    // The position is the dot beside the name and the name is the title, so
    // neither is a pair; everything else the table draws is one.
    const rest = columns.filter((c) => c.key !== 'name' && c.key !== 'position'
      && c.key !== 'actions' && !PHONE_PAIRS.includes(c.key))
    // The order the advice served — the XI, then the bench. The desktop table
    // sorts, and the rows arrive in that order (v19c §2.1).
    const stacked: StackedRow[] = rows.map((row) => ({
      key: row.code,
      lead: <Verdicts row={row} />,
      title: (
        <span className="inline-flex items-center gap-1.5">
          <PosBadge pos={row.position} variant="dot" />
          {row.name}
          {/* v19e §2.4: in the title, because a stacked row has no last cell
              to put it in and the disclosure would hide it. */}
          <PlayerActions code={row.code} name={row.name} />
        </span>
      ),
      pairs: pairsFrom(shown, row),
      detail: (
        <div className="flex flex-col gap-2">
          <StackedPairs pairs={pairsFrom(rest, row)} />
          <PhoneBreakdown detail={breakdown[row.code]} />
        </div>
      ),
      open: open.has(row.code),
      onToggle: () => setOpen((prev) => {
        const next = new Set(prev)
        if (next.has(row.code)) next.delete(row.code)
        else next.add(row.code)
        return next
      }),
    }))
    return <StackedRows rows={stacked} testId="squad-stacked" />
  }

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
            <table className={TABLE_CLASS}>
              <tbody>
                {detail.components.map((c) => (
                  <tr key={c.label} className={TR_CLASS}>
                    <td className={`${tdClass()} text-text-secondary`}>
                      {c.label}
                    </td>
                    <td className={`${tdClass(true)} text-text`}>
                      {fmtNum(c.points)}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td className={`${tdClass()} label`}>Total</td>
                  <td className={`${tdClass(true)} text-text`}>
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
